#!/usr/bin/env python3
"""
Backfill year data from video descriptions and tags in .info.json files
This is a fallback for videos missing year information
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.as_posix())

from src.database.connection import get_db
from src.database.models import Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.backfill_year_descriptions")


def extract_year_candidates(text):
    """Extract potential years from text (1950-2030)"""
    if not text:
        return []

    # Find all 4-digit years
    years = re.findall(r'\b(19[5-9]\d|20[0-3]\d)\b', str(text))
    return [int(y) for y in years]


def extract_year_from_copyright(text):
    """Extract year from copyright notice (e.g., '(C) 2005')"""
    if not text:
        return None

    match = re.search(r'\(C\)\s*(\d{4})', text, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        if 1950 <= year <= 2030:
            return year

    # Try ℗ symbol
    match = re.search(r'℗\s*(\d{4})', text)
    if match:
        year = int(match.group(1))
        if 1950 <= year <= 2030:
            return year

    return None


def extract_year_from_album_context(text):
    """Extract year from album release context"""
    if not text:
        return None

    # Look for "album released", "Released @", etc.
    patterns = [
        r'[Rr]eleased?\s+[@:in]*\s*\w*\s*(\d{4})',
        r'[Aa]lbum.*?(\d{4})',
        r'from.*?(\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year = int(match.group(1))
            if 1950 <= year <= 2030:
                return year

    return None


def get_best_year_estimate(info_data, video_title):
    """
    Intelligently extract the most likely year from .info.json data
    Priority:
    1. Copyright notice (most reliable)
    2. Album release context
    3. Description years (prefer later years in description)
    4. Tags (least reliable)
    """
    description = info_data.get('description', '')
    tags = info_data.get('tags', [])
    title = info_data.get('title', '')

    # Priority 1: Copyright notice
    year = extract_year_from_copyright(description)
    if year:
        return year, 'copyright'

    # Priority 2: Album release context
    year = extract_year_from_album_context(description)
    if year:
        return year, 'album_context'

    # Priority 3: Description years (prefer recent mentions)
    desc_years = extract_year_candidates(description)
    if desc_years:
        # Prefer the latest year mentioned (usually release year, not band formation)
        return max(desc_years), 'description'

    # Priority 4: Tags
    if tags:
        tag_years = extract_year_candidates(' '.join(tags))
        if tag_years:
            return max(tag_years), 'tags'

    return None, None


def backfill_year_from_descriptions():
    """Extract year from .info.json descriptions and tags"""

    with get_db() as session:
        # Find videos without year
        videos_without_year = session.query(Video).filter(
            Video.year.is_(None), Video.local_path.isnot(None)
        ).all()

        total = len(videos_without_year)
        logger.info(f"Found {total} videos without year data")

        updated_count = 0
        skipped_invalid_path = 0
        no_info_file = 0
        no_year_found = 0

        for video in videos_without_year:
            try:
                # Skip invalid paths (Windows backslashes)
                if not video.local_path or '\\' in video.local_path:
                    skipped_invalid_path += 1
                    continue

                video_path = Path(video.local_path)

                if not video_path.exists():
                    no_info_file += 1
                    continue

                # Look for .info.json file
                info_json_path = video_path.with_suffix('.info.json')

                if not info_json_path.exists():
                    no_info_file += 1
                    continue

                with open(info_json_path, 'r') as f:
                    info_data = json.load(f)

                year, source = get_best_year_estimate(info_data, video.title)

                if year:
                    video.year = year
                    updated_count += 1
                    logger.info(
                        f"Updated video {video.id} ({video.title[:50]}) -> {year} (from {source})"
                    )

                    if updated_count % 10 == 0:
                        session.commit()
                else:
                    no_year_found += 1

            except (ValueError, TypeError, json.JSONDecodeError) as e:
                logger.debug(f"Could not extract year from video {video.id}: {e}")
                no_year_found += 1
                continue

        # Final commit
        session.commit()

        logger.info(f"\nBackfill complete!")
        logger.info(f"  - Updated: {updated_count} videos")
        logger.info(f"  - No .info.json file: {no_info_file} videos")
        logger.info(f"  - No year found: {no_year_found} videos")
        logger.info(f"  - Skipped (invalid path): {skipped_invalid_path} videos")
        logger.info(f"  - Total processed: {total} videos")

        # Show statistics
        total_videos = session.query(Video).count()
        videos_with_year = (
            session.query(Video).filter(Video.year.isnot(None)).count()
        )
        percentage = (videos_with_year / total_videos * 100) if total_videos > 0 else 0

        logger.info(f"\nFinal statistics:")
        logger.info(f"  - Total videos: {total_videos}")
        logger.info(f"  - Videos with year: {videos_with_year}")
        logger.info(f"  - Percentage: {percentage:.2f}%")

        return updated_count


if __name__ == "__main__":
    try:
        updated = backfill_year_from_descriptions()
        sys.exit(0 if updated >= 0 else 1)
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)
