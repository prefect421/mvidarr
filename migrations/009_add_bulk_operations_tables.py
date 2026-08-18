#!/usr/bin/env python3
"""
Migration: Add Bulk Operations Tables for MVidarr 0.9.7 - Issue #74
Version: 009
Date: 2025-08-16
Description: Creates tables for bulk operations, progress tracking, audit trail, 
templates, and undo/redo functionality.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_009")


def upgrade(connection):
    """Create bulk operations tables"""
    try:
        # Use the connection provided by the migration system
        # DO NOT use get_db() as it will close the connection
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 009: Adding bulk operations tables")

            # Create bulk_operations table (MySQL/MariaDB syntax)
            connection.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS bulk_operations (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    user_id INTEGER NOT NULL,
                    operation_type VARCHAR(50) NOT NULL,
                    operation_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    target_ids JSON NOT NULL,
                    operation_params JSON,
                    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
                    total_items INTEGER NOT NULL,
                    processed_items INTEGER DEFAULT 0,
                    successful_items INTEGER DEFAULT 0,
                    failed_items INTEGER DEFAULT 0,
                    progress_percentage FLOAT DEFAULT 0.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME,
                    completed_at DATETIME,
                    estimated_completion DATETIME,
                    results JSON,
                    error_log JSON,
                    is_undoable BOOLEAN DEFAULT 1,
                    undo_data JSON,
                    undone_at DATETIME,
                    undone_by INTEGER,
                    is_preview BOOLEAN DEFAULT 0,
                    preview_results JSON,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (undone_by) REFERENCES users(id) ON DELETE SET NULL
                )
            """
                )
            )

            # Create indexes for bulk_operations
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_user_id ON bulk_operations(user_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_type ON bulk_operations(operation_type)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_status ON bulk_operations(status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_created ON bulk_operations(created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_undoable ON bulk_operations(is_undoable)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_operation_composite ON bulk_operations(user_id, status, created_at)"
                )
            )

            logger.info("Created bulk_operations table with indexes")

            # Create bulk_operation_progress table
            connection.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS bulk_operation_progress (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    operation_id INTEGER NOT NULL,
                    current_item_id VARCHAR(100),
                    current_item_name VARCHAR(500),
                    stage VARCHAR(100),
                    stage_progress FLOAT DEFAULT 0.0,
                    items_per_second FLOAT,
                    estimated_time_remaining INTEGER,
                    status_message TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (operation_id) REFERENCES bulk_operations(id) ON DELETE CASCADE
                )
            """
                )
            )

            # Create indexes for bulk_operation_progress
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_progress_operation ON bulk_operation_progress(operation_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_progress_updated ON bulk_operation_progress(updated_at)"
                )
            )

            logger.info("Created bulk_operation_progress table with indexes")

            # Create bulk_operation_audit table
            connection.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS bulk_operation_audit (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    operation_id INTEGER NOT NULL,
                    item_type VARCHAR(50) NOT NULL,
                    item_id INTEGER NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    field_name VARCHAR(100),
                    old_value JSON,
                    new_value JSON,
                    change_reason VARCHAR(255),
                    batch_sequence INTEGER,
                    change_metadata JSON,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (operation_id) REFERENCES bulk_operations(id) ON DELETE CASCADE
                )
            """
                )
            )

            # Create indexes for bulk_operation_audit
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_audit_operation ON bulk_operation_audit(operation_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_audit_item ON bulk_operation_audit(item_type, item_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_audit_timestamp ON bulk_operation_audit(timestamp)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_audit_action ON bulk_operation_audit(action)"
                )
            )

            logger.info("Created bulk_operation_audit table with indexes")

            # Create bulk_operation_templates table
            connection.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS bulk_operation_templates (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    user_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    operation_type VARCHAR(50) NOT NULL,
                    template_params JSON NOT NULL,
                    target_criteria JSON,
                    is_public BOOLEAN DEFAULT 0,
                    is_system BOOLEAN DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    last_used_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """
                )
            )

            # Create indexes for bulk_operation_templates
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_template_user ON bulk_operation_templates(user_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_template_type ON bulk_operation_templates(operation_type)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_template_public ON bulk_operation_templates(is_public)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_template_system ON bulk_operation_templates(is_system)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bulk_template_usage ON bulk_operation_templates(usage_count)"
                )
            )

            logger.info("Created bulk_operation_templates table with indexes")

            # Insert default system templates
            system_templates = [
                {
                    "name": "Mark Videos as Downloaded",
                    "description": "Update selected videos to Downloaded status",
                    "operation_type": "VIDEO_STATUS_UPDATE",
                    "template_params": '{"new_status": "DOWNLOADED"}',
                },
                {
                    "name": "Mark Videos as Wanted",
                    "description": "Update selected videos to Wanted status",
                    "operation_type": "VIDEO_STATUS_UPDATE",
                    "template_params": '{"new_status": "WANTED"}',
                },
                {
                    "name": "Mark Videos as Ignored",
                    "description": "Update selected videos to Ignored status",
                    "operation_type": "VIDEO_STATUS_UPDATE",
                    "template_params": '{"new_status": "IGNORED"}',
                },
                {
                    "name": "Bulk Delete Videos",
                    "description": "Delete selected videos from the library",
                    "operation_type": "VIDEO_DELETE",
                    "template_params": '{"confirm_delete": true}',
                },
                {
                    "name": "Update Video Quality",
                    "description": "Update quality information for selected videos",
                    "operation_type": "VIDEO_METADATA_UPDATE",
                    "template_params": '{"updates": {"quality": "1080p"}}',
                },
                {
                    "name": "Bulk Download Videos",
                    "description": "Queue selected videos for download",
                    "operation_type": "VIDEO_DOWNLOAD",
                    "template_params": '{"priority": 5}',
                },
            ]

            for template in system_templates:
                # Check if template already exists
                existing = connection.execute(
                    text(
                        """
                    SELECT id FROM bulk_operation_templates 
                    WHERE name = :name AND is_system = 1
                """
                    ),
                    {"name": template["name"]},
                ).fetchone()

                if not existing:
                    connection.execute(
                        text(
                            """
                        INSERT INTO bulk_operation_templates (
                            user_id, name, description, operation_type, 
                            template_params, is_public, is_system
                        ) VALUES (
                            NULL, :name, :description, :operation_type, 
                            :template_params, 1, 1
                        )
                    """
                        ),
                        {
                            "name": template["name"],
                            "description": template["description"],
                            "operation_type": template["operation_type"],
                            "template_params": template["template_params"],
                        },
                    )

            logger.info("Created system bulk operation templates")

            # DO NOT commit here - migration system handles the commit
            logger.info(
                "Migration 009 completed successfully: Bulk operations tables created"
            )

    except Exception as e:
        logger.error(f"Migration 009 failed: {e}")
        raise


def downgrade(connection):
    """Remove bulk operations tables"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting downgrade of migration 009")

            # Drop tables in reverse order of dependencies
            connection.execute(text("DROP TABLE IF EXISTS bulk_operation_templates"))
            connection.execute(text("DROP TABLE IF EXISTS bulk_operation_audit"))
            connection.execute(text("DROP TABLE IF EXISTS bulk_operation_progress"))
            connection.execute(text("DROP TABLE IF EXISTS bulk_operations"))

            # DO NOT commit here - migration system handles the commit
            logger.info("Migration 009 downgrade completed successfully")

    except Exception as e:
        logger.error(f"Migration 009 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bulk Operations Tables Migration")
    parser.add_argument(
        "--downgrade", action="store_true", help="Run downgrade instead of upgrade"
    )

    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
