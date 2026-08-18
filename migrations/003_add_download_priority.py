#!/usr/bin/env python3
"""
Migration: Add priority column to downloads table
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.003")


def upgrade(connection):
    """Add priority column and index to downloads table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            # Check if priority column already exists
            result = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'downloads'
                AND column_name = 'priority'
                AND table_schema = DATABASE()
            """))

            priority_exists = result.scalar() > 0

            if not priority_exists:
                logger.info("Adding priority column to downloads table...")

                # Add priority column
                connection.execute(text("""
                    ALTER TABLE downloads
                    ADD COLUMN priority INT DEFAULT 5
                    COMMENT '1-10, lower is higher priority (1=highest, 10=lowest)'
                """))

                # Update existing records to have default priority
                connection.execute(text("""
                    UPDATE downloads
                    SET priority = 5
                    WHERE priority IS NULL
                """))

                logger.info("Priority column added successfully")
            else:
                logger.info("Priority column already exists")

            # Check and create indexes
            indexes_to_create = [
                (
                    "idx_download_priority",
                    "CREATE INDEX idx_download_priority ON downloads (priority)",
                ),
                (
                    "idx_download_priority_status",
                    "CREATE INDEX idx_download_priority_status ON downloads (priority, status)",
                ),
            ]

            for index_name, create_sql in indexes_to_create:
                # Check if index exists
                result = connection.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM information_schema.statistics
                    WHERE table_name = 'downloads'
                    AND index_name = :index_name
                    AND table_schema = DATABASE()
                """),
                    {"index_name": index_name},
                )

                index_exists = result.scalar() > 0

                if not index_exists:
                    logger.info(f"Creating index {index_name}...")
                    connection.execute(text(create_sql))
                    logger.info(f"Index {index_name} created successfully")
                else:
                    logger.info(f"Index {index_name} already exists")

            # DO NOT commit here - migration system handles the commit
            logger.info("Migration 003 completed successfully")

    except Exception as e:
        logger.error(f"Migration 003 failed: {e}")
        raise


def downgrade(connection):
    """Remove priority column and indexes from downloads table"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration 003...")

            # Drop indexes
            indexes_to_drop = [
                "idx_download_priority",
                "idx_download_priority_status",
            ]

            for index_name in indexes_to_drop:
                try:
                    connection.execute(text(f"DROP INDEX {index_name} ON downloads"))
                    logger.info(f"Dropped index {index_name}")
                except Exception as e:
                    logger.warning(f"Could not drop index {index_name}: {e}")

            # Drop priority column
            try:
                connection.execute(text("ALTER TABLE downloads DROP COLUMN priority"))
                logger.info("Dropped priority column")
            except Exception as e:
                logger.warning(f"Could not drop priority column: {e}")

            # DO NOT commit here - migration system handles the commit
            logger.info("Migration 003 downgrade completed")

    except Exception as e:
        logger.error(f"Migration 003 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migration 003: Add download priority")
    parser.add_argument(
        "--downgrade", action="store_true", help="Downgrade the migration"
    )

    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
