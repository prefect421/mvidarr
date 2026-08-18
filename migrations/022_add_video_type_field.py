#!/usr/bin/env python3
"""
Migration 022: Add video_type to videos table
Date: January 30, 2026
Issue: #191 - Per-artist video type filtering for autodownload
Version: v0.11.7

This migration adds the video_type column to the videos table to store
the classification of each video (official, live, lyric, etc.).

This is required for per-artist video type filtering feature.
Video types are auto-detected from titles and metadata during discovery.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.022")


def upgrade(connection):
    """Add video_type column to videos table"""
    try:
        logger.info("Starting migration 022: Add video_type to videos table")

        # Check if column already exists
        result = connection.execute(text("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'videos'
              AND COLUMN_NAME = 'video_type'
            """)).fetchone()

        if result[0] > 0:
            logger.info("video_type column already exists - skipping migration")
            return True

        # Add video_type column
        logger.info("Adding video_type column to videos table...")
        connection.execute(text("""
            ALTER TABLE videos
            ADD COLUMN video_type VARCHAR(50) NULL
            COMMENT 'Video type classification: official_music_video, live_performance, lyric_video, etc.'
            """))

        # Add index for video_type for efficient filtering
        logger.info("Creating index on video_type column...")
        connection.execute(text("""
            CREATE INDEX idx_video_type ON videos(video_type)
            """))

        logger.info("✅ Successfully added video_type column and index to videos table")
        logger.info("   - Existing videos will have NULL type (unclassified)")
        logger.info("   - New videos will be auto-classified during discovery")

        return True

    except Exception as e:
        logger.error(f"Migration 022 failed: {e}", exc_info=True)
        raise


def downgrade(connection):
    """Remove video_type column from videos table"""
    try:
        logger.info("Starting migration 022 downgrade: Remove video_type from videos")

        # Check if column exists
        result = connection.execute(text("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'videos'
              AND COLUMN_NAME = 'video_type'
            """)).fetchone()

        if result[0] == 0:
            logger.info("video_type column does not exist - skipping downgrade")
            return True

        # Drop index first
        logger.info("Dropping index on video_type column...")
        try:
            connection.execute(text("""
                DROP INDEX idx_video_type ON videos
                """))
        except Exception:
            logger.warning("Index idx_video_type may not exist, continuing...")

        # Drop video_type column
        logger.info("Removing video_type column from videos table...")
        connection.execute(text("""
            ALTER TABLE videos
            DROP COLUMN video_type
            """))

        logger.info("✅ Successfully removed video_type column from videos table")

        return True

    except Exception as e:
        logger.error(f"Migration 022 downgrade failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    """Allow running migration directly for testing"""
    from src.database.connection import get_db_connection

    print("Running migration 022...")
    with get_db_connection() as conn:
        if upgrade(conn):
            print("Migration 022 completed successfully")
        else:
            print("Migration 022 failed")
