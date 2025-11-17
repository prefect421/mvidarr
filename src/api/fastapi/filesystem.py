"""
FastAPI Filesystem Browser API
Provides directory browsing capabilities for custom video imports.
"""

import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.filesystem")

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])


# ====================================
# Pydantic Models
# ====================================


class DirectoryEntry(BaseModel):
    """Single directory entry"""

    name: str
    path: str
    is_directory: bool
    is_readable: bool
    size: Optional[int] = None
    video_count: Optional[int] = None


class DirectoryListResponse(BaseModel):
    """Directory listing response"""

    current_path: str
    parent_path: Optional[str] = None
    entries: List[DirectoryEntry]
    total_entries: int


# ====================================
# Endpoints
# ====================================


@router.get("/browse", response_model=DirectoryListResponse)
async def browse_directory(
    path: str = Query(
        default="/", description="Directory path to browse (default: root)"
    )
):
    """
    Browse filesystem directories for video import.

    Returns a list of subdirectories and their metadata.
    Only shows directories (not files) to simplify navigation.

    Args:
        path: Directory path to browse

    Returns:
        List of directory entries with metadata
    """
    try:
        # Resolve path
        browse_path = Path(path).resolve()

        # Security check - ensure path exists and is directory
        if not browse_path.exists():
            raise HTTPException(status_code=404, detail="Directory does not exist")

        if not browse_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")

        # Check if readable
        if not os.access(browse_path, os.R_OK):
            raise HTTPException(status_code=403, detail="Directory is not readable")

        # Get parent directory
        parent_path = (
            str(browse_path.parent) if browse_path.parent != browse_path else None
        )

        # List directory contents (directories only)
        entries = []
        video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v"}

        try:
            for item in sorted(
                browse_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
            ):
                # Skip hidden files/directories (starting with .)
                if item.name.startswith("."):
                    continue

                is_dir = item.is_dir()
                is_readable = os.access(item, os.R_OK)

                entry = DirectoryEntry(
                    name=item.name,
                    path=str(item),
                    is_directory=is_dir,
                    is_readable=is_readable,
                )

                # Only include directories in the list
                if is_dir:
                    # Count video files in this directory (quick scan, not recursive)
                    try:
                        video_count = sum(
                            1
                            for f in item.iterdir()
                            if f.is_file() and f.suffix.lower() in video_extensions
                        )
                        entry.video_count = video_count if video_count > 0 else None
                    except (PermissionError, OSError):
                        entry.video_count = None

                    entries.append(entry)

        except PermissionError:
            raise HTTPException(
                status_code=403, detail="Permission denied reading directory"
            )

        return DirectoryListResponse(
            current_path=str(browse_path),
            parent_path=parent_path,
            entries=entries,
            total_entries=len(entries),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error browsing directory '{path}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/common-paths", response_model=List[DirectoryEntry])
async def get_common_paths():
    """
    Get common directory paths as shortcuts for browsing.

    Returns common locations like:
    - Home directory
    - /mnt (common mount point)
    - /media (common media mount)
    - Current music videos path

    Returns:
        List of common directory shortcuts
    """
    try:
        common_paths = []

        # Home directory
        home_dir = Path.home()
        if home_dir.exists() and home_dir.is_dir():
            common_paths.append(
                DirectoryEntry(
                    name=f"Home ({home_dir.name})",
                    path=str(home_dir),
                    is_directory=True,
                    is_readable=os.access(home_dir, os.R_OK),
                )
            )

        # Root
        root_dir = Path("/")
        if root_dir.exists() and root_dir.is_dir():
            common_paths.append(
                DirectoryEntry(
                    name="Root (/)",
                    path=str(root_dir),
                    is_directory=True,
                    is_readable=os.access(root_dir, os.R_OK),
                )
            )

        # /mnt (common mount point)
        mnt_dir = Path("/mnt")
        if mnt_dir.exists() and mnt_dir.is_dir() and os.access(mnt_dir, os.R_OK):
            common_paths.append(
                DirectoryEntry(
                    name="Mounts (/mnt)",
                    path=str(mnt_dir),
                    is_directory=True,
                    is_readable=True,
                )
            )

        # /media (common media mount)
        media_dir = Path("/media")
        if media_dir.exists() and media_dir.is_dir() and os.access(media_dir, os.R_OK):
            common_paths.append(
                DirectoryEntry(
                    name="Media (/media)",
                    path=str(media_dir),
                    is_directory=True,
                    is_readable=True,
                )
            )

        # Current music videos path from settings
        try:
            from src.services.settings_service import settings

            music_videos_path = settings.get("music_videos_path", "data/musicvideos")
            if music_videos_path:
                mvp = Path(music_videos_path)
                if mvp.exists() and mvp.is_dir():
                    common_paths.append(
                        DirectoryEntry(
                            name=f"Music Videos Library ({mvp.name})",
                            path=str(mvp),
                            is_directory=True,
                            is_readable=os.access(mvp, os.R_OK),
                        )
                    )
        except Exception as e:
            logger.warning(f"Could not get music videos path: {e}")

        return common_paths

    except Exception as e:
        logger.error(f"Error getting common paths: {e}")
        raise HTTPException(status_code=500, detail=str(e))
