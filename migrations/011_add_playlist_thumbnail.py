#!/usr/bin/env python3
"""
Migration 011: Add thumbnail_url field to playlists table
Date: 2025
Purpose: Add thumbnail_url column to support playlist thumbnails
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.011")


def upgrade(connection):
    """Add thumbnail_url field to playlists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 011: Add thumbnail_url to playlists")

            # Check if thumbnail_url column already exists (idempotency)
            result = connection.execute(
                text(
                    """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'playlists'
                AND column_name = 'thumbnail_url'
                AND table_schema = DATABASE()
            """
                )
            )

            column_exists = result.scalar() > 0

            if not column_exists:
                logger.info("Adding thumbnail_url column to playlists table...")

                # Add thumbnail_url column
                connection.execute(
                    text("ALTER TABLE playlists ADD COLUMN thumbnail_url VARCHAR(500)")
                )

                logger.info("✅ thumbnail_url column added successfully")
            else:
                logger.info("✅ thumbnail_url column already exists - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 011 completed successfully")

    except Exception as e:
        logger.error(f"Migration 011 failed: {e}")
        raise


def downgrade(connection):
    """Remove thumbnail_url field from playlists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration 011: Removing thumbnail_url column")

            # Check if column exists before dropping
            result = connection.execute(
                text(
                    """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'playlists'
                AND column_name = 'thumbnail_url'
                AND table_schema = DATABASE()
            """
                )
            )

            column_exists = result.scalar() > 0

            if column_exists:
                connection.execute(
                    text("ALTER TABLE playlists DROP COLUMN thumbnail_url")
                )
                logger.info("✅ thumbnail_url column removed successfully")
            else:
                logger.info("✅ thumbnail_url column does not exist - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 011 downgrade completed")

    except Exception as e:
        logger.error(f"Migration 011 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
