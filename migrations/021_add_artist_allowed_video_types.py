#!/usr/bin/env python3
"""
Migration 021: Add allowed_video_types to artists table
Date: January 30, 2026
Issue: #191 - Per-artist video type filtering for autodownload
Version: v0.11.7

This migration adds the allowed_video_types JSON column to the artists table
to support per-artist filtering of video types during auto-download.

Supported video types:
- official_music_video: Official music videos
- live_performance: Live performances/concerts
- lyric_video: Lyric videos
- acoustic_version: Acoustic versions
- remix_version: Remixes
- cover_version: Cover versions
- music_documentary: Music documentaries
- concert_footage: Concert footage

NULL value means no filtering (download all types)
Empty array [] means download nothing
Array with types means download only those types
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.021")


def upgrade(connection):
    """Add allowed_video_types column to artists table"""
    try:
        logger.info("Starting migration 021: Add allowed_video_types to artists table")

        # Check if column already exists
        result = connection.execute(
            text(
                """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'artists'
              AND COLUMN_NAME = 'allowed_video_types'
            """
            )
        ).fetchone()

        if result[0] > 0:
            logger.info(
                "allowed_video_types column already exists - skipping migration"
            )
            return True

        # Add allowed_video_types column
        logger.info("Adding allowed_video_types column to artists table...")
        connection.execute(
            text(
                """
            ALTER TABLE artists
            ADD COLUMN allowed_video_types JSON NULL
            COMMENT 'List of allowed video types for auto-download filtering (Issue #191)'
            """
            )
        )

        logger.info("✅ Successfully added allowed_video_types column to artists table")
        logger.info("   - NULL = no filtering (download all types)")
        logger.info("   - [] = download nothing")
        logger.info("   - [types] = download only specified types")

        return True

    except Exception as e:
        logger.error(f"Migration 021 failed: {e}", exc_info=True)
        raise


def downgrade(connection):
    """Remove allowed_video_types column from artists table"""
    try:
        logger.info(
            "Starting migration 021 downgrade: Remove allowed_video_types from artists"
        )

        # Check if column exists before dropping
        result = connection.execute(
            text(
                """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'artists'
              AND COLUMN_NAME = 'allowed_video_types'
            """
            )
        ).fetchone()

        if result[0] == 0:
            logger.info(
                "allowed_video_types column does not exist - skipping downgrade"
            )
            return True

        # Drop allowed_video_types column
        logger.info("Removing allowed_video_types column from artists table...")
        connection.execute(
            text(
                """
            ALTER TABLE artists
            DROP COLUMN allowed_video_types
            """
            )
        )

        logger.info(
            "✅ Successfully removed allowed_video_types column from artists table"
        )

        return True

    except Exception as e:
        logger.error(f"Migration 021 downgrade failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    """Allow running migration directly for testing"""
    from src.database.connection import get_db_connection

    print("Running migration 021...")
    with get_db_connection() as conn:
        if upgrade(conn):
            print("Migration 021 completed successfully")
        else:
            print("Migration 021 failed")
