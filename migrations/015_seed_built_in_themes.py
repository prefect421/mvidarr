#!/usr/bin/env python3
"""
Migration: Seed Built-in Themes
Version: 015
Date: 2025-10-06
Description: Populates the custom_themes table with built-in themes (Cyber, Default, VaporWave, TARDIS, Punk 77, MTV)
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_015")

# Built-in theme data
BUILT_IN_THEMES = [
    {
        "name": "cyber",
        "display_name": "Cyber",
        "description": "Cyberpunk-inspired dark theme with cyan and green accents",
        "theme_data": {
            "--bg-primary": "#000000",
            "--bg-secondary": "#0d1117",
            "--bg-tertiary": "#161b22",
            "--sidebar-bg": "#000000",
            "--sidebar-bg-secondary": "#2d2d2d",
            "--search-bar-bg": "#161b22",
            "--bg-modal": "#333333",
            "--bg-card": "#2a2a2a",
            "--bg-hover": "#404040",
            "--top-bar-bg": "#0d1117",
            "--text-primary": "#00fff7",
            "--text-secondary": "#7dd3fc",
            "--text-accent": "#06ff9b",
            "--text-muted": "#888888",
            "--text-inverse": "#000000",
            "--btn-primary-bg": "#53ffff",
            "--btn-primary-text": "#000000",
            "--btn-primary-hover": "#3a8eef",
            "--btn-secondary-bg": "#666666",
            "--btn-secondary-text": "#ffffff",
            "--btn-secondary-hover": "#777777",
            "--btn-danger-bg": "#dc3545",
            "--btn-danger-text": "#ffffff",
            "--btn-danger-hover": "#c82333",
            "--border-primary": "#00fff7",
            "--border-secondary": "#555555",
            "--border-focus": "#4a9eff",
            "--border-hover": "#666666",
            "--success": "#008800",
            "--success-dark": "#1e7e34",
            "--warning": "#e1b500",
            "--warning-dark": "#d39e00",
            "--error": "#ff0000",
            "--error-color": "#ff6b6b",
            "--info": "#006c6c",
            "--info-dark": "#117a8b",
            "--input-bg": "#3a3a3a",
            "--input-text": "#ffffff",
            "--input-border": "#555555",
            "--input-focus": "#4a9eff",
            "--nav-bg": "#1a1a1a",
            "--nav-text": "#cccccc",
            "--nav-hover": "#404040",
            "--nav-active": "#4a9eff",
            "--accent-secondary": "#0099cc",
            "--accent-dark": "#007799",
            "--shadow": "#000000",
            "--shadow-hover": "#000000",
            "--border-focus-shadow": "#00fff7",
            "--modalBackgroundColor": "#0d1117",
            "--modalBackdropBackgroundColor": "#000000",
            "--modal-overlay": "#000000",
            "--modalCloseButtonHoverColor": "#ff0000",
            "--inputHoverBackgroundColor": "#161b22",
            "--inputSelectedBackgroundColor": "#00fff7",
            "--inputReadOnlyBackgroundColor": "#000000",
            "--inputErrorBorderColor": "#ff0000",
            "--inputWarningBorderColor": "#ffff00",
            "--menuItemColor": "#00fff7",
            "--menuItemHoverBackgroundColor": "#161b22",
            "--popoverBodyBackgroundColor": "#0d1117",
            "--popoverTitleBackgroundColor": "#000000",
            "--disabledColor": "#444444",
            "--helpTextColor": "#7dd3fc",
            "--linkHoverColor": "#00fff7",
            "--iconButtonHoverColor": "#00fff7",
        },
    },
    {
        "name": "default",
        "display_name": "Default",
        "description": "Classic dark theme with blue accents",
        "theme_data": {
            "--bg-primary": "#1a1a1a",
            "--bg-secondary": "#2d2d2d",
            "--bg-tertiary": "#3a3a3a",
            "--text-primary": "#ffffff",
            "--text-secondary": "#cccccc",
            "--text-accent": "#4a9eff",
            "--btn-primary-bg": "#4a9eff",
            "--btn-primary-text": "#ffffff",
            "--border-primary": "#444444",
            "--success": "#28a745",
            "--warning": "#ffc107",
            "--error": "#dc3545",
            "--info": "#17a2b8",
            "--sidebar-bg": "#1a1a1a",
            "--search-bar-bg": "#333333",
            "--top-bar-bg": "#1a1a1a",
        },
    },
    {
        "name": "vaporwave",
        "display_name": "VaporWave",
        "description": "Retro vaporwave aesthetic with pink and purple gradients",
        "theme_data": {
            "--bg-primary": "#1a0d26",
            "--text-primary": "#ff3cac",
            "--text-secondary": "#d4a5f2",
            "--bg-secondary": "#2d1b3d",
            "--bg-tertiary": "#3d2852",
            "--text-accent": "#ff3cac",
            "--btn-primary-bg": "#ff3cac",
            "--btn-primary-text": "#ffffff",
            "--border-primary": "#ff3cac",
            "--success": "#00ff94",
            "--warning": "#ffee00",
            "--error": "#ff073a",
            "--info": "#0abdc6",
            "--sidebar-bg": "#1a0d26",
            "--search-bar-bg": "#3d2852",
            "--top-bar-bg": "#2d1b3d",
        },
    },
    {
        "name": "tardis",
        "display_name": "TARDIS",
        "description": "Doctor Who inspired theme with police box blue",
        "theme_data": {
            "--bg-primary": "#000000",
            "--bg-secondary": "#592d00",
            "--bg-tertiary": "#6a6a6a",
            "--sidebar-bg": "#002147",
            "--sidebar-bg-secondary": "#002147",
            "--search-bar-bg": "#39240d",
            "--bg-modal": "#333333",
            "--bg-card": "#9d4f00",
            "--bg-hover": "#404040",
            "--top-bar-bg": "#002147",
            "--text-primary": "#ffffff",
            "--text-secondary": "#cccccc",
            "--text-accent": "#4db8ff",
            "--text-muted": "#888888",
            "--text-inverse": "#000000",
            "--btn-primary-bg": "#4db8ff",
            "--btn-primary-text": "#ffffff",
            "--btn-primary-hover": "#3a8eef",
            "--btn-secondary-bg": "#666666",
            "--btn-secondary-text": "#ffffff",
            "--btn-secondary-hover": "#777777",
            "--btn-danger-bg": "#dc3545",
            "--btn-danger-text": "#ffffff",
            "--btn-danger-hover": "#c82333",
            "--border-primary": "#444444",
            "--border-secondary": "#555555",
            "--border-focus": "#4a9eff",
            "--border-hover": "#666666",
            "--success": "#28a745",
            "--success-dark": "#1e7e34",
            "--warning": "#ffc107",
            "--warning-dark": "#d39e00",
            "--error": "#dc3545",
            "--error-color": "#ff6b6b",
            "--info": "#17a2b8",
            "--info-dark": "#117a8b",
            "--input-bg": "#3a3a3a",
            "--input-text": "#ffffff",
            "--input-border": "#555555",
            "--input-focus": "#4a9eff",
            "--nav-bg": "#1a1a1a",
            "--nav-text": "#cccccc",
            "--nav-hover": "#404040",
            "--nav-active": "#4a9eff",
            "--accent-secondary": "#0099cc",
            "--accent-dark": "#007799",
            "--shadow": "#00214720",
            "--shadow-hover": "#00214740",
            "--border-focus-shadow": "#4db8ff",
            "--modalBackgroundColor": "#333333",
            "--modalBackdropBackgroundColor": "#000000",
            "--modal-overlay": "#00000080",
            "--modalCloseButtonHoverColor": "#dc3545",
            "--inputHoverBackgroundColor": "#404040",
            "--inputSelectedBackgroundColor": "#4db8ff",
            "--inputReadOnlyBackgroundColor": "#000000",
            "--inputErrorBorderColor": "#dc3545",
            "--inputWarningBorderColor": "#ffc107",
            "--menuItemColor": "#ffffff",
            "--menuItemHoverBackgroundColor": "#404040",
            "--popoverBodyBackgroundColor": "#333333",
            "--popoverTitleBackgroundColor": "#002147",
            "--disabledColor": "#666666",
            "--helpTextColor": "#cccccc",
            "--linkHoverColor": "#4db8ff",
            "--iconButtonHoverColor": "#4db8ff",
        },
    },
    {
        "name": "punk_77",
        "display_name": "Punk 77",
        "description": "Rebellious punk rock theme with bold neon colors",
        "theme_data": {
            "--bg-primary": "#189a4d",
            "--bg-secondary": "#ea00ea",
            "--bg-tertiary": "#6c21c0",
            "--sidebar-bg": "#f1da58",
            "--sidebar-bg-secondary": "#ffff00",
            "--search-bar-bg": "#2d2d2d",
            "--bg-modal": "#ff33b8",
            "--bg-card": "#0e832c",
            "--bg-hover": "#404040",
            "--top-bar-bg": "#2d2d2d",
            "--text-primary": "#ffffff",
            "--text-secondary": "#4f0002",
            "--text-accent": "#000000",
            "--text-muted": "#fff311",
            "--text-inverse": "#000000",
            "--btn-primary-bg": "#ff0040",
            "--btn-primary-text": "#ffffff",
            "--btn-primary-hover": "#3a8eef",
            "--btn-secondary-bg": "#666666",
            "--btn-secondary-text": "#ffffff",
            "--btn-secondary-hover": "#777777",
            "--btn-danger-bg": "#dc3545",
            "--btn-danger-text": "#ffffff",
            "--btn-danger-hover": "#c82333",
            "--border-primary": "#00ff00",
            "--border-secondary": "#ff00ff",
            "--border-focus": "#0000ff",
            "--border-hover": "#00ffff",
            "--success": "#28a745",
            "--success-dark": "#1e7e34",
            "--warning": "#ffc107",
            "--warning-dark": "#d39e00",
            "--error": "#dc3545",
            "--error-color": "#ff6b6b",
            "--info": "#17a2b8",
            "--info-dark": "#117a8b",
            "--input-bg": "#3a3a3a",
            "--input-text": "#ffffff",
            "--input-border": "#555555",
            "--input-focus": "#4a9eff",
            "--nav-bg": "#1a1a1a",
            "--nav-text": "#cccccc",
            "--nav-hover": "#404040",
            "--nav-active": "#4a9eff",
            "--accent-secondary": "#0099cc",
            "--accent-dark": "#007799",
            "--shadow": "#189a4d20",
            "--shadow-hover": "#189a4d40",
            "--border-focus-shadow": "#00ff00",
            "--modalBackgroundColor": "#ff33b8",
            "--modalBackdropBackgroundColor": "#189a4d",
            "--modal-overlay": "#00000080",
            "--modalCloseButtonHoverColor": "#ff0040",
            "--inputHoverBackgroundColor": "#404040",
            "--inputSelectedBackgroundColor": "#ff0040",
            "--inputReadOnlyBackgroundColor": "#0e832c",
            "--inputErrorBorderColor": "#dc3545",
            "--inputWarningBorderColor": "#ffc107",
            "--menuItemColor": "#ffffff",
            "--menuItemHoverBackgroundColor": "#404040",
            "--popoverBodyBackgroundColor": "#ff33b8",
            "--popoverTitleBackgroundColor": "#f1da58",
            "--disabledColor": "#666666",
            "--helpTextColor": "#fff311",
            "--linkHoverColor": "#ff0040",
            "--iconButtonHoverColor": "#ff0040",
        },
    },
    {
        "name": "mtv",
        "display_name": "MTV",
        "description": "MTV-inspired retro theme with vibrant 80s colors",
        "theme_data": {
            "--bg-primary": "#000000",
            "--bg-secondary": "#560b66",
            "--bg-tertiary": "#1e4757",
            "--sidebar-bg": "#ff1493",
            "--sidebar-bg-secondary": "#2d2d2d",
            "--search-bar-bg": "#2d2d2d",
            "--bg-modal": "#333333",
            "--bg-card": "#2a2a2a",
            "--bg-hover": "#404040",
            "--top-bar-bg": "#338bec",
            "--text-primary": "#ffffff",
            "--text-secondary": "#cccccc",
            "--text-accent": "#00ffff",
            "--text-muted": "#888888",
            "--text-inverse": "#000000",
            "--btn-primary-bg": "#00a6a6",
            "--btn-primary-text": "#ffffff",
            "--btn-primary-hover": "#3a8eef",
            "--btn-secondary-bg": "#666666",
            "--btn-secondary-text": "#ffffff",
            "--btn-secondary-hover": "#777777",
            "--btn-danger-bg": "#dc3545",
            "--btn-danger-text": "#ffffff",
            "--btn-danger-hover": "#c82333",
            "--border-primary": "#444444",
            "--border-secondary": "#555555",
            "--border-focus": "#4a9eff",
            "--border-hover": "#666666",
            "--success": "#28a745",
            "--success-dark": "#1e7e34",
            "--warning": "#ffc107",
            "--warning-dark": "#d39e00",
            "--error": "#dc3545",
            "--error-color": "#ff6b6b",
            "--info": "#17a2b8",
            "--info-dark": "#117a8b",
            "--input-bg": "#3a3a3a",
            "--input-text": "#ffffff",
            "--input-border": "#555555",
            "--input-focus": "#4a9eff",
            "--nav-bg": "#1a1a1a",
            "--nav-text": "#cccccc",
            "--nav-hover": "#404040",
            "--nav-active": "#4a9eff",
            "--accent-secondary": "#0099cc",
            "--accent-dark": "#007799",
            "--shadow": "#ff149320",
            "--shadow-hover": "#ff149340",
            "--border-focus-shadow": "#00ffff",
            "--modalBackgroundColor": "#333333",
            "--modalBackdropBackgroundColor": "#000000",
            "--modal-overlay": "#00000080",
            "--modalCloseButtonHoverColor": "#dc3545",
            "--inputHoverBackgroundColor": "#404040",
            "--inputSelectedBackgroundColor": "#00a6a6",
            "--inputReadOnlyBackgroundColor": "#2a2a2a",
            "--inputErrorBorderColor": "#dc3545",
            "--inputWarningBorderColor": "#ffc107",
            "--menuItemColor": "#ffffff",
            "--menuItemHoverBackgroundColor": "#404040",
            "--popoverBodyBackgroundColor": "#333333",
            "--popoverTitleBackgroundColor": "#ff1493",
            "--disabledColor": "#888888",
            "--helpTextColor": "#cccccc",
            "--linkHoverColor": "#00ffff",
            "--iconButtonHoverColor": "#00a6a6",
        },
    },
]


def upgrade(connection):
    """Seed built-in themes"""
    try:
        logger.info("Starting migration 015: Seeding built-in themes")

        # Check if any built-in themes already exist (idempotency)
        result = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM custom_themes
                WHERE is_built_in = 1
            """
            )
        )

        existing_count = result.scalar()

        if existing_count > 0:
            logger.info(
                f"Built-in themes already exist ({existing_count} found) - skipping seed"
            )
            return

        # Insert each built-in theme
        for theme in BUILT_IN_THEMES:
            # Check if this specific theme exists
            existing = connection.execute(
                text(
                    """
                    SELECT id FROM custom_themes
                    WHERE name = :name
                """
                ),
                {"name": theme["name"]},
            ).fetchone()

            if not existing:
                # Use the first admin user or NULL for system themes
                admin_user_result = connection.execute(
                    text("SELECT id FROM users WHERE role = 'ADMIN' LIMIT 1")
                ).fetchone()
                admin_user_id = admin_user_result[0] if admin_user_result else None

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
                logger.info(f"Created built-in theme: {theme['display_name']}")

        logger.info(
            f"Migration 015 completed successfully: {len(BUILT_IN_THEMES)} built-in themes seeded"
        )

    except Exception as e:
        logger.error(f"Migration 015 failed: {e}")
        raise


def downgrade(connection):
    """Remove built-in themes"""
    try:
        logger.info("Starting downgrade of migration 015")

        # Delete all built-in themes
        connection.execute(
            text(
                """
                DELETE FROM custom_themes
                WHERE is_built_in = 1
            """
            )
        )

        logger.info("Migration 015 downgrade completed successfully")

    except Exception as e:
        logger.error(f"Migration 015 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed Built-in Themes Migration")
    parser.add_argument(
        "--downgrade", action="store_true", help="Run downgrade instead of upgrade"
    )

    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
