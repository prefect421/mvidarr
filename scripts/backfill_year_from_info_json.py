#!/usr/bin/env python3
"""
Backfill year data from .info.json files for videos missing year information
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import get_db
from src.database.models import Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.backfill_year_info")

def backfill_year_from_info_files():
    """Extract year from .info.json files for videos without year"""

    with get_db() as session:
        # Find videos without year
        videos_without_year = session.query(Video).filter(
            Video.year.is_(None),
            Video.local_path.isnot(None)
        ).all()

        total = len(videos_without_year)
        logger.info(f"Found {total} videos without year data")

        updated_count = 0
        failed_count = 0
        no_info_file = 0

        for video in videos_without_year:
            try:
                # Handle invalid paths
                if not video.local_path or '\\' in video.local_path:
                    no_info_file += 1
                    logger.debug(f"Invalid path for video {video.id}: {video.local_path}")
                    continue

                video_path = Path(video.local_path)

                if not video_path.exists():
                    no_info_file += 1
                    continue

                # Look for .info.json file
                info_json_path = video_path.with_suffix('.info.json')

                if info_json_path.exists():
                    with open(info_json_path, 'r') as f:
                        info_data = json.load(f)

                    upload_date = info_data.get('upload_date')

                    if upload_date and isinstance(upload_date, str) and len(upload_date) >= 4:
                        year = int(upload_date[:4])
                        video.year = year
                        updated_count += 1

                        if updated_count % 10 == 0:
                            logger.info(f"Progress: {updated_count}/{total} videos updated")
                            session.commit()
                else:
                    no_info_file += 1

            except (ValueError, TypeError, json.JSONDecodeError) as e:
                failed_count += 1
                logger.debug(f"Could not extract year from video {video.id}: {e}")
                continue

        # Final commit
        session.commit()

        logger.info(f"\nBackfill complete!")
        logger.info(f"  - Updated: {updated_count} videos")
        logger.info(f"  - No .info.json file: {no_info_file} videos")
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
        backfill_year_from_info_files()
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)
