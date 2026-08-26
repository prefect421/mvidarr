#!/usr/bin/env python3
"""
Diagnostic script to understand video indexing issues
Checks for path mismatches and duplicate records
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.database.connection import get_db
from src.database.models import Download, Video
from src.services.video_indexing_service import video_indexing_service
from sqlalchemy import func

def diagnose_indexing():
    """Diagnose video indexing issues"""

    print("=" * 80)
    print("MVIDARR VIDEO INDEXING DIAGNOSTIC")
    print("=" * 80)

    with get_db() as session:
        # 1. Check total downloads
        total_downloads = session.query(Download).count()
        print(f"\n1. Total Download records in database: {total_downloads}")

        # 2. Check path patterns
        old_path_count = session.query(Download).filter(
            Download.file_path.like('%/music_videos/%')
        ).count()
        new_path_count = session.query(Download).filter(
            Download.file_path.like('%/musicvideos/%')
        ).count()
        other_path_count = total_downloads - old_path_count - new_path_count

        print(f"\n2. Download records by path pattern:")
        print(f"   - Old path (/music_videos/): {old_path_count}")
        print(f"   - New path (/musicvideos/): {new_path_count}")
        print(f"   - Other paths: {other_path_count}")

        # 3. Sample paths
        if old_path_count > 0:
            print(f"\n3. Sample OLD path records:")
            old_paths = session.query(Download.file_path).filter(
                Download.file_path.like('%/music_videos/%')
            ).limit(5).all()
            for path, in old_paths:
                print(f"   - {path}")

        if new_path_count > 0:
            print(f"\n4. Sample NEW path records:")
            new_paths = session.query(Download.file_path).filter(
                Download.file_path.like('%/musicvideos/%')
            ).limit(5).all()
            for path, in new_paths:
                print(f"   - {path}")

        # 4. Check actual files on disk
        print(f"\n5. Scanning video files on disk...")
        video_files = video_indexing_service.scan_video_files()
        print(f"   - Found {len(video_files)} video files on disk")

        if len(video_files) > 0:
            print(f"\n6. Sample file paths from disk scan:")
            for file_path in video_files[:5]:
                print(f"   - {file_path}")

        # 5. Check for orphaned records
        print(f"\n7. Checking for files that exist on disk but not in database...")
        files_on_disk = set(str(f) for f in video_files)
        files_in_db = set(dl.file_path for dl in session.query(Download.file_path).all())

        missing_from_db = files_on_disk - files_in_db
        print(f"   - Files on disk but not in database: {len(missing_from_db)}")

        if len(missing_from_db) > 0:
            print(f"\n8. Sample files missing from database:")
            for file_path in list(missing_from_db)[:10]:
                print(f"   - {file_path}")

        # 6. Check for stale database records
        stale_records = files_in_db - files_on_disk
        print(f"\n9. Files in database but not on disk (stale records): {len(stale_records)}")

        if len(stale_records) > 0:
            print(f"\n10. Sample stale database records:")
            for file_path in list(stale_records)[:10]:
                print(f"   - {file_path}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

    # Recommendations
    print("\nRECOMMENDATIONS:")
    if old_path_count > 0:
        print(f"\n⚠️  Found {old_path_count} records with OLD path pattern (/music_videos/)")
        print("   These records are likely from before the path fix and should be:")
        print("   a) Deleted if the files don't exist at those paths")
        print("   b) Updated to use the new path pattern (/musicvideos/)")

    if len(missing_from_db) > 0:
        print(f"\n✅ Found {len(missing_from_db)} files on disk not in database")
        print("   These should be indexed in the next indexing run")
        print("   But first, consider cleaning up old records with wrong paths")

if __name__ == "__main__":
    try:
        diagnose_indexing()
    except Exception as e:
        print(f"\n❌ Error running diagnostic: {e}")
        import traceback
        traceback.print_exc()
