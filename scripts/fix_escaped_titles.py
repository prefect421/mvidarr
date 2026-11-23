#!/usr/bin/env python3
"""Repair HTML-escaped video titles and the files named after them (#612).

Videos added before v1.1.8 may have titles such as ``Where&#39;s our love`` or
``A &amp; B`` (the YouTube Data API returns HTML-escaped text), and downloaded
files and sidecars (.info.json, subtitles) carry the same escaped names.

Dry run by default. Nothing changes until you pass --apply.

    docker exec <container> python3 scripts/fix_escaped_titles.py
    docker exec <container> python3 scripts/fix_escaped_titles.py --apply

Back up the database first if the library matters to you.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_db  # noqa: E402
from src.services.title_unescape_service import cleanup_escaped_titles  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: dry run)"
    )
    args = parser.parse_args()

    with get_db() as session:
        report = cleanup_escaped_titles(session, apply=args.apply)

    mode = "APPLIED" if args.apply else "DRY RUN (no changes made)"
    print(f"== {mode} ==")
    for d in report["details"]:
        new = d.get("new_title")
        print(f"- video {d['video_id']}: {d['title']!r}" + (f" -> {new!r}" if new else ""))
        for r in d.get("renames", []):
            print(f"    rename: {r}")
    print(
        f"\nTitles to fix: {report['titles_to_fix']}   "
        f"Videos with files to rename: {report['files_to_rename']}"
    )
    if args.apply:
        print(f"Videos updated: {report['renamed']}")
    for c in report["conflicts"]:
        print(f"CONFLICT (files left as-is): {c}")
    for e in report["errors"]:
        print(f"ERROR: {e}")
    if not args.apply and (report["titles_to_fix"] or report["files_to_rename"]):
        print("\nRe-run with --apply to make these changes.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
