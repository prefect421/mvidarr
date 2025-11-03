#!/usr/bin/env python3
"""
Script to backfill year data for videos missing this information.

This script extracts year information from:
1. YouTube upload_date in video_metadata (format: YYYYMMDD)
2. IMVDb year field in imvdb_metadata
3. Release_date field if available

Usage:
    python scripts/backfill_video_years.py [--dry-run] [--video-id VIDEO_ID]

Options:
    --dry-run       Show what would be updated without making changes
    --video-id ID   Only process a specific video ID
    --force         Update even if year already exists
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.connection import get_db
from src.database.models import Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.scripts.backfill_video_years")


def extract_year_from_upload_date(upload_date_str: str) -> int:
    """
    Extract year from YouTube upload_date string.

    Args:
        upload_date_str: Upload date in YYYYMMDD format (e.g., "20240906")

    Returns:
        Year as integer, or None if extraction fails
    """
    try:
        if isinstance(upload_date_str, str) and len(upload_date_str) >= 4:
            year = int(upload_date_str[:4])
            # Sanity check: year should be reasonable
            if 1900 <= year <= datetime.now().year + 1:
                return year
    except (ValueError, TypeError):
        pass
    return None


def extract_year_from_video(video: Video) -> dict:
    """
    Extract year information from video metadata.

    Tries multiple sources in priority order:
    1. IMVDb year (most reliable for music videos)
    2. YouTube upload_date
    3. Release date field

    Args:
        video: Video database model

    Returns:
        Dictionary with 'year' and 'source' keys, or None if no year found
    """
    # Priority 1: IMVDb metadata (most accurate for music video release year)
    if hasattr(video, "imvdb_metadata") and video.imvdb_metadata:
        try:
            imvdb_data = (
                video.imvdb_metadata
                if isinstance(video.imvdb_metadata, dict)
                else json.loads(video.imvdb_metadata)
            )
            if imvdb_data.get("year"):
                year = int(imvdb_data["year"])
                if 1900 <= year <= datetime.now().year + 1:
                    return {"year": year, "source": "imvdb"}
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # Priority 2: YouTube upload_date from video_metadata
    if hasattr(video, "video_metadata") and video.video_metadata:
        try:
            metadata = (
                video.video_metadata
                if isinstance(video.video_metadata, dict)
                else json.loads(video.video_metadata)
            )
            if metadata.get("upload_date"):
                year = extract_year_from_upload_date(metadata["upload_date"])
                if year:
                    return {"year": year, "source": "youtube_upload_date"}
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    # Priority 3: Release date field
    if hasattr(video, "release_date") and video.release_date:
        try:
            if isinstance(video.release_date, datetime):
                return {"year": video.release_date.year, "source": "release_date"}
            elif isinstance(video.release_date, str):
                # Try to parse date string
                parsed_date = datetime.fromisoformat(
                    video.release_date.replace("Z", "+00:00")
                )
                return {"year": parsed_date.year, "source": "release_date"}
        except (ValueError, AttributeError):
            pass

    return None


def backfill_video_year(
    video: Video, force: bool = False, dry_run: bool = False
) -> dict:
    """
    Backfill year for a single video.

    Args:
        video: Video database model
        force: Update even if year already exists
        dry_run: Don't actually update, just report what would happen

    Returns:
        Dictionary with result information
    """
    result = {
        "video_id": video.id,
        "title": video.title,
        "current_year": video.year,
        "updated": False,
        "new_year": None,
        "source": None,
        "skipped_reason": None,
    }

    # Skip if year already exists and force is not set
    if video.year and not force:
        result["skipped_reason"] = "year_already_exists"
        return result

    # Try to extract year
    year_info = extract_year_from_video(video)

    if not year_info:
        result["skipped_reason"] = "no_year_found"
        return result

    # Update the video
    result["new_year"] = year_info["year"]
    result["source"] = year_info["source"]

    if not dry_run:
        video.year = year_info["year"]
        video.updated_at = datetime.utcnow()
        result["updated"] = True
    else:
        result["updated"] = False  # Would be updated but dry-run
        result["dry_run"] = True

    return result


def backfill_all_videos(
    dry_run: bool = False, force: bool = False, video_id: int = None
):
    """
    Backfill year data for all videos (or a specific video).

    Args:
        dry_run: Show what would be updated without making changes
        force: Update even if year already exists
        video_id: Only process this specific video ID
    """
    logger.info("=" * 80)
    logger.info("Video Year Backfill Script")
    logger.info("=" * 80)

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    if force:
        logger.info("⚠️  FORCE MODE - Will update videos that already have year data")

    stats = {
        "total_processed": 0,
        "updated": 0,
        "skipped_has_year": 0,
        "skipped_no_data": 0,
        "by_source": {},
    }

    try:
        with get_db() as session:
            # Build query
            query = session.query(Video)

            if video_id:
                query = query.filter(Video.id == video_id)
                logger.info(f"📹 Processing single video ID: {video_id}")
            else:
                logger.info("📹 Processing all videos in database")

            videos = query.all()
            total_videos = len(videos)

            if total_videos == 0:
                logger.warning("No videos found to process")
                return

            logger.info(f"Found {total_videos} video(s) to process")
            logger.info("")

            # Process each video
            for idx, video in enumerate(videos, 1):
                stats["total_processed"] += 1

                result = backfill_video_year(video, force=force, dry_run=dry_run)

                # Log progress every 100 videos
                if idx % 100 == 0:
                    logger.info(f"Progress: {idx}/{total_videos} videos processed...")

                # Update statistics
                if result["updated"] or result.get("dry_run"):
                    stats["updated"] += 1
                    source = result["source"]
                    stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

                    logger.info(
                        f"✅ {'[DRY-RUN] ' if dry_run else ''}Updated video {result['video_id']}: "
                        f"{result['title'][:60]} -> Year: {result['new_year']} "
                        f"(from {source})"
                    )
                elif result["skipped_reason"] == "year_already_exists":
                    stats["skipped_has_year"] += 1
                elif result["skipped_reason"] == "no_year_found":
                    stats["skipped_no_data"] += 1
                    logger.debug(
                        f"⚠️  No year data found for video {result['video_id']}: "
                        f"{result['title'][:60]}"
                    )

            # Commit changes if not dry run
            if not dry_run:
                session.commit()
                logger.info("")
                logger.info("✅ Changes committed to database")
            else:
                logger.info("")
                logger.info("🔍 Dry run complete - no changes made")

    except Exception as e:
        logger.error(f"Error during backfill: {e}", exc_info=True)
        raise

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total videos processed:     {stats['total_processed']}")
    logger.info(f"Videos updated:             {stats['updated']}")
    logger.info(f"Videos skipped (has year):  {stats['skipped_has_year']}")
    logger.info(f"Videos skipped (no data):   {stats['skipped_no_data']}")
    logger.info("")

    if stats["by_source"]:
        logger.info("Updates by source:")
        for source, count in sorted(stats["by_source"].items()):
            logger.info(f"  - {source}: {count}")

    logger.info("=" * 80)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Backfill year data for videos missing this information",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be updated
  python scripts/backfill_video_years.py --dry-run

  # Update all videos missing year data
  python scripts/backfill_video_years.py

  # Update a specific video
  python scripts/backfill_video_years.py --video-id 703

  # Force update all videos (even if they have year data)
  python scripts/backfill_video_years.py --force
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )

    parser.add_argument("--video-id", type=int, help="Only process a specific video ID")

    parser.add_argument(
        "--force", action="store_true", help="Update even if year already exists"
    )

    args = parser.parse_args()

    try:
        backfill_all_videos(
            dry_run=args.dry_run, force=args.force, video_id=args.video_id
        )
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\n❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
