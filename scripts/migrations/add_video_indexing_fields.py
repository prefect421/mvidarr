#!/usr/bin/env python3
"""
Database migration: Add video indexing fields
Adds local_path field to videos table and thumbnails_path setting
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text

from src.config.config import Config
from src.database.connection import get_db, init_db
from src.database.models import Setting
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration.video_indexing_fields")


class DummyApp:
    """Dummy app for database initialization"""

    def __init__(self):
        self.config = {}
        self.db_manager = None
        config = Config()
        for attr in dir(config):
            if not attr.startswith("_"):
                self.config[attr] = getattr(config, attr)

    def teardown_appcontext(self, func):
        """Dummy teardown function for Flask compatibility"""
        pass


def run_migration():
    """Run the migration"""
    try:
        # Initialize database
        app = DummyApp()
        init_db(app)

        with get_db() as session:
            # Add local_path column to videos table if it doesn't exist
            try:
                result = session.execute(text("DESCRIBE videos"))
                columns = [row[0] for row in result.fetchall()]

                if "local_path" not in columns:
                    logger.info("Adding local_path column to videos table")
                    session.execute(text("""
                        ALTER TABLE videos 
                        ADD COLUMN local_path VARCHAR(500) NULL 
                        AFTER thumbnail_path
                    """))
                    print("✅ Added local_path column to videos table")
                else:
                    print("⏭️  local_path column already exists in videos table")

            except Exception as e:
                logger.error(f"Failed to add local_path column: {e}")
                print(f"❌ Failed to add local_path column: {e}")
                return False

            # Add default settings for video indexing
            default_settings = [
                (
                    "thumbnails_path",
                    "data/thumbnails",
                    "Directory for storing video thumbnails",
                ),
                (
                    "auto_index_organized_videos",
                    "true",
                    "Automatically index videos when they are organized",
                ),
            ]

            for key, value, description in default_settings:
                existing = session.query(Setting).filter(Setting.key == key).first()
                if not existing:
                    setting = Setting(key=key, value=value, description=description)
                    session.add(setting)
                    logger.info(f"Added setting: {key}")
                    print(f"✅ Added setting: {key}")
                else:
                    print(f"⏭️  Setting already exists: {key}")

            session.commit()
            print("\n✅ Migration completed successfully")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return False


def main():
    """Main migration entry point"""
    print("🔄 Running video indexing fields migration...")
    print("-" * 50)

    success = run_migration()

    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nYou can now:")
        print("1. Run video indexing to populate the database")
        print("2. Use the new video indexing features")
        return 0
    else:
        print("\n💥 Migration failed!")
        return 1


if __name__ == "__main__":
    exit(main())
