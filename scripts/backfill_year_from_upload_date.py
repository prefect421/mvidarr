#!/usr/bin/env python3
"""
Backfill year data from YouTube upload_date for videos missing year information
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import get_db
from src.database.models import Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.backfill_year")

def backfill_year_from_upload_date():
    """Extract year from upload_date in video_metadata for videos without year"""

    with get_db() as session:
        # Find videos without year but with video_metadata
        videos_without_year = session.query(Video).filter(
            Video.year.is_(None),
            Video.video_metadata.isnot(None)
        ).all()

        total = len(videos_without_year)
        logger.info(f"Found {total} videos without year data that have metadata")

        updated_count = 0
        failed_count = 0

        for video in videos_without_year:
            try:
                upload_date = video.video_metadata.get('upload_date')

                if upload_date and isinstance(upload_date, str) and len(upload_date) >= 4:
                    year = int(upload_date[:4])
                    video.year = year
                    updated_count += 1

                    if updated_count % 10 == 0:
                        logger.info(f"Progress: {updated_count}/{total} videos updated")
                        session.commit()

            except (ValueError, TypeError) as e:
                failed_count += 1
                logger.debug(f"Could not extract year from video {video.id} upload_date: {e}")
                continue

        # Final commit
        session.commit()

        logger.info(f"Backfill complete!")
        logger.info(f"  - Updated: {updated_count} videos")
        logger.info(f"  - Failed: {failed_count} videos")
        logger.info(f"  - Total processed: {total} videos")

        # Show statistics
        total_videos = session.query(Video).count()
        videos_with_year = session.query(Video).filter(Video.year.isnot(None)).count()
        percentage = (videos_with_year / total_videos * 100) if total_videos > 0 else 0

        logger.info(f"\nFinal statistics:")
        logger.info(f"  - Total videos: {total_videos}")
        logger.info(f"  - Videos with year: {videos_with_year}")
        logger.info(f"  - Percentage: {percentage:.2f}%")

if __name__ == "__main__":
    try:
        backfill_year_from_upload_date()
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)
