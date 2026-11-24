"""Remux existing .mkv downloads to .mp4 without re-encoding (#633).

Before v1.1.9 yt-dlp merged H.264+Opus and VP9+AAC into MKV, which the UI then
flags as needing transcoding. New downloads are merged into MP4; this repairs
the ones already on disk. It is a lossless stream copy (``ffmpeg -c copy``).

Safety: the new file is written to ``<name>.mp4.part``, verified (has a video
stream, duration matches the source) and only then renamed into place. The
database is updated and committed before the original is deleted, and a failure
at any step leaves the original and the database untouched. Dry run by default.
"""

import json
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional

from src.database.models import Download, Video
from src.utils.logger import get_logger
from src.utils.media_paths import resolve_media_path

logger = get_logger("mvidarr.mkv_remux")

DURATION_TOLERANCE_SECONDS = 1.0
DURATION_TOLERANCE_RATIO = 0.005


def _probe(runner: Callable, path: str) -> Optional[Dict[str, Any]]:
    proc = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
        return {
            "duration": float(data.get("format", {}).get("duration") or 0),
            "video": [
                s for s in data.get("streams", []) if s.get("codec_type") == "video"
            ],
            "audio": [
                s for s in data.get("streams", []) if s.get("codec_type") == "audio"
            ],
        }
    except (ValueError, TypeError):
        return None


def _duration_matches(src: float, out: float) -> bool:
    return abs(src - out) <= max(
        DURATION_TOLERANCE_SECONDS, src * DURATION_TOLERANCE_RATIO
    )


def remux_mkv_to_mp4(
    session,
    apply: bool = False,
    keep_original: bool = False,
    runner: Callable = subprocess.run,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "applied": apply,
        "candidates": 0,
        "remuxed": 0,
        "conflicts": [],
        "errors": [],
        "details": [],
    }
    videos: List[Video] = (
        session.query(Video)
        .filter(Video.local_path.ilike("%.mkv"))
        .order_by(Video.id)
        .all()
    )
    for video in videos:
        src = resolve_media_path(video.local_path)
        if src is None:
            continue
        report["candidates"] += 1
        target = src.with_suffix(".mp4")
        part = src.with_suffix(".mp4.part")
        detail = {"video_id": video.id, "from": src.name, "to": target.name}
        report["details"].append(detail)

        if target.exists():
            report["conflicts"].append(
                f"video {video.id}: {target.name} already exists; left unchanged"
            )
            continue
        if not apply:
            continue

        try:
            before = _probe(runner, str(src))
            if not before or not before["video"]:
                raise RuntimeError("source has no readable video stream")
            # video + audio only: MP4 cannot carry MKV attachments/most subtitle codecs
            proc = runner(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(src),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-f",
                    "mp4",
                    str(part),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed: {(proc.stderr or '').strip()[:200]}"
                )
            after = _probe(runner, str(part))
            if not after or not after["video"]:
                raise RuntimeError("remuxed file has no readable video stream")
            if not _duration_matches(before["duration"], after["duration"]):
                raise RuntimeError(
                    f"duration mismatch (source {before['duration']:.1f}s, "
                    f"remuxed {after['duration']:.1f}s)"
                )
            if len(after["audio"]) < len(before["audio"][:1]):
                raise RuntimeError("audio stream was lost in the remux")
            os.replace(part, target)
        except Exception as e:
            if part.exists():
                part.unlink()
            report["errors"].append(f"video {video.id}: {e}")
            logger.error(f"MKV remux failed for video {video.id}: {e}")
            continue

        old_local = video.local_path
        new_local = os.path.splitext(old_local)[0] + ".mp4"
        try:
            video.local_path = new_local
            for d in session.query(Download).filter(Download.video_id == video.id):
                if d.file_path == old_local:
                    d.file_path = new_local
                    d.file_size = target.stat().st_size
            session.commit()
        except Exception as e:
            session.rollback()
            target.unlink()  # original is still in place and the DB points at it
            report["errors"].append(f"video {video.id}: database update failed: {e}")
            continue

        if not keep_original:
            try:
                src.unlink()
            except OSError as e:
                report["errors"].append(
                    f"video {video.id}: remuxed, but could not delete {src.name}: {e}"
                )
        report["remuxed"] += 1
    return report
