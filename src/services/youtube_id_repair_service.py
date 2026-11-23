"""Repair videos whose youtube_id no longer matches their downloaded file (#634).

Before v1.1.9, "force refresh" metadata enrichment could replace a downloaded
video's YouTube ID with a fuzzy title match. yt-dlp wrote the real ID into each
download's ``.info.json`` at download time, so it can be restored from there.

Dry run by default. Only videos whose stored ID *differs* from the file's are
changed; videos with no ID are filled only with ``fill_missing=True``. Conflicts (an ID owned by an unrelated video, or two
videos whose files carry the same ID) are reported and left untouched; they
need a human decision (usually: a duplicate download).
"""

import json
import os
from typing import Any, Dict, List, Optional

from src.database.models import Video
from src.utils.logger import get_logger
from src.utils.media_paths import resolve_media_path

logger = get_logger("mvidarr.youtube_id_repair")


def _file_identity(video: Video) -> Optional[Dict[str, str]]:
    """The YouTube id/url recorded next to the media file, if readable."""
    media = resolve_media_path(video.local_path)
    if media is None:
        return None
    info = media.with_suffix(".info.json")
    if not info.exists():
        return None
    try:
        data = json.loads(info.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    file_id = data.get("id")
    if not isinstance(file_id, str) or not file_id:
        return None
    return {
        "id": file_id,
        "url": data.get("webpage_url") or f"https://www.youtube.com/watch?v={file_id}",
    }


def repair_youtube_ids(
    session, apply: bool = False, fill_missing: bool = False
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "applied": apply,
        "checked": 0,
        "to_fix": 0,
        "missing_not_filled": 0,
        "fixed": 0,
        "no_info_json": 0,
        "conflicts": [],
        "errors": [],
        "details": [],
    }

    owners = {
        yid: vid
        for vid, yid in session.query(Video.id, Video.youtube_id)
        .filter(Video.youtube_id.isnot(None))
        .all()
    }

    videos = (
        session.query(Video)
        .filter(Video.local_path.isnot(None))
        .order_by(Video.id)
        .all()
    )
    by_id = {v.id: v for v in videos}
    planned: Dict[int, Dict[str, str]] = {}
    for v in videos:
        ident = _file_identity(v)
        report["checked"] += 1
        if ident is None:
            if resolve_media_path(v.local_path) is not None:
                report["no_info_json"] += 1
            continue
        if v.youtube_id == ident["id"]:
            continue
        if v.youtube_id is None and not fill_missing:
            # Not the #634 corruption: this video never had an ID. Only touched
            # on request, because the file's ID is often already owned by a
            # duplicate row and it is not what the user asked for.
            report["missing_not_filled"] += 1
            continue
        planned[v.id] = ident

    # Drop plans that cannot be applied, restarting each time because a dropped
    # plan changes who still owns an ID.
    while True:
        claimed: Dict[str, int] = {}
        dropped = None
        for vid in sorted(planned):
            new = planned[vid]["id"]
            if new in claimed:
                dropped = (
                    vid,
                    f"video {vid}: file id {new} is also the file id of video "
                    f"{claimed[new]}: probably a duplicate download; left unchanged",
                )
                break
            owner = owners.get(new)
            if owner is not None and owner != vid and owner not in planned:
                dropped = (
                    vid,
                    f"video {vid}: its file's id {new} is already used by video "
                    f"{owner}: probably a duplicate row for the same YouTube video; "
                    f"left unchanged",
                )
                break
            claimed[new] = vid
        if dropped is None:
            break
        report["conflicts"].append(dropped[1])
        del planned[dropped[0]]

    report["to_fix"] = len(planned)
    for vid, ident in planned.items():
        v = by_id[vid]
        report["details"].append(
            {"video_id": vid, "title": v.title, "old": v.youtube_id, "new": ident["id"]}
        )

    if not apply or not planned:
        return report

    try:
        # Two phases inside one transaction: IDs may need to swap, and the
        # unique constraint forbids a direct swap.
        old_ids = {}
        for vid in planned:
            old_ids[vid] = by_id[vid].youtube_id
            by_id[vid].youtube_id = None
        session.flush()
        for vid, ident in planned.items():
            v = by_id[vid]
            old = old_ids[vid]
            v.youtube_id = ident["id"]
            v.youtube_url = ident["url"]
            if old and v.url and old in v.url:
                v.url = v.url.replace(old, ident["id"])
        session.commit()
        report["fixed"] = len(planned)
    except Exception as e:
        session.rollback()
        report["errors"].append(f"rolled back, nothing changed: {e}")
        logger.error(f"YouTube ID repair failed: {e}")
    return report
