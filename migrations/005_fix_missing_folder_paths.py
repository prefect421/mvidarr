#!/usr/bin/env python3
"""
Migration 005: Fix missing folder paths for artists
Date: July 2025
Purpose: Populate missing folder_path fields using sanitized artist names
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.services.filename_cleanup import FilenameCleanup
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.005_fix")


def upgrade(connection):
    """Fix missing folder paths for all artists"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 005: Fix missing artist folder paths")

            # Use raw SQL to avoid ORM model attribute issues
            result = connection.execute(text("""
                SELECT id, name, folder_path
                FROM artists
                WHERE folder_path IS NULL OR folder_path = ''
            """))

            artists_to_fix = result.fetchall()

            if not artists_to_fix:
                logger.info(
                    "✅ All artists already have folder paths - no migration needed"
                )
                return

            logger.info(f"Found {len(artists_to_fix)} artists to fix")

            fixed_count = 0
            for artist_id, artist_name, _ in artists_to_fix:
                try:
                    folder_path = FilenameCleanup.sanitize_folder_name(artist_name)

                    connection.execute(
                        text("""
                        UPDATE artists SET folder_path = :folder_path WHERE id = :id
                    """),
                        {"folder_path": folder_path, "id": artist_id},
                    )

                    logger.info(
                        f"Fixed artist ID {artist_id}: '{artist_name}' -> '{folder_path}'"
                    )
                    fixed_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to fix artist {artist_id} '{artist_name}': {e}"
                    )
                    continue

            logger.info(
                f"✅ Fixed folder paths for {fixed_count}/{len(artists_to_fix)} artists"
            )
            # DO NOT commit here - migration system handles the commit

    except Exception as e:
        logger.error(f"Migration 005 failed: {e}")
        raise


def downgrade(connection):
    """Remove generated folder paths"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Downgrading migration 005: Clearing folder paths")

            connection.execute(text("""
                UPDATE artists
                SET folder_path = NULL
                WHERE folder_path IS NOT NULL
            """))

            logger.info(
                "✅ Migration 005 downgrade completed: Cleared all folder paths"
            )
            # DO NOT commit here - migration system handles the commit

    except Exception as e:
        logger.error(f"Migration 005 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    upgrade()
