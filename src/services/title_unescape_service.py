"""One-off cleanup for HTML-escaped video titles (#612).

The YouTube Data API returns titles HTML-escaped (``&amp;``, ``&#39;``). New
titles are now unescaped when the API response is parsed; this module repairs
rows (and the files named after them) that were stored before that fix.

Always run as a dry run first. Renames are all-or-nothing per video and are
reversed if the database update fails.
"""

import html
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from src.database.models import Download, Video
from src.utils.logger import get_logger
from src.utils.media_paths import resolve_media_path

logger = get_logger("mvidarr.title_unescape")


_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_MARKUP_CHARS = {"<", ">", '"'}


def _decode_entity(match: "re.Match") -> str:
    entity = match.group(0)
    decoded = html.unescape(entity)
    # Leave unknown entities alone, and never decode to markup characters.
    if decoded == entity or decoded in _MARKUP_CHARS:
        return entity
    return decoded


def decode_entities(text: Optional[str]) -> Optional[str]:
    """Decode well-formed entities only; everything else is left byte-for-byte.

    Used for file names, where a literal ``"`` or ``<`` must not be rewritten.
    """
    if text is None:
        return None
    return _ENTITY_RE.sub(_decode_entity, text)


def _neutralise_raw(fragment: str) -> str:
    return fragment.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def unescape_text(text: Optional[str]) -> Optional[str]:
    """Make API/stored text readable without ever producing markup.

    - Well-formed entities such as ``&amp;`` and ``&#39;`` are decoded, except
      those for ``<``, ``>`` and ``"`` (and their numeric forms), which stay
      encoded.
    - Any *raw* ``<``, ``>`` or ``"`` in the input is encoded too. The YouTube
      API always escapes them, so this only matters for hostile or malformed
      responses, but it means the result can never contain live markup.
    - Only ``;``-terminated entities are decoded, in a single pass, so
      malformed text such as ``&quotTrue`` is left as stored and ``&amp;lt;``
      can never become ``<``.

    The frontend interpolates titles into innerHTML/attributes in many places
    (#622), which is why this is deliberately conservative. ``None`` passes
    through.
    """
    if text is None:
        return None
    out, last = [], 0
    for m in _ENTITY_RE.finditer(text):
        out.append(_neutralise_raw(text[last : m.start()]))
        out.append(_decode_entity(m))
        last = m.end()
    out.append(_neutralise_raw(text[last:]))
    return "".join(out)


def _escaped(text: Optional[str]) -> bool:
    """True if a *file name* contains a decodable entity."""
    return bool(text) and decode_entities(text) != text


def _title_needs_fix(text: Optional[str]) -> bool:
    return bool(text) and unescape_text(text) != text


def _plan_renames(real_path: Path) -> Dict[str, Any]:
    """Plan renames of the media file and every sibling sharing its stem.

    Returns ``{"moves": [(src, dst)], "conflict": str | None}``.
    """
    old_stem = real_path.stem
    new_stem = decode_entities(old_stem)
    if "/" in new_stem or "\\" in new_stem or "\0" in new_stem:
        return {"moves": [], "conflict": "unescaped name would contain a separator"}

    moves = []
    for sibling in sorted(real_path.parent.iterdir()):
        name = sibling.name
        if name == old_stem or name.startswith(old_stem + "."):
            moves.append((sibling, sibling.with_name(new_stem + name[len(old_stem) :])))

    for src, dst in moves:
        if dst.exists():
            return {"moves": [], "conflict": f"target already exists: {dst}"}
    return {"moves": moves, "conflict": None}


def _swap_basename(path_str: str, new_basename: str) -> str:
    return os.path.join(os.path.dirname(path_str), new_basename)


def cleanup_escaped_titles(session, apply: bool = False) -> Dict[str, Any]:
    """Unescape stored titles and rename the files named after them.

    Args:
        session: SQLAlchemy session.
        apply: when False (default) nothing is changed, only reported.
    """
    report: Dict[str, Any] = {
        "applied": apply,
        "titles_to_fix": 0,
        "files_to_rename": 0,
        "renamed": 0,
        "conflicts": [],
        "errors": [],
        "details": [],
    }

    videos: List[Video] = (
        session.query(Video)
        .filter(or_(Video.title.like("%&%;%"), Video.local_path.like("%&%;%")))
        .all()
    )

    for video in videos:
        title_escaped = _title_needs_fix(video.title)
        path_escaped = bool(video.local_path) and _escaped(
            os.path.basename(video.local_path)
        )
        if not (title_escaped or path_escaped):
            continue

        detail: Dict[str, Any] = {"video_id": video.id, "title": video.title}
        if title_escaped:
            report["titles_to_fix"] += 1
            detail["new_title"] = unescape_text(video.title)

        moves: List = []
        if path_escaped:
            real = resolve_media_path(video.local_path)
            if real is not None:
                plan = _plan_renames(real)
                if plan["conflict"]:
                    report["conflicts"].append(f"video {video.id}: {plan['conflict']}")
                else:
                    moves = plan["moves"]
        thumb_move = None
        if video.thumbnail_path and _escaped(os.path.basename(video.thumbnail_path)):
            t_real = resolve_media_path(video.thumbnail_path)
            if t_real is not None:
                t_new = t_real.with_name(decode_entities(t_real.name))
                if "/" not in t_new.name and not t_new.exists():
                    thumb_move = (t_real, t_new)

        if moves or thumb_move:
            report["files_to_rename"] += 1
            detail["renames"] = [f"{s.name} -> {d.name}" for s, d in moves]
        report["details"].append(detail)

        if not apply:
            continue

        done: List = []
        try:
            old_local = video.local_path
            for src, dst in moves + ([thumb_move] if thumb_move else []):
                src.rename(dst)
                done.append((src, dst))

            if title_escaped:
                video.title = unescape_text(video.title)
            if moves:
                new_local = _swap_basename(
                    old_local, decode_entities(os.path.basename(old_local))
                )
                video.local_path = new_local
                for d in session.query(Download).filter(Download.video_id == video.id):
                    if d.file_path == old_local:
                        d.file_path = new_local
            if thumb_move:
                video.thumbnail_path = _swap_basename(
                    video.thumbnail_path, thumb_move[1].name
                )
            session.commit()
            report["renamed"] += 1 if (moves or thumb_move) else 0
        except Exception as e:  # reverse any renames, keep the DB consistent
            session.rollback()
            for src, dst in reversed(done):
                try:
                    dst.rename(src)
                except OSError:
                    logger.error(f"Could not restore {dst} -> {src}")
            report["errors"].append(f"video {video.id}: {e}")
            logger.error(f"Title cleanup failed for video {video.id}: {e}")

    return report
