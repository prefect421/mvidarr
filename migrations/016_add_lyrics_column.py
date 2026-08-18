#!/usr/bin/env python3
"""
Migration: Add lyrics column to videos table
Version: 016
Date: 2025-10-08
Description: Adds lyrics TEXT column to videos table for song lyrics storage
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_016")


def upgrade(connection):
    """Add lyrics column to videos table"""
    try:
        logger.info("Starting migration 016: Adding lyrics column to videos table")

        # Check if column already exists
        result = connection.execute(text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'videos'
                AND COLUMN_NAME = 'lyrics'
            """))

        if result.scalar() > 0:
            logger.info("Lyrics column already exists - skipping migration")
            return

        # Add lyrics column
        connection.execute(text("""
                ALTER TABLE videos
                ADD COLUMN lyrics TEXT NULL
                COMMENT 'Song lyrics'
                AFTER last_enriched
            """))

        logger.info("Migration 016 completed successfully: lyrics column added")

    except Exception as e:
        logger.error(f"Migration 016 failed: {e}")
        raise


def downgrade(connection):
    """Remove lyrics column from videos table"""
    try:
        logger.info("Starting downgrade of migration 016")

        # Check if column exists
        result = connection.execute(text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'videos'
                AND COLUMN_NAME = 'lyrics'
            """))

        if result.scalar() == 0:
            logger.info("Lyrics column doesn't exist - skipping downgrade")
            return

        # Remove lyrics column
        connection.execute(text("""
                ALTER TABLE videos
                DROP COLUMN lyrics
            """))

        logger.info("Migration 016 downgrade completed successfully")

    except Exception as e:
        logger.error(f"Migration 016 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add Lyrics Column Migration")
    parser.add_argument(
        "--downgrade", action="store_true", help="Run downgrade instead of upgrade"
    )

    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
