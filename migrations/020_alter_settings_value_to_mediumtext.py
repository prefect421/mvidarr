#!/usr/bin/env python3
"""
Migration 020: Alter settings.value column to MEDIUMTEXT
Date: December 29, 2025
Issue: Cookie upload failing with "Data too long for column 'value'"
Version: v0.11.1

This migration changes the settings.value column from TEXT to MEDIUMTEXT
to support large values like base64-encoded cookie files.

TEXT: 65,535 bytes (64KB) - old limit
MEDIUMTEXT: 16,777,215 bytes (16MB) - new limit

This fixes the cookie upload 500 error where base64-encoded cookies
exceed the 64KB TEXT column limit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.020")


def upgrade(connection):
    """Alter settings.value column to MEDIUMTEXT"""
    try:
        logger.info("Starting migration 020: Alter settings.value to MEDIUMTEXT")

        # Check current column type
        result = connection.execute(
            text(
                """
            SELECT COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'settings'
              AND COLUMN_NAME = 'value'
            """
            )
        ).fetchone()

        if result:
            current_type = result[0]
            logger.info(f"Current settings.value column type: {current_type}")

            # Alter column to MEDIUMTEXT
            logger.info("Altering settings.value column to MEDIUMTEXT...")
            connection.execute(
                text(
                    """
                ALTER TABLE settings
                MODIFY COLUMN value MEDIUMTEXT NULL
                """
                )
            )
            # Note: Transaction is managed by migration framework - no manual commit

            logger.info(
                "✅ Successfully altered settings.value column to MEDIUMTEXT"
            )
            logger.info(
                "   Old limit: 65,535 bytes (64KB) - New limit: 16,777,215 bytes (16MB)"
            )
        else:
            logger.warning("settings.value column not found - skipping migration")

        return True

    except Exception as e:
        logger.error(f"Migration 020 failed: {e}", exc_info=True)
        raise


def downgrade(connection):
    """Revert settings.value column back to TEXT (WARNING: May lose data!)"""
    try:
        logger.info("Starting migration 020 downgrade: Revert to TEXT")

        # WARNING: Check for large values that would be truncated
        result = connection.execute(
            text(
                """
            SELECT COUNT(*)
            FROM settings
            WHERE CHAR_LENGTH(value) > 65535
            """
            )
        ).fetchone()

        large_values_count = result[0] if result else 0

        if large_values_count > 0:
            logger.error(
                f"⚠️  Cannot downgrade: {large_values_count} settings have values > 64KB"
            )
            logger.error("   These values would be truncated. Aborting downgrade.")
            raise RuntimeError(
                f"Cannot downgrade: {large_values_count} settings exceed TEXT limit"
            )

        # Safe to downgrade
        logger.info("No large values found - safe to downgrade to TEXT")
        connection.execute(
            text(
                """
            ALTER TABLE settings
            MODIFY COLUMN value TEXT NULL
            """
            )
        )
        # Note: Transaction is managed by migration framework - no manual commit

        logger.info("✅ Successfully reverted settings.value column to TEXT")
        return True

    except Exception as e:
        logger.error(f"Migration 020 downgrade failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Test migration
    from src.database.connection import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        upgrade(conn)
