"""Move a downloaded video (and its sidecar files) into another artist's folder.

Used when a video's artist is changed with "Move file to artist folder" ticked
(#635), and by scripts/fix_misfiled_videos.py to repair files that landed in a
channel-named folder (#629).

Safety: all-or-nothing. Every destination name is checked first (nothing is ever
overwritten); if any move fails, the ones already done are moved back. The caller
owns the database transaction: this updates ``video.local_path`` and matching
``Download.file_path`` rows on the session but does not commit, so a failed
commit can be rolled back and the files restored with ``restore_moves``.
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.config.config import Config
from src.database.models import Download, Video
from src.utils.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger
from src.utils.media_paths import resolve_media_path

logger = get_logger("mvidarr.video_file_mover")


def _library_root() -> str:
    """The configured music-video library folder (as recorded in local_path)."""
    from src.services.settings_service import settings

    root = settings.get("music_videos_path", "data/musicvideos")
    return root.strip() if root and root.strip() else "data/musicvideos"


def _sidecars(media: Path) -> List[Path]:
    """The media file plus every file sharing its exact stem (.info.json, subtitles).

    ``Song.mp4`` has sidecars ``Song.info.json`` / ``Song.en.vtt`` but NOT the
    unrelated ``Song (live).mp4``: a name only counts if it is the stem followed
    by a dot.
    """
    stem = media.stem
    out = [media]
    for sibling in sorted(media.parent.iterdir()):
        if sibling == media or not sibling.is_file():
            continue
        if sibling.name.startswith(stem + "."):
            out.append(sibling)
    return out


def restore_moves(done: List[Tuple[Path, Path]]) -> None:
    """Move already-moved files back (best effort, newest first)."""
    for src, dst in reversed(done):
        try:
            shutil.move(str(dst), str(src))
        except OSError as e:
            logger.error(f"Could not restore {dst} -> {src}: {e}")


def move_video_to_artist_folder(
    session, video: Video, artist_name: str
) -> Dict[str, Any]:
    """Move ``video``'s files into ``<library>/<sanitized artist_name>/``.

    Returns ``{"moved": bool, "error": str|None, "skipped": str|None, "done": [...]}``.
    ``done`` lists the (src, dst) pairs so a caller whose later commit fails can
    call :func:`restore_moves`. The folder name matches where new downloads go
    (the sanitized artist name).
    """
    result: Dict[str, Any] = {
        "moved": False,
        "error": None,
        "skipped": None,
        "done": [],
    }

    media = resolve_media_path(video.local_path)
    if media is None:
        result["skipped"] = "no file on disk"
        return result

    folder = FilenameCleanup.sanitize_folder_name(artist_name)
    library = _library_root()
    dest_dir_str = os.path.join(library, folder)
    dest_dir = Path(dest_dir_str)
    if not dest_dir.is_absolute():
        # Resolve against the same base the source was found under: the working
        # directory, or the app root (as streaming does for relative paths).
        recorded = Path(video.local_path)
        base = Path(".") if recorded.exists() else Config.BASE_DIR
        dest_dir = base / dest_dir_str

    try:
        if media.parent.resolve() == dest_dir.resolve():
            result["skipped"] = "already in the artist's folder"
            return result
    except OSError:
        pass

    files = _sidecars(media)
    moves = [(f, dest_dir / f.name) for f in files]
    for _, dst in moves:
        if dst.exists():
            result["error"] = f"target already exists: {dst}"
            return result

    done: List[Tuple[Path, Path]] = []
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src, dst in moves:
            shutil.move(str(src), str(dst))
            done.append((src, dst))
    except Exception as e:
        restore_moves(done)
        result["error"] = f"move failed, nothing changed: {e}"
        logger.error(f"Moving video {video.id} failed: {e}")
        return result

    old_local = video.local_path
    new_local = os.path.join(dest_dir_str, media.name)
    video.local_path = new_local
    for d in session.query(Download).filter(Download.video_id == video.id):
        if d.file_path == old_local:
            d.file_path = new_local

    result.update(moved=True, done=done, new_local_path=new_local)
    logger.info(f"Moved video {video.id} files to {dest_dir_str}")
    return result
