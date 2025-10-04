#!/usr/bin/env python3
"""
Migration 006: Add Sort Name Field to Artists

This migration implements Issue #17 by:
1. Adding a sort_name column to the artists table
2. Populating sort names for all existing artists using intelligent formatting rules
3. Ensuring all new artists will have sort names generated automatically
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from sqlalchemy import Column, Index, String, text

from src.database.connection import engine, get_db
from src.database.models import Artist
from src.utils.logger import get_logger
from src.utils.sort_name_generator import generate_sort_name

logger = get_logger("mvidarr.migration.006")


def add_sort_name_column(connection):
    """Add sort_name column to artists table"""
    try:
        # Use the connection provided by the migration system
        # DO NOT use engine.connect() as it creates a separate connection
        if True:  # Keep indentation for minimal changes
            conn = connection
            # Check if column already exists
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) as count
                FROM information_schema.columns 
                WHERE table_name = 'artists' 
                AND column_name = 'sort_name'
                AND table_schema = DATABASE()
            """
                )
            )

            column_exists = result.fetchone()[0] > 0

            if not column_exists:
                logger.info("Adding sort_name column to artists table")
                conn.execute(
                    text(
                        "ALTER TABLE artists ADD COLUMN sort_name VARCHAR(255) DEFAULT NULL"
                    )
                )

                # Add index for sort_name
                logger.info("Adding index for sort_name column")
                conn.execute(
                    text("CREATE INDEX idx_artist_sort_name ON artists (sort_name)")
                )

                # DO NOT commit here - migration system handles the commit
                logger.info("✅ Successfully added sort_name column and index")
            else:
                logger.info("✅ sort_name column already exists")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to add sort_name column: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def populate_sort_names(connection):
    """
    Populate sort names for all existing artists
    """
    try:
        # Use the connection provided by the migration system
        # Use raw SQL to avoid SQLAlchemy model attribute issues
        if True:  # Keep indentation for minimal changes
            logger.info("Starting sort name population for existing artists")

            # Get artists needing sort names using raw SQL
            result = connection.execute(
                text(
                    """
                SELECT id, name
                FROM artists
                WHERE sort_name IS NULL OR sort_name = ''
            """
                )
            )

            artists_to_fix = result.fetchall()
            total_to_fix = len(artists_to_fix)

            if total_to_fix == 0:
                logger.info(
                    "✅ All artists already have sort names - no population needed"
                )
                return True

            logger.info(f"Found {total_to_fix} artists needing sort names")

            # Generate and update sort names using raw SQL
            fixed_count = 0

            for artist_id, artist_name in artists_to_fix:
                try:
                    # Generate sort name using the utility function
                    sort_name = generate_sort_name(artist_name)

                    # Update using raw SQL
                    connection.execute(
                        text(
                            """
                        UPDATE artists
                        SET sort_name = :sort_name
                        WHERE id = :artist_id
                    """
                        ),
                        {"sort_name": sort_name, "artist_id": artist_id},
                    )

                    logger.info(
                        f"Generated sort name for artist ID {artist_id}: '{artist_name}' -> '{sort_name}'"
                    )
                    fixed_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to generate sort name for artist {artist_id} '{artist_name}': {e}"
                    )
                    continue

            # DO NOT commit here - migration system handles the commit
            logger.info(f"✅ Sort name population completed successfully")
            logger.info(
                f"✅ Generated sort names for {fixed_count}/{total_to_fix} artists"
            )

            # Verify the fix using raw SQL
            result = connection.execute(
                text(
                    """
                SELECT COUNT(*) as count
                FROM artists
                WHERE sort_name IS NULL OR sort_name = ''
            """
                )
            )
            remaining_without_sort_names = result.fetchone()[0]

            if remaining_without_sort_names == 0:
                logger.info("✅ Verification passed: All artists now have sort names")
                return True
            else:
                logger.warning(
                    f"⚠️  {remaining_without_sort_names} artists still without sort names"
                )
                return False

    except Exception as e:
        logger.error(f"❌ Sort name population failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def upgrade(connection):
    """
    Main migration function (required by migration system)
    """
    logger.info("Starting migration 006: Add sort name field to artists")

    # Step 1: Add the column
    if not add_sort_name_column(connection):
        raise Exception("Failed to add sort_name column")

    # Step 2: Populate sort names for existing artists
    if not populate_sort_names(connection):
        raise Exception("Failed to populate sort names")

    logger.info("✅ Migration 006 completed successfully")


def migrate_add_sort_name():
    """
    Wrapper for backwards compatibility
    """
    upgrade()
    return True


def downgrade():
    """
    Rollback migration - remove sort_name column (required by migration system)
    """
    logger.info("Rolling back migration 006: Removing sort_name column")

    with engine.connect() as conn:
        # Drop index first
        try:
            conn.execute(text("DROP INDEX idx_artist_sort_name ON artists"))
            logger.info("Dropped sort_name index")
        except Exception as e:
            logger.warning(f"Could not drop index (may not exist): {e}")

        # Drop column
        conn.execute(text("ALTER TABLE artists DROP COLUMN sort_name"))
        conn.commit()

    logger.info("✅ Migration 006 rollback completed successfully")


def rollback_migration():
    """
    Wrapper for backwards compatibility
    """
    downgrade()
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Migration 006: Add sort name field to artists"
    )
    parser.add_argument(
        "--rollback", action="store_true", help="Rollback the migration"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )

    args = parser.parse_args()

    if args.rollback:
        success = rollback_migration()
    else:
        if args.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
            logger.info("Would add sort_name column to artists table")
            logger.info("Would populate sort names for all existing artists")
            success = True
        else:
            success = migrate_add_sort_name()

    sys.exit(0 if success else 1)
