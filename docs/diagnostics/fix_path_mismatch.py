#!/usr/bin/env python3
"""
Fix video indexing path mismatch
Removes stale Download records with old path pattern (/music_videos/)
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.database.connection import get_db
from src.database.models import Download, Video

def fix_path_mismatch(dry_run=True):
    """
    Remove stale Download records with old path pattern

    Args:
        dry_run: If True, only show what would be deleted without actually deleting
    """

    print("=" * 80)
    print("MVIDARR PATH MISMATCH FIX")
    print("=" * 80)

    if dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made")
        print("Run with --execute to actually delete records\n")
    else:
        print("\n⚠️  EXECUTE MODE - Records will be deleted!")
        print("=" * 80)

    with get_db() as session:
        # Find all Download records with old path pattern
        old_path_downloads = session.query(Download).filter(
            Download.file_path.like('%/music_videos/%')
        ).all()

        total_old = len(old_path_downloads)
        print(f"\nFound {total_old} Download records with OLD path pattern (/music_videos/)")

        if total_old == 0:
            print("✅ No stale records found - nothing to do!")
            return

        # Show some examples
        print(f"\nExample records to be deleted:")
        for i, download in enumerate(old_path_downloads[:10], 1):
            print(f"  {i}. ID: {download.id}, Path: {download.file_path}")

        if total_old > 10:
            print(f"  ... and {total_old - 10} more")

        if not dry_run:
            # Get user confirmation
            print(f"\n⚠️  About to delete {total_old} Download records")
            response = input("Are you sure? Type 'YES' to confirm: ")

            if response != "YES":
                print("❌ Aborted - no changes made")
                return

            # Get associated video IDs before deleting downloads
            video_ids = set(d.video_id for d in old_path_downloads if d.video_id)

            # Delete the Download records
            deleted_count = 0
            for download in old_path_downloads:
                session.delete(download)
                deleted_count += 1

            # Check for orphaned videos (videos with no downloads)
            orphaned_videos = []
            for video_id in video_ids:
                remaining_downloads = session.query(Download).filter(
                    Download.video_id == video_id
                ).count()

                if remaining_downloads == 0:
                    video = session.query(Video).filter(Video.id == video_id).first()
                    if video:
                        orphaned_videos.append(video)

            # Delete orphaned videos
            for video in orphaned_videos:
                session.delete(video)

            session.commit()

            print(f"\n✅ Successfully deleted:")
            print(f"   - {deleted_count} Download records")
            print(f"   - {len(orphaned_videos)} orphaned Video records")
            print(f"\nYou can now run video indexing to re-index the files from the correct path")

        else:
            print(f"\n💡 To execute the deletion, run:")
            print(f"   python3 {__file__} --execute")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    try:
        fix_path_mismatch(dry_run=dry_run)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
