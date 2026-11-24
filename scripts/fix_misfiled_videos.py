#!/usr/bin/env python3
"""Move downloads that landed in the wrong folder into their artist's folder (#629).

Before v1.1.9, videos imported from a YouTube search were saved into a folder named
after the uploading CHANNEL ("The Prodigy - Topic", label names, "Unknown Artist")
rather than the artist they are assigned to. This moves the media file and its
sidecars (.info.json, subtitles) into <library>/<artist>/ and updates the database.
Nothing is ever overwritten; any failure restores the files.

Dry run by default. Nothing changes until you pass --apply.

    docker exec <container> python3 scripts/fix_misfiled_videos.py
    docker exec <container> python3 scripts/fix_misfiled_videos.py --apply

Back up the database first if the library matters to you.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_db  # noqa: E402
from src.services.misfiled_videos_service import repair_misfiled_videos  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: dry run)"
    )
    args = parser.parse_args()
    with get_db() as session:
        report = repair_misfiled_videos(session, apply=args.apply)
    print(f"== {'APPLIED' if args.apply else 'DRY RUN (no changes made)'} ==")
    for d in report["details"]:
        print(
            f"- video {d['video_id']} ({d['artist']}): {d['from']}/ -> {d['to']}/   {d['file']}"
        )
    print(f"\nChecked: {report['checked']}   Misfiled: {report['to_move']}")
    if args.apply:
        print(f"Moved: {report['moved']}")
    for c in report["conflicts"]:
        print(f"CONFLICT: {c}")
    for e in report["errors"]:
        print(f"ERROR: {e}")
    if not args.apply and report["to_move"]:
        print("\nRe-run with --apply to move them.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
