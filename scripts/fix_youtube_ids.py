#!/usr/bin/env python3
"""Restore YouTube IDs that metadata enrichment overwrote (#634).

Before v1.1.9, "Refresh All Metadata" with force refresh could replace a
downloaded video's YouTube ID with a different upload found by fuzzy title
search. The true ID is still in each download's ``.info.json``; this puts it
back (and fixes ``youtube_url``).

Only videos whose stored ID *differs* from their file's are changed. Videos with
no ID at all are left alone unless you pass --fill-missing.

Dry run by default. Nothing changes until you pass --apply. Videos whose file
carries an ID owned by an unrelated video, or two videos whose files carry the
same ID (usually a duplicate download), are reported and left alone.

    docker exec <container> python3 scripts/fix_youtube_ids.py
    docker exec <container> python3 scripts/fix_youtube_ids.py --apply

Back up the database first if the library matters to you.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_db  # noqa: E402
from src.services.youtube_id_repair_service import repair_youtube_ids  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: dry run)"
    )
    parser.add_argument(
        "--fill-missing",
        action="store_true",
        help="also fill videos that have NO youtube_id from their file's .info.json",
    )
    args = parser.parse_args()

    with get_db() as session:
        report = repair_youtube_ids(
            session, apply=args.apply, fill_missing=args.fill_missing
        )

    print(f"== {'APPLIED' if args.apply else 'DRY RUN (no changes made)'} ==")
    for d in report["details"]:
        print(f"- video {d['video_id']}: {d['old']} -> {d['new']}   ({d['title']})")
    print(
        f"\nChecked: {report['checked']}   To fix: {report['to_fix']}   "
        f"Without .info.json: {report['no_info_json']}"
    )
    if report["missing_not_filled"]:
        print(
            f"{report['missing_not_filled']} videos have no youtube_id at all "
            f"(not touched; use --fill-missing to fill them)"
        )
    if args.apply:
        print(f"Fixed: {report['fixed']}")
    for c in report["conflicts"]:
        print(f"CONFLICT: {c}")
    for e in report["errors"]:
        print(f"ERROR: {e}")
    if not args.apply and report["to_fix"]:
        print("\nRe-run with --apply to make these changes.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
