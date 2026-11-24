"""Move downloads that landed in the wrong folder into their artist's folder (#629).

Before v1.1.9, videos imported from a YouTube search were downloaded into a folder
named after the *uploading channel* ("The Prodigy - Topic", label names, "Unknown
Artist") instead of the artist the video is assigned to. This finds them and moves
them with the same safe, all-or-nothing mover the edit form uses. Dry run by default.
"""

import os
from typing import Any, Dict

from src.database.models import Video
from src.services.video_file_mover import move_video_to_artist_folder
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger
from src.utils.media_paths import resolve_media_path

logger = get_logger("mvidarr.misfiled_videos")


def _in_artist_folder(video: Video) -> bool:
    parent = os.path.basename(os.path.dirname(video.local_path)).strip().lower()
    artist = video.artist
    candidates = {
        FilenameCleanup.sanitize_folder_name(artist.name).lower(),
        artist.name.lower(),
    }
    if artist.folder_path:
        candidates.add(os.path.basename(str(artist.folder_path).rstrip("/")).lower())
    return parent in candidates


def repair_misfiled_videos(session, apply: bool = False) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "applied": apply,
        "checked": 0,
        "to_move": 0,
        "moved": 0,
        "conflicts": [],
        "errors": [],
        "details": [],
    }
    videos = (
        session.query(Video)
        .filter(Video.local_path.isnot(None), Video.artist_id.isnot(None))
        .order_by(Video.id)
        .all()
    )
    for video in videos:
        if video.artist is None or resolve_media_path(video.local_path) is None:
            continue
        report["checked"] += 1
        if _in_artist_folder(video):
            continue
        report["to_move"] += 1
        report["details"].append(
            {
                "video_id": video.id,
                "artist": video.artist.name,
                "from": os.path.basename(os.path.dirname(video.local_path)),
                "to": FilenameCleanup.sanitize_folder_name(video.artist.name),
                "file": os.path.basename(video.local_path),
            }
        )
        if not apply:
            continue
        res = move_video_to_artist_folder(session, video, video.artist.name)
        if res["error"]:
            report["conflicts"].append(f"video {video.id}: {res['error']}")
            session.rollback()
            continue
        try:
            session.commit()
            report["moved"] += int(res["moved"])
        except Exception as e:
            session.rollback()
            from src.services.video_file_mover import restore_moves

            restore_moves(res["done"])
            report["errors"].append(
                f"video {video.id}: database update failed, files restored: {e}"
            )
    return report
