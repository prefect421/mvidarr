#!/usr/bin/env python3
"""
Standalone script to seed built-in themes directly into the database.
This ensures new installations have the default themes available.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import src.database.connection as db_conn
from src.config.config import Config
from src.database.connection import DatabaseManager, get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.seed_themes")

# Initialize database connection
config = Config()
db_conn.db_manager = DatabaseManager(config)

# Load theme definitions from migration 015
import importlib.util

spec = importlib.util.spec_from_file_location(
    "migration_015",
    str(Path(__file__).parent.parent / "migrations" / "015_seed_built_in_themes.py"),
)
migration_015 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_015)

BUILT_IN_THEMES = migration_015.BUILT_IN_THEMES


def seed_themes():
    """Seed built-in themes into the database"""
    try:
        logger.info("Starting built-in theme seeding...")

        with get_db() as session:
            connection = session.connection()

            # Check if any built-in themes already exist
            from sqlalchemy import text

            result = connection.execute(
                text("SELECT COUNT(*) FROM custom_themes WHERE is_built_in = 1")
            )
            existing_count = result.scalar()

            if existing_count > 0:
                print(f"✓ Built-in themes already exist ({existing_count} found)")
                logger.info(f"Built-in themes already seeded ({existing_count} found)")
                return True

            # Get admin user for theme ownership
            result = connection.execute(
                text("SELECT id FROM users WHERE role = 'ADMIN' LIMIT 1")
            )
            admin_user = result.fetchone()

            if not admin_user:
                # Try any user
                result = connection.execute(text("SELECT id FROM users LIMIT 1"))
                admin_user = result.fetchone()

            if not admin_user:
                print("✗ No users found - creating system user for themes")
                connection.execute(
                    text(
                        """
                    INSERT INTO users (username, password_hash, email, role, created_at)
                    VALUES ('system', '', 'system@mvidarr.local', 'ADMIN', CURRENT_TIMESTAMP)
                """
                    )
                )
                result = connection.execute(
                    text("SELECT id FROM users WHERE username = 'system'")
                )
                admin_user = result.fetchone()
                logger.info("Created system user for built-in themes")

            admin_user_id = admin_user[0]

            # Insert each built-in theme
            themes_created = 0
            for theme in BUILT_IN_THEMES:
                # Check if theme exists by name
                result = connection.execute(
                    text("SELECT id FROM custom_themes WHERE name = :name"),
                    {"name": theme["name"]},
                )
                if result.fetchone():
                    print(
                        f"  - Theme '{theme['display_name']}' already exists, skipping"
                    )
                    continue

                connection.execute(
                    text(
                        """
                        INSERT INTO custom_themes (
                            name, display_name, description, created_by,
                            is_public, is_built_in, theme_data,
                            created_at, updated_at
                        ) VALUES (
                            :name, :display_name, :description, :created_by,
                            1, 1, :theme_data,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """
                    ),
                    {
                        "name": theme["name"],
                        "display_name": theme["display_name"],
                        "description": theme.get("description", ""),
                        "created_by": admin_user_id,
                        "theme_data": json.dumps(theme["theme_data"]),
                    },
                )
                themes_created += 1
                print(f"  ✓ Created theme: {theme['display_name']}")
                logger.info(f"Created built-in theme: {theme['display_name']}")

            session.commit()

            print(f"\n✓ Successfully seeded {themes_created} built-in themes")
            logger.info(f"Theme seeding completed: {themes_created} themes created")
            return True

    except Exception as e:
        print(f"\n✗ Error seeding themes: {e}")
        logger.error(f"Theme seeding failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Built-in Theme Seeding Script")
    print("=" * 70)

    success = seed_themes()

    if success:
        print("\n✓ Theme seeding completed successfully")
        sys.exit(0)
    else:
        print("\n✗ Theme seeding failed")
        sys.exit(1)
