#!/usr/bin/env python3
"""
Fix Stuck Downloads - Reset orphaned videos in DOWNLOADING status
This script finds videos stuck in DOWNLOADING status with no corresponding Download record
and resets them so they can be properly queued for download.
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.connection import get_db
from src.database.models import Download, Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fix_stuck_downloads")


def fix_stuck_downloads():
    """Find and fix videos stuck in DOWNLOADING status without Download records"""
    try:
        with get_db() as session:
            # Find videos in DOWNLOADING status
            downloading_videos = (
                session.query(Video)
                .filter(Video.status == "DOWNLOADING")
                .all()
            )

            logger.info(f"Found {len(downloading_videos)} videos in DOWNLOADING status")

            if not downloading_videos:
                logger.info("No stuck downloads found!")
                return {"success": True, "fixed_count": 0, "message": "No stuck downloads"}

            fixed_count = 0
            orphaned_count = 0

            for video in downloading_videos:
                # Check if there's a corresponding Download record
                download_record = (
                    session.query(Download)
                    .filter(Download.video_id == video.id)
                    .filter(Download.status.in_(["pending", "queued", "downloading"]))
                    .first()
                )

                if not download_record:
                    # Orphaned video - no Download record exists
                    logger.info(
                        f"Orphaned video {video.id}: {video.title} (status: {video.status})"
                    )
                    orphaned_count += 1

                    # Create a new Download record if video has a YouTube URL
                    if video.youtube_url and video.artist_id:
                        try:
                            new_download = Download(
                                video_id=video.id,
                                artist_id=video.artist_id,
                                original_url=video.youtube_url,
                                title=video.title,
                                status="queued",
                                progress=0,
                                created_at=video.created_at,
                            )
                            session.add(new_download)

                            # Reset video status to WANTED so it can be re-queued
                            video.status = "WANTED"

                            logger.info(
                                f"✅ Created Download record and reset video {video.id} to WANTED status"
                            )
                            fixed_count += 1
                        except Exception as e:
                            logger.error(
                                f"Failed to create Download record for video {video.id}: {e}"
                            )
                    else:
                        logger.warning(
                            f"Cannot create Download record for video {video.id} - missing URL or artist_id"
                        )
                        # Still reset to WANTED status
                        video.status = "WANTED"
                        fixed_count += 1

            # Commit all changes
            session.commit()

            logger.info(
                f"✅ Fixed {fixed_count} orphaned downloads out of {orphaned_count} found"
            )

            return {
                "success": True,
                "total_downloading": len(downloading_videos),
                "orphaned_count": orphaned_count,
                "fixed_count": fixed_count,
                "message": f"Fixed {fixed_count} orphaned videos",
            }

    except Exception as e:
        logger.error(f"Error fixing stuck downloads: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("=" * 80)
    print("Fixing Stuck Downloads")
    print("=" * 80)

    result = fix_stuck_downloads()

    print(f"\nResult: {result}")

    if result["success"]:
        print(f"\n✅ Successfully fixed {result.get('fixed_count', 0)} stuck downloads")
        print(f"   Total videos in DOWNLOADING status: {result.get('total_downloading', 0)}")
        print(f"   Orphaned videos (no Download record): {result.get('orphaned_count', 0)}")
        print("\nVideos have been reset to WANTED status and Download records created.")
        print("The background job will pick them up within 30 seconds.")
    else:
        print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
