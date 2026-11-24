"""Helpers for locating media files recorded in the database."""

from pathlib import Path
from typing import Optional

from src.config.config import Config


def resolve_media_path(path_str: Optional[str]) -> Optional[Path]:
    """Find a stored path on disk.

    Relative paths (``data/musicvideos/...``) are tried as given and then
    against the app root, the same way streaming resolves them.
    """
    if not path_str:
        return None
    p = Path(path_str)
    if p.exists():
        return p
    if not p.is_absolute():
        alt = Config.BASE_DIR / p
        if alt.exists():
            return alt
    return None
