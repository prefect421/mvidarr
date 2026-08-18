#!/usr/bin/env python3
"""
Migration: Add background job tables
Date: 2025
Purpose: Add tables for background job queue system with persistence and logging
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.add_background_job_tables")


def upgrade(connection):
    """Add background job system tables"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration: Add background job tables")

            # Check if tables already exist (idempotency)
            result = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name = 'background_jobs'
                AND table_schema = DATABASE()
            """))

            jobs_table_exists = result.scalar() > 0

            if jobs_table_exists:
                logger.info(
                    "✅ Background job tables already exist - skipping migration"
                )
                return

            # Background jobs table
            logger.info("Creating background_jobs table...")
            connection.execute(text("""
                CREATE TABLE background_jobs (
                    id VARCHAR(36) PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'queued',
                    priority INT DEFAULT 2,
                    payload JSON,
                    result JSON,
                    progress INT DEFAULT 0,
                    message TEXT,
                    error_message TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME NULL,
                    completed_at DATETIME NULL,
                    retry_count INT DEFAULT 0,
                    max_retries INT DEFAULT 3,
                    retry_delay INT DEFAULT 60,
                    created_by VARCHAR(50),
                    tags JSON
                )
            """))

            # Add indexes for performance
            connection.execute(
                text(
                    "CREATE INDEX idx_status_created ON background_jobs (status, created_at)"
                )
            )
            connection.execute(
                text("CREATE INDEX idx_created_by ON background_jobs (created_by)")
            )
            connection.execute(
                text("CREATE INDEX idx_type_status ON background_jobs (type, status)")
            )
            connection.execute(
                text(
                    "CREATE INDEX idx_priority_created ON background_jobs (priority, created_at)"
                )
            )

            # Job execution logs table
            logger.info("Creating job_execution_logs table...")
            connection.execute(text("""
                CREATE TABLE job_execution_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    job_id VARCHAR(36) NOT NULL,
                    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    level VARCHAR(10) NOT NULL,
                    message TEXT NOT NULL,
                    worker_name VARCHAR(50),
                    step VARCHAR(100),
                    data JSON
                )
            """))

            # Add indexes for log queries
            connection.execute(
                text(
                    "CREATE INDEX idx_job_id_timestamp ON job_execution_logs (job_id, timestamp)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX idx_level_timestamp ON job_execution_logs (level, timestamp)"
                )
            )

            # Job schedules table (for future enhancement)
            logger.info("Creating job_schedules table...")
            connection.execute(text("""
                CREATE TABLE job_schedules (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    job_type VARCHAR(50) NOT NULL,
                    cron_expression VARCHAR(100),
                    payload_template JSON,
                    enabled INT DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_run_at DATETIME NULL,
                    next_run_at DATETIME NULL,
                    total_runs INT DEFAULT 0,
                    successful_runs INT DEFAULT 0,
                    failed_runs INT DEFAULT 0
                )
            """))

            # Add indexes for schedule queries
            connection.execute(
                text(
                    "CREATE INDEX idx_enabled_next_run ON job_schedules (enabled, next_run_at)"
                )
            )
            connection.execute(
                text("CREATE INDEX idx_job_type ON job_schedules (job_type)")
            )

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Created background job system tables:")
            logger.info("   - background_jobs (main job storage)")
            logger.info("   - job_execution_logs (detailed execution logs)")
            logger.info("   - job_schedules (future: scheduled jobs)")
            logger.info("   - Added performance indexes")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


def downgrade(connection):
    """Remove background job system tables"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration: Removing background job tables")

            # Drop tables in reverse order (due to potential foreign key constraints)
            connection.execute(text("DROP TABLE IF EXISTS job_schedules"))
            connection.execute(text("DROP TABLE IF EXISTS job_execution_logs"))
            connection.execute(text("DROP TABLE IF EXISTS background_jobs"))

            # DO NOT commit here - migration system handles the commit
            logger.info("✅ Removed background job system tables")

    except Exception as e:
        logger.error(f"Downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
