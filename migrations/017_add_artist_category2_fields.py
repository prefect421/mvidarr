#!/usr/bin/env python3
"""
Migration 017: Add Category 2 Artist Fields
Date: December 9, 2025
Issue: #174 - Add fields that exist in API but not in database

This migration adds Category 2 fields from Issue #174:
- biography (TEXT) - Artist biography/description
- formed_year (INT) - Year the artist/band was formed
- location (VARCHAR) - Artist origin location
- website (VARCHAR) - Official artist website
- wikipedia_url (VARCHAR) - Wikipedia article URL
- musicbrainz_id (VARCHAR) - MusicBrainz identifier
- imvdb_slug (VARCHAR) - IMVDb URL slug

Note: sort_name already exists via migration 006
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.017")


def upgrade(connection):
    """Add Category 2 fields to artists table"""
    try:
        logger.info("Starting migration 017: Add Category 2 artist fields")

        fields_to_add = [
            ("biography", "TEXT", "Artist biography/description"),
            ("formed_year", "INT", "Year the artist/band was formed"),
            ("location", "VARCHAR(255)", "Artist origin location"),
            ("website", "VARCHAR(500)", "Official artist website"),
            ("wikipedia_url", "VARCHAR(500)", "Wikipedia article URL"),
            ("musicbrainz_id", "VARCHAR(100)", "MusicBrainz identifier"),
            ("imvdb_slug", "VARCHAR(100)", "IMVDb URL slug"),
        ]

        for field_name, field_type, field_comment in fields_to_add:
            # Check if column already exists (idempotency)
            result = connection.execute(text(f"""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'artists'
                AND column_name = '{field_name}'
                AND table_schema = DATABASE()
            """))

            field_exists = result.scalar() > 0

            if not field_exists:
                logger.info(f"Adding {field_name} column to artists table...")

                # Add column with appropriate type and comment
                connection.execute(text(f"""
                    ALTER TABLE artists
                    ADD COLUMN {field_name} {field_type} DEFAULT NULL
                    COMMENT '{field_comment}'
                """))

                logger.info(f"✅ {field_name} column added successfully")
            else:
                logger.info(f"✅ {field_name} column already exists - skipping")

        # Add indexes for commonly queried fields
        logger.info("Adding indexes for new fields...")

        indexes_to_add = [
            ("idx_artist_formed_year", "formed_year"),
            ("idx_artist_musicbrainz_id", "musicbrainz_id"),
            ("idx_artist_imvdb_slug", "imvdb_slug"),
        ]

        for index_name, column_name in indexes_to_add:
            # Check if index already exists
            result = connection.execute(text(f"""
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_name = 'artists'
                AND index_name = '{index_name}'
                AND table_schema = DATABASE()
            """))

            index_exists = result.scalar() > 0

            if not index_exists:
                logger.info(f"Creating index {index_name}...")
                connection.execute(
                    text(f"CREATE INDEX {index_name} ON artists ({column_name})")
                )
                logger.info(f"✅ Index {index_name} created successfully")
            else:
                logger.info(f"✅ Index {index_name} already exists - skipping")

        logger.info("✅ Migration 017 completed successfully")

    except Exception as e:
        logger.error(f"Migration 017 failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


def downgrade(connection):
    """
    Rollback migration - remove Category 2 fields
    """
    try:
        logger.info("Rolling back migration 017: Removing Category 2 artist fields")

        # Drop indexes first
        indexes_to_drop = [
            "idx_artist_formed_year",
            "idx_artist_musicbrainz_id",
            "idx_artist_imvdb_slug",
        ]

        for index_name in indexes_to_drop:
            try:
                connection.execute(text(f"DROP INDEX {index_name} ON artists"))
                logger.info(f"Dropped index {index_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop index {index_name} (may not exist): {e}"
                )

        # Drop columns
        fields_to_drop = [
            "biography",
            "formed_year",
            "location",
            "website",
            "wikipedia_url",
            "musicbrainz_id",
            "imvdb_slug",
        ]

        for field_name in fields_to_drop:
            try:
                connection.execute(
                    text(f"ALTER TABLE artists DROP COLUMN {field_name}")
                )
                logger.info(f"Dropped column {field_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop column {field_name} (may not exist): {e}"
                )

        logger.info("✅ Migration 017 rollback completed successfully")

    except Exception as e:
        logger.error(f"Migration 017 rollback failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    import argparse

    from src.database.connection import engine

    parser = argparse.ArgumentParser(
        description="Migration 017: Add Category 2 artist fields"
    )
    parser.add_argument(
        "--rollback", action="store_true", help="Rollback the migration"
    )

    args = parser.parse_args()

    with engine.connect() as conn:
        if args.rollback:
            downgrade(conn)
        else:
            upgrade(conn)
        conn.commit()

    sys.exit(0)
