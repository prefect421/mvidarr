"""Helpers for building YouTube URLs from validated IDs."""

import re
from typing import Optional

_YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def youtube_thumbnail_url(youtube_id) -> Optional[str]:
    """Canonical YouTube thumbnail URL for a video ID, or None if the ID is bad.

    The URL is always rebuilt from a strictly validated ID and never taken from
    the client: the server later downloads whatever is stored in
    ``thumbnail_url``, and allow-listing a client-supplied string is fragile
    (URL parsers disagree about backslashes, ``@`` and similar). hqdefault
    exists for every video; maxresdefault does not (#613).
    """
    if isinstance(youtube_id, str) and _YOUTUBE_ID_RE.fullmatch(youtube_id):
        return f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
    return None
