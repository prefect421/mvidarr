"""
Utility to ensure built-in themes are seeded in the database.
This can be called during application startup or run manually.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import text
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.ensure_themes")


# Import theme definitions from migration 015
def get_builtin_themes():
    """Get built-in theme definitions from migration 015"""
    try:
        import importlib.util

        migrations_dir = Path(__file__).parent.parent.parent / "migrations"
        migration_015_path = migrations_dir / "015_seed_built_in_themes.py"

        if not migration_015_path.exists():
            logger.error(f"Migration 015 not found at: {migration_015_path}")
            return []

        spec = importlib.util.spec_from_file_location(
            "migration_015", migration_015_path
        )
        migration_015 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration_015)

        return migration_015.BUILT_IN_THEMES

    except Exception as e:
        logger.error(f"Failed to load built-in theme definitions: {e}")
        return []


def ensure_builtin_themes_exist():
    """
    Ensure built-in themes exist in the database.
    Seeds them if they don't exist.

    Returns:
        tuple: (success: bool, themes_created: int, message: str)
    """
    try:
        logger.info("Checking for built-in themes...")

        with get_db() as session:
            connection = session.connection()

            # Check if any built-in themes exist
            result = connection.execute(
                text("SELECT COUNT(*) FROM custom_themes WHERE is_built_in = 1")
            )
            existing_count = result.scalar()

            if existing_count > 0:
                logger.info(f"Built-in themes already exist ({existing_count} found)")
                return (
                    True,
                    0,
                    f"Built-in themes already exist ({existing_count} found)",
                )

            # No built-in themes - seed them
            logger.info("No built-in themes found - seeding now...")

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
                # No users exist yet - skip theme seeding
                # Themes will be seeded after the first admin is created via Installation Wizard
                logger.info(
                    "No users found - skipping built-in theme seeding. "
                    "Themes will be seeded after first admin creation via Installation Wizard."
                )
                return (
                    True,
                    0,
                    "Skipped - no admin user exists yet (will seed after wizard completion)",
                )

            admin_user_id = admin_user[0]

            # Get theme definitions
            themes = get_builtin_themes()
            if not themes:
                logger.error("No built-in theme definitions found!")
                return (False, 0, "Failed to load theme definitions")

            # Insert each theme
            themes_created = 0
            for theme in themes:
                # Check if theme exists by name
                result = connection.execute(
                    text("SELECT id FROM custom_themes WHERE name = :name"),
                    {"name": theme["name"]},
                )
                if result.fetchone():
                    logger.info(
                        f"Theme '{theme['display_name']}' already exists, skipping"
                    )
                    continue

                connection.execute(
                    text("""
                        INSERT INTO custom_themes (
                            name, display_name, description, created_by,
                            is_public, is_built_in, theme_data,
                            created_at, updated_at
                        ) VALUES (
                            :name, :display_name, :description, :created_by,
                            1, 1, :theme_data,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "name": theme["name"],
                        "display_name": theme["display_name"],
                        "description": theme.get("description", ""),
                        "created_by": admin_user_id,
                        "theme_data": json.dumps(theme["theme_data"]),
                    },
                )
                themes_created += 1
                logger.info(f"Created built-in theme: {theme['display_name']}")

            session.commit()

            logger.info(f"Successfully seeded {themes_created} built-in themes")
            return (
                True,
                themes_created,
                f"Successfully seeded {themes_created} built-in themes",
            )

    except Exception as e:
        logger.error(f"Failed to ensure built-in themes: {e}")
        return (False, 0, f"Error: {str(e)}")


if __name__ == "__main__":
    """Run as standalone script"""
    print("=" * 70)
    print("Built-in Theme Verification & Seeding")
    print("=" * 70)

    success, count, message = ensure_builtin_themes_exist()

    print(f"\n{message}")

    if success:
        print("\n✓ Theme verification completed successfully")
        sys.exit(0)
    else:
        print("\n✗ Theme verification failed")
        sys.exit(1)
