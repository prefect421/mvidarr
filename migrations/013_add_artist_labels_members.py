#!/usr/bin/env python3
"""
Migration 013: Add Artist Labels and Members Fields
Date: August 28, 2025
Issue: Fix missing keywords, genres, record labels, and band members display issue
Purpose: Add labels and members fields to the artists table
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.013")


def upgrade(connection):
    """Add labels and members fields to artists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 013: Add artist labels and members fields")

            # Check if labels column already exists (idempotency)
            result = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'artists'
                AND column_name = 'labels'
                AND table_schema = DATABASE()
            """))

            labels_exists = result.scalar() > 0

            if not labels_exists:
                logger.info("Adding labels column to artists table...")

                # Add labels column (JSON for record labels)
                connection.execute(text("""
                    ALTER TABLE artists
                    ADD COLUMN labels JSON DEFAULT NULL
                    COMMENT 'Record labels associated with the artist'
                """))

                logger.info("✅ labels column added successfully")
            else:
                logger.info("✅ labels column already exists - skipping")

            # Check if members column already exists (idempotency)
            result = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'artists'
                AND column_name = 'members'
                AND table_schema = DATABASE()
            """))

            members_exists = result.scalar() > 0

            if not members_exists:
                logger.info("Adding members column to artists table...")

                # Add members column (TEXT for band members)
                connection.execute(text("""
                    ALTER TABLE artists
                    ADD COLUMN members TEXT DEFAULT NULL
                    COMMENT 'Band members (stored as text)'
                """))

                logger.info("✅ members column added successfully")
            else:
                logger.info("✅ members column already exists - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 013 completed successfully")

    except Exception as e:
        logger.error(f"Migration 013 failed: {e}")
        raise


def downgrade(connection):
    """Remove labels and members fields from artists table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info(
                "Downgrading migration 013: Removing artist labels and members fields"
            )

            # Drop columns
            columns_to_drop = ["members", "labels"]

            for column_name in columns_to_drop:
                # Check if column exists before dropping
                result = connection.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = 'artists'
                    AND column_name = :column_name
                    AND table_schema = DATABASE()
                """),
                    {"column_name": column_name},
                )

                column_exists = result.scalar() > 0

                if column_exists:
                    connection.execute(
                        text(f"ALTER TABLE artists DROP COLUMN {column_name}")
                    )
                    logger.info(f"✅ {column_name} column removed successfully")
                else:
                    logger.info(f"✅ {column_name} column does not exist - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 013 downgrade completed")

    except Exception as e:
        logger.error(f"Migration 013 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
