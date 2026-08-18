#!/usr/bin/env python3
"""
Migration 010: Add video enrichment fields (album, last_enriched)
Date: August 18, 2025
Purpose: Add missing fields to videos table for metadata enrichment functionality
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_010")


def upgrade(connection):
    """Add video enrichment fields"""
    try:
        # Use the connection provided by the migration system
        # DO NOT use get_db() as it will close the connection
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 010: Adding video enrichment fields")

            # Check if album column exists
            result = connection.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'videos'
                AND column_name = 'album'
            """
                )
            ).fetchone()

            if not result:
                # Add album field for track album information
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos ADD COLUMN album VARCHAR(500)
                """
                    )
                )
                logger.info("Added album column to videos table")
            else:
                logger.info("album column already exists in videos table")

            # Check if last_enriched column exists
            result = connection.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'videos'
                AND column_name = 'last_enriched'
            """
                )
            ).fetchone()

            if not result:
                # Add last_enriched timestamp field
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos ADD COLUMN last_enriched DATETIME
                """
                    )
                )
                logger.info("Added last_enriched column to videos table")
            else:
                logger.info("last_enriched column already exists in videos table")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 010: Successfully added video enrichment fields")

    except Exception as e:
        logger.error(f"❌ Migration 010 failed: {e}")
        raise


def downgrade(connection):
    """Remove video enrichment fields"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info(
                "Starting migration 010 downgrade: Removing video enrichment fields"
            )

            # Remove added columns
            connection.execute(
                text(
                    """
                ALTER TABLE videos DROP COLUMN last_enriched
            """
                )
            )

            connection.execute(
                text(
                    """
                ALTER TABLE videos DROP COLUMN album
            """
                )
            )

            # DO NOT commit here - migration system handles the commit
            logger.info(
                "✅ Migration 010: Successfully removed video enrichment fields"
            )

    except Exception as e:
        logger.error(f"❌ Migration 010 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    # Run migration
    print("Migration 010: Add video enrichment fields")
    print("This migration adds album and last_enriched fields to the videos table")
    upgrade()
