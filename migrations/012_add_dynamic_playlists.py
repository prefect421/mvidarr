#!/usr/bin/env python3
"""
Migration 012: Add Dynamic Playlists Support
Date: August 23, 2025
Issue: #109 - Dynamic Playlists
Purpose: Add fields to support dynamic playlists with filter criteria and automatic updating
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.012")


def upgrade(connection):
    """Add dynamic playlist fields to playlists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 012: Add dynamic playlist fields")

            # Check if columns already exist (idempotency)
            result = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'playlists'
                AND column_name = 'playlist_type'
                AND table_schema = DATABASE()
            """))

            playlist_type_exists = result.scalar() > 0

            if not playlist_type_exists:
                logger.info("Adding dynamic playlist columns to playlists table...")

                # Add playlist_type column with ENUM
                connection.execute(text("""
                    ALTER TABLE playlists
                    ADD COLUMN playlist_type ENUM('STATIC', 'DYNAMIC')
                    DEFAULT 'STATIC' NOT NULL
                """))

                # Add filter_criteria JSON column
                connection.execute(text("""
                    ALTER TABLE playlists
                    ADD COLUMN filter_criteria JSON DEFAULT NULL
                """))

                # Add auto_update column
                connection.execute(text("""
                    ALTER TABLE playlists
                    ADD COLUMN auto_update BOOLEAN DEFAULT TRUE NOT NULL
                """))

                # Add last_updated timestamp column
                connection.execute(text("""
                    ALTER TABLE playlists
                    ADD COLUMN last_updated DATETIME DEFAULT NULL
                """))

                logger.info("✅ Dynamic playlist columns added successfully")
            else:
                logger.info(
                    "✅ Dynamic playlist columns already exist - skipping column creation"
                )

            # Create indexes (check for existence first)
            indexes_to_create = [
                (
                    "idx_playlist_type",
                    "CREATE INDEX idx_playlist_type ON playlists (playlist_type)",
                ),
                (
                    "idx_playlist_auto_update",
                    "CREATE INDEX idx_playlist_auto_update ON playlists (auto_update)",
                ),
                (
                    "idx_playlist_last_updated",
                    "CREATE INDEX idx_playlist_last_updated ON playlists (last_updated)",
                ),
                (
                    "idx_playlist_type_auto",
                    "CREATE INDEX idx_playlist_type_auto ON playlists (playlist_type, auto_update)",
                ),
            ]

            for index_name, create_sql in indexes_to_create:
                # Check if index exists
                result = connection.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM information_schema.statistics
                    WHERE table_name = 'playlists'
                    AND index_name = :index_name
                    AND table_schema = DATABASE()
                """),
                    {"index_name": index_name},
                )

                index_exists = result.scalar() > 0

                if not index_exists:
                    logger.info(f"Creating index {index_name}...")
                    connection.execute(text(create_sql))
                    logger.info(f"✅ Index {index_name} created successfully")
                else:
                    logger.info(f"✅ Index {index_name} already exists")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 012 completed successfully")

    except Exception as e:
        logger.error(f"Migration 012 failed: {e}")
        raise


def downgrade(connection):
    """Remove dynamic playlist fields from playlists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration 012: Removing dynamic playlist fields")

            # Drop indexes
            indexes_to_drop = [
                "idx_playlist_type_auto",
                "idx_playlist_last_updated",
                "idx_playlist_auto_update",
                "idx_playlist_type",
            ]

            for index_name in indexes_to_drop:
                try:
                    connection.execute(text(f"DROP INDEX {index_name} ON playlists"))
                    logger.info(f"Dropped index {index_name}")
                except Exception as e:
                    logger.warning(f"Could not drop index {index_name}: {e}")

            # Drop columns
            columns_to_drop = [
                "last_updated",
                "auto_update",
                "filter_criteria",
                "playlist_type",
            ]

            for column_name in columns_to_drop:
                try:
                    connection.execute(
                        text(f"ALTER TABLE playlists DROP COLUMN {column_name}")
                    )
                    logger.info(f"Dropped column {column_name}")
                except Exception as e:
                    logger.warning(f"Could not drop column {column_name}: {e}")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 012 downgrade completed")

    except Exception as e:
        logger.error(f"Migration 012 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
