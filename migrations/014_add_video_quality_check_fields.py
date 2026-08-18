#!/usr/bin/env python3
"""
Migration 014: Add video quality check fields
Date: 2025
Purpose: Add fields to track available YouTube qualities and last check date
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.014")


def upgrade(connection):
    """Add quality check fields to videos table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 014: Add video quality check fields")

            # Check if available_qualities column already exists (idempotency)
            result = connection.execute(
                text(
                    """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'videos'
                AND column_name = 'available_qualities'
                AND table_schema = DATABASE()
            """
                )
            )

            available_qualities_exists = result.scalar() > 0

            if not available_qualities_exists:
                logger.info("Adding quality check fields to videos table...")

                # Add available_qualities JSON field
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos
                    ADD COLUMN available_qualities JSON DEFAULT NULL
                """
                    )
                )

                # Add quality_check_date field
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos
                    ADD COLUMN quality_check_date DATETIME DEFAULT NULL
                """
                    )
                )

                # Add max_available_quality field
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos
                    ADD COLUMN max_available_quality VARCHAR(50) DEFAULT NULL
                """
                    )
                )

                # Add quality_check_status field to track check results
                connection.execute(
                    text(
                        """
                    ALTER TABLE videos
                    ADD COLUMN quality_check_status VARCHAR(50) DEFAULT NULL
                """
                    )
                )

                logger.info("✅ Quality check fields added successfully")
            else:
                logger.info("✅ Quality check fields already exist - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 014 completed successfully")

    except Exception as e:
        logger.error(f"Migration 014 failed: {e}")
        raise


def downgrade(connection):
    """Remove quality check fields from videos table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration 014: Removing quality check fields")

            # Drop columns
            columns_to_drop = [
                "quality_check_status",
                "max_available_quality",
                "quality_check_date",
                "available_qualities",
            ]

            for column_name in columns_to_drop:
                # Check if column exists before dropping
                result = connection.execute(
                    text(
                        """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = 'videos'
                    AND column_name = :column_name
                    AND table_schema = DATABASE()
                """
                    ),
                    {"column_name": column_name},
                )

                column_exists = result.scalar() > 0

                if column_exists:
                    connection.execute(
                        text(f"ALTER TABLE videos DROP COLUMN {column_name}")
                    )
                    logger.info(f"✅ {column_name} column removed successfully")
                else:
                    logger.info(f"✅ {column_name} column does not exist - skipping")

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Migration 014 downgrade completed")

    except Exception as e:
        logger.error(f"Migration 014 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
