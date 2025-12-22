#!/usr/bin/env python3
"""
Migration 019: Add Scheduler V2 Tables and Fields
Date: December 22, 2025
Issue: #181 - Phase 1: Database Schema & Celery Configuration for Scheduler V2
Version: v0.10.1

This migration adds Scheduler V2 infrastructure:
1. Creates scheduled_jobs table for job tracking
2. Adds per-artist scheduling fields to artists table:
   - discovery_interval_hours (INT) - Custom discovery interval per artist
   - last_download (DATETIME) - Last download timestamp
   - discovery_enabled (BOOLEAN) - Enable/disable discovery independently
   - download_enabled (BOOLEAN) - Enable/disable downloads independently
   - max_videos_per_discovery (INT) - Max videos per discovery run
   - schedule_priority (VARCHAR) - Scheduling priority level
3. Adds retry tracking fields to downloads table:
   - retry_count (INT) - Number of retry attempts
   - last_attempt (DATETIME) - Last retry attempt timestamp
   - last_error (TEXT) - Last error message
   - next_retry_at (DATETIME) - Next scheduled retry time
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.019")


def upgrade(connection):
    """Add Scheduler V2 tables and fields"""
    try:
        logger.info("Starting migration 019: Add Scheduler V2 tables and fields")

        # ===================================================================
        # Part 1: Create scheduled_jobs table
        # ===================================================================
        logger.info("Creating scheduled_jobs table...")

        # Check if table already exists
        result = connection.execute(
            text(
                """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'scheduled_jobs'
        """
            )
        )

        table_exists = result.scalar() > 0

        if not table_exists:
            connection.execute(
                text(
                    """
                CREATE TABLE scheduled_jobs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    job_type VARCHAR(50) NOT NULL COMMENT 'discovery, download, health_check',
                    artist_id INT DEFAULT NULL COMMENT 'NULL for global jobs',
                    status VARCHAR(50) NOT NULL DEFAULT 'pending' COMMENT 'pending, running, completed, failed, retrying',
                    started_at DATETIME DEFAULT NULL,
                    completed_at DATETIME DEFAULT NULL,
                    celery_task_id VARCHAR(255) DEFAULT NULL UNIQUE COMMENT 'Celery task UUID',
                    retry_count INT NOT NULL DEFAULT 0,
                    max_retries INT NOT NULL DEFAULT 3,
                    error_message TEXT DEFAULT NULL,
                    result_summary JSON DEFAULT NULL COMMENT 'Job results as JSON',
                    execution_time_seconds INT DEFAULT NULL COMMENT 'Execution duration',
                    triggered_by VARCHAR(50) NOT NULL DEFAULT 'scheduler' COMMENT 'scheduler, manual, api, webhook',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE,
                    INDEX idx_scheduled_job_type (job_type),
                    INDEX idx_scheduled_job_status (status),
                    INDEX idx_scheduled_job_artist_id (artist_id),
                    INDEX idx_scheduled_job_celery_task_id (celery_task_id),
                    INDEX idx_scheduled_job_created_at (created_at),
                    INDEX idx_scheduled_job_started_at (started_at),
                    INDEX idx_scheduled_job_type_status (job_type, status),
                    INDEX idx_scheduled_job_artist_status (artist_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='Scheduled job tracking for Scheduler V2'
            """
                )
            )
            logger.info("✅ scheduled_jobs table created successfully")
        else:
            logger.info("✅ scheduled_jobs table already exists - skipping")

        # ===================================================================
        # Part 2: Add Scheduler V2 fields to artists table
        # ===================================================================
        logger.info("Adding Scheduler V2 fields to artists table...")

        artist_fields_to_add = [
            (
                "discovery_interval_hours",
                "INT NOT NULL DEFAULT 24",
                "Per-artist discovery interval in hours",
            ),
            (
                "last_download",
                "DATETIME DEFAULT NULL",
                "Last download timestamp for this artist",
            ),
            (
                "discovery_enabled",
                "BOOLEAN NOT NULL DEFAULT TRUE",
                "Enable/disable discovery independently",
            ),
            (
                "download_enabled",
                "BOOLEAN NOT NULL DEFAULT TRUE",
                "Enable/disable auto-downloads independently",
            ),
            (
                "max_videos_per_discovery",
                "INT NOT NULL DEFAULT 5",
                "Maximum videos to discover per run",
            ),
            (
                "schedule_priority",
                "VARCHAR(20) NOT NULL DEFAULT 'medium'",
                "Scheduling priority: high, medium, low",
            ),
        ]

        for field_name, field_type, field_comment in artist_fields_to_add:
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

                connection.execute(
                    text(
                        f"""
                    ALTER TABLE artists
                    ADD COLUMN {field_name} {field_type}
                    COMMENT '{field_comment}'
                """
                    )
                )

                logger.info(f"✅ {field_name} column added successfully")
            else:
                logger.info(f"✅ {field_name} column already exists - skipping")

        # Add indexes for artist scheduler fields
        logger.info("Adding indexes for artist scheduler fields...")

        artist_indexes_to_add = [
            ("idx_artist_discovery_enabled", "discovery_enabled"),
            ("idx_artist_download_enabled", "download_enabled"),
            ("idx_artist_schedule_priority", "schedule_priority"),
            ("idx_artist_last_discovery", "last_discovery"),
            ("idx_artist_last_download", "last_download"),
        ]

        for index_name, column_name in artist_indexes_to_add:
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

        # Add composite index for scheduler queries
        composite_index = "idx_artist_scheduler_query"
        result = connection.execute(
            text(
                f"""
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_name = 'artists'
            AND index_name = '{composite_index}'
            AND table_schema = DATABASE()
        """
            )
        )

        if result.scalar() == 0:
            logger.info(f"Creating composite index {composite_index}...")
            connection.execute(
                text(
                    f"""
                CREATE INDEX {composite_index}
                ON artists (monitored, discovery_enabled, schedule_priority)
            """
                )
            )
            logger.info(f"✅ Composite index {composite_index} created successfully")
        else:
            logger.info(f"✅ Composite index {composite_index} already exists")

        # ===================================================================
        # Part 3: Add retry fields to downloads table
        # ===================================================================
        logger.info("Adding retry tracking fields to downloads table...")

        download_fields_to_add = [
            ("retry_count", "INT NOT NULL DEFAULT 0", "Number of retry attempts"),
            (
                "last_attempt",
                "DATETIME DEFAULT NULL",
                "Last retry attempt timestamp",
            ),
            ("last_error", "TEXT DEFAULT NULL", "Last error message encountered"),
            (
                "next_retry_at",
                "DATETIME DEFAULT NULL",
                "Next scheduled retry time (exponential backoff)",
            ),
        ]

        for field_name, field_type, field_comment in download_fields_to_add:
            # Check if column already exists
            result = connection.execute(
                text(
                    f"""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'downloads'
                AND column_name = '{field_name}'
                AND table_schema = DATABASE()
            """
                )
            )

            field_exists = result.scalar() > 0

            if not field_exists:
                logger.info(f"Adding {field_name} column to downloads table...")

                connection.execute(
                    text(
                        f"""
                    ALTER TABLE downloads
                    ADD COLUMN {field_name} {field_type}
                    COMMENT '{field_comment}'
                """
                    )
                )

                logger.info(f"✅ {field_name} column added successfully")
            else:
                logger.info(f"✅ {field_name} column already exists - skipping")

        # Add indexes for download retry fields
        logger.info("Adding indexes for download retry fields...")

        download_indexes_to_add = [
            ("idx_download_retry_count", "retry_count"),
            ("idx_download_next_retry_at", "next_retry_at"),
        ]

        for index_name, column_name in download_indexes_to_add:
            result = connection.execute(
                text(
                    f"""
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_name = 'downloads'
                AND index_name = '{index_name}'
                AND table_schema = DATABASE()
            """
                )
            )

            index_exists = result.scalar() > 0

            if not index_exists:
                logger.info(f"Creating index {index_name}...")
                connection.execute(
                    text(f"CREATE INDEX {index_name} ON downloads ({column_name})")
                )
                logger.info(f"✅ Index {index_name} created successfully")
            else:
                logger.info(f"✅ Index {index_name} already exists - skipping")

        # Add composite index for retry queries
        retry_composite_index = "idx_download_retry_status"
        result = connection.execute(
            text(
                f"""
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_name = 'downloads'
            AND index_name = '{retry_composite_index}'
            AND table_schema = DATABASE()
        """
            )
        )

        if result.scalar() == 0:
            logger.info(f"Creating composite index {retry_composite_index}...")
            connection.execute(
                text(
                    f"""
                CREATE INDEX {retry_composite_index}
                ON downloads (status, retry_count, next_retry_at)
            """
                )
            )
            logger.info(
                f"✅ Composite index {retry_composite_index} created successfully"
            )
        else:
            logger.info(f"✅ Composite index {retry_composite_index} already exists")

        logger.info("✅ Migration 019 completed successfully")
        logger.info("")
        logger.info("Scheduler V2 infrastructure is now ready:")
        logger.info("  - scheduled_jobs table created")
        logger.info("  - Artist model enhanced with 6 scheduling fields")
        logger.info("  - Download model enhanced with 4 retry fields")
        logger.info("  - All indexes created for optimal performance")

    except Exception as e:
        logger.error(f"Migration 019 failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


def downgrade(connection):
    """
    Rollback migration - remove Scheduler V2 tables and fields
    """
    try:
        logger.info("Rolling back migration 019: Removing Scheduler V2 infrastructure")

        # Drop scheduled_jobs table
        logger.info("Dropping scheduled_jobs table...")
        try:
            connection.execute(text("DROP TABLE IF EXISTS scheduled_jobs"))
            logger.info("✅ scheduled_jobs table dropped")
        except Exception as e:
            logger.warning(f"Could not drop scheduled_jobs table: {e}")

        # Drop artist scheduler indexes
        artist_indexes_to_drop = [
            "idx_artist_discovery_enabled",
            "idx_artist_download_enabled",
            "idx_artist_schedule_priority",
            "idx_artist_last_download",
            "idx_artist_scheduler_query",
        ]

        for index_name in artist_indexes_to_drop:
            try:
                connection.execute(text(f"DROP INDEX {index_name} ON artists"))
                logger.info(f"Dropped index {index_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop index {index_name} (may not exist): {e}"
                )

        # Drop artist scheduler fields
        artist_fields_to_drop = [
            "discovery_interval_hours",
            "last_download",
            "discovery_enabled",
            "download_enabled",
            "max_videos_per_discovery",
            "schedule_priority",
        ]

        for field_name in artist_fields_to_drop:
            try:
                connection.execute(
                    text(f"ALTER TABLE artists DROP COLUMN {field_name}")
                )
                logger.info(f"Dropped column artists.{field_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop column artists.{field_name} (may not exist): {e}"
                )

        # Drop download retry indexes
        download_indexes_to_drop = [
            "idx_download_retry_count",
            "idx_download_next_retry_at",
            "idx_download_retry_status",
        ]

        for index_name in download_indexes_to_drop:
            try:
                connection.execute(text(f"DROP INDEX {index_name} ON downloads"))
                logger.info(f"Dropped index {index_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop index {index_name} (may not exist): {e}"
                )

        # Drop download retry fields
        download_fields_to_drop = [
            "retry_count",
            "last_attempt",
            "last_error",
            "next_retry_at",
        ]

        for field_name in download_fields_to_drop:
            try:
                connection.execute(
                    text(f"ALTER TABLE downloads DROP COLUMN {field_name}")
                )
                logger.info(f"Dropped column downloads.{field_name}")
            except Exception as e:
                logger.warning(
                    f"Could not drop column downloads.{field_name} (may not exist): {e}"
                )

        logger.info("✅ Migration 019 rollback completed successfully")

    except Exception as e:
        logger.error(f"Migration 019 rollback failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    import argparse

    from src.database.connection import engine

    parser = argparse.ArgumentParser(
        description="Migration 019: Add Scheduler V2 tables and fields"
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

    logger.info("Migration complete. Database connection closed.")
    sys.exit(0)
