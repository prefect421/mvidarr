#!/usr/bin/env python3
"""
Database migration 004: Add thumbnail metadata and source tracking
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text

from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_004")


def upgrade(connection):
    """Add thumbnail metadata and source tracking columns"""
    logger.info("Running migration 004: Add thumbnail metadata and source tracking")

    try:
        # Use the connection provided by the migration system
        # DO NOT use get_db() as it will close the connection
        if True:  # Keep indentation for minimal changes
            # Check and add thumbnail metadata columns to artists table
            # Check if thumbnail_source already exists
            result = connection.execute(
                text("SHOW COLUMNS FROM artists LIKE 'thumbnail_source'")
            )
            if not result.fetchone():
                connection.execute(text("""
                    ALTER TABLE artists
                    ADD COLUMN thumbnail_source VARCHAR(50) DEFAULT NULL,
                    ADD COLUMN thumbnail_metadata JSON DEFAULT NULL,
                    ADD COLUMN thumbnail_uploaded_at DATETIME DEFAULT NULL
                """))
                logger.info("Added thumbnail metadata columns to artists table")
            else:
                logger.info("Thumbnail metadata columns already exist in artists table")

            # Check and add thumbnail metadata columns to videos table
            result = connection.execute(
                text("SHOW COLUMNS FROM videos LIKE 'thumbnail_source'")
            )
            if not result.fetchone():
                connection.execute(text("""
                    ALTER TABLE videos
                    ADD COLUMN thumbnail_source VARCHAR(50) DEFAULT NULL,
                    ADD COLUMN thumbnail_metadata JSON DEFAULT NULL,
                    ADD COLUMN thumbnail_uploaded_at DATETIME DEFAULT NULL
                """))
                logger.info("Added thumbnail metadata columns to videos table")
            else:
                logger.info("Thumbnail metadata columns already exist in videos table")

            # Set default source for existing thumbnails
            connection.execute(text("""
                UPDATE artists
                SET thumbnail_source = 'imvdb'
                WHERE thumbnail_url IS NOT NULL OR thumbnail_path IS NOT NULL
            """))

            connection.execute(text("""
                UPDATE videos
                SET thumbnail_source = 'imvdb'
                WHERE thumbnail_url IS NOT NULL OR thumbnail_path IS NOT NULL
            """))

            # DO NOT commit here - migration system handles the commit
            # session.commit() would close the connection that the migration system needs
            logger.info("Migration 004 completed successfully")

    except Exception as e:
        logger.error(f"Migration 004 failed: {e}")
        raise


def downgrade(connection):
    """Remove thumbnail metadata and source tracking columns"""
    logger.info("Running downgrade for migration 004")

    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            # Remove thumbnail metadata columns from artists table
            connection.execute(text("""
                ALTER TABLE artists
                DROP COLUMN thumbnail_source,
                DROP COLUMN thumbnail_metadata,
                DROP COLUMN thumbnail_uploaded_at
            """))

            # Remove thumbnail metadata columns from videos table
            connection.execute(text("""
                ALTER TABLE videos
                DROP COLUMN thumbnail_source,
                DROP COLUMN thumbnail_metadata,
                DROP COLUMN thumbnail_uploaded_at
            """))

            # DO NOT commit here - migration system handles the commit
            logger.info("Migration 004 downgrade completed successfully")

    except Exception as e:
        logger.error(f"Migration 004 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    # Create Flask app context for database access
    import os

    os.chdir(Path(__file__).parent.parent)

    from app import create_app

    app = create_app()

    with app.app_context():
        upgrade()
