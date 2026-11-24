#!/usr/bin/env python3
"""Remux existing .mkv downloads to .mp4 without re-encoding (#633).

Before v1.1.9, yt-dlp merged H.264+Opus (and VP9+AAC) into MKV, which the UI
flags as needing transcoding. New downloads are MP4 already; this converts the
old ones with ``ffmpeg -c copy`` (lossless, fast, no quality change).

Each file is written to ``<name>.mp4.part``, verified (video stream present,
duration matches) and only then moved into place; the database is updated before
the original MKV is deleted. Any failure leaves the original and the database
untouched. Dry run by default.

    docker exec <container> python3 scripts/remux_mkv_to_mp4.py
    docker exec <container> python3 scripts/remux_mkv_to_mp4.py --apply
    docker exec <container> python3 scripts/remux_mkv_to_mp4.py --apply --keep-original

--keep-original leaves the .mkv beside the new .mp4 (uses twice the space, and
a library re-index may then see both). Back up the database first.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_db  # noqa: E402
from src.services.mkv_remux_service import remux_mkv_to_mp4  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true", help="make the changes (default: dry run)"
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="do not delete the .mkv after a verified remux",
    )
    args = parser.parse_args()

    with get_db() as session:
        report = remux_mkv_to_mp4(
            session, apply=args.apply, keep_original=args.keep_original
        )

    print(f"== {'APPLIED' if args.apply else 'DRY RUN (no changes made)'} ==")
    for d in report["details"]:
        print(f"- video {d['video_id']}: {d['from']} -> {d['to']}")
    print(f"\nMKV files found: {report['candidates']}")
    if args.apply:
        print(f"Remuxed: {report['remuxed']}")
    for c in report["conflicts"]:
        print(f"CONFLICT: {c}")
    for e in report["errors"]:
        print(f"ERROR: {e}")
    if not args.apply and report["candidates"]:
        print("\nRe-run with --apply to convert them.")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
