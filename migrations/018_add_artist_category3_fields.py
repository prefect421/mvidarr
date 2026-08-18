#!/usr/bin/env python3
"""
Migration 018: Add Category 3 Artist Fields
Date: December 9, 2025
Issue: #174 - Add fields that exist in frontend but not in API or database

This migration adds Category 3 fields from Issue #174:
- overview (TEXT) - Artist overview/summary
- disbanded_year (INT) - Year the band disbanded
- origin_country (VARCHAR) - Country of origin
- spotify_url (VARCHAR) - Spotify profile URL
- youtube_url (VARCHAR) - YouTube channel URL
- apple_music_url (VARCHAR) - Apple Music profile URL
- twitter_url (VARCHAR) - Twitter/X profile URL
- facebook_url (VARCHAR) - Facebook page URL
- instagram_url (VARCHAR) - Instagram profile URL
- quality_profile (VARCHAR) - Quality profile for downloads
- priority (INT) - Artist priority for downloads
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.018")


def upgrade(connection):
    """Add Category 3 fields to artists table"""
    try:
        logger.info("Starting migration 018: Add Category 3 artist fields")

        fields_to_add = [
            ("overview", "TEXT", "Artist overview/summary"),
            ("disbanded_year", "INT", "Year the band disbanded"),
            ("origin_country", "VARCHAR(100)", "Country of origin"),
            ("spotify_url", "VARCHAR(500)", "Spotify profile URL"),
            ("youtube_url", "VARCHAR(500)", "YouTube channel URL"),
            ("apple_music_url", "VARCHAR(500)", "Apple Music profile URL"),
            ("twitter_url", "VARCHAR(500)", "Twitter/X profile URL"),
            ("facebook_url", "VARCHAR(500)", "Facebook page URL"),
            ("instagram_url", "VARCHAR(500)", "Instagram profile URL"),
            ("quality_profile", "VARCHAR(50)", "Quality profile for downloads"),
            ("priority", "INT", "Artist priority for downloads"),
        ]

        for field_name, field_type, field_comment in fields_to_add:
            # Check if column already exists (idempotency)
            result = connection.execute(
                text(
                    f"""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'artists'
                AND column_name = '{field_name}'
                AND table_schema = DATABASE()
            """
                )
            )

            field_exists = result.scalar() > 0

            if not field_exists:
                logger.info(f"Adding {field_name} column to artists table...")

                # Add column with appropriate type and comment
                connection.execute(
                    text(
                        f"""
                    ALTER TABLE artists
                    ADD COLUMN {field_name} {field_type} DEFAULT NULL
                    COMMENT '{field_comment}'
                """
                    )
                )

                logger.info(f"✅ {field_name} column added successfully")
            else:
                logger.info(f"✅ {field_name} column already exists - skipping")

        # Add indexes for commonly queried/filtered fields
        logger.info("Adding indexes for new fields...")

        indexes_to_add = [
            ("idx_artist_origin_country", "origin_country"),
            ("idx_artist_disbanded_year", "disbanded_year"),
            ("idx_artist_quality_profile", "quality_profile"),
            ("idx_artist_priority", "priority"),
        ]

        for index_name, column_name in indexes_to_add:
            # Check if index already exists
            result = connection.execute(
                text(
                    f"""
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_name = 'artists'
                AND index_name = '{index_name}'
                AND table_schema = DATABASE()
            """
                )
            )

            index_exists = result.scalar() > 0

            if not index_exists:
                logger.info(f"Creating index {index_name}...")
                connection.execute(
                    text(f"CREATE INDEX {index_name} ON artists ({column_name})")
                )
                logger.info(f"✅ Index {index_name} created successfully")
            else:
                logger.info(f"✅ Index {index_name} already exists - skipping")

        logger.info("✅ Migration 018 completed successfully")

    except Exception as e:
        logger.error(f"Migration 018 failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


def downgrade(connection):
    """
    Rollback migration - remove Category 3 fields
    """
    try:
        logger.info("Rolling back migration 018: Removing Category 3 artist fields")

        # Drop indexes first
        indexes_to_drop = [
            "idx_artist_origin_country",
            "idx_artist_disbanded_year",
            "idx_artist_quality_profile",
            "idx_artist_priority",
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
            "overview",
            "disbanded_year",
            "origin_country",
            "spotify_url",
            "youtube_url",
            "apple_music_url",
            "twitter_url",
            "facebook_url",
            "instagram_url",
            "quality_profile",
            "priority",
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

        logger.info("✅ Migration 018 rollback completed successfully")

    except Exception as e:
        logger.error(f"Migration 018 rollback failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    import argparse

    from src.database.connection import engine

    parser = argparse.ArgumentParser(
        description="Migration 018: Add Category 3 artist fields"
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
