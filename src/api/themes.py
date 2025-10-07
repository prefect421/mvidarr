"""
API endpoints for theme management and customization
"""

import logging
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request, session
from sqlalchemy import or_

from src.database.connection import get_db
from src.database.models import CustomTheme, User

logger = logging.getLogger(__name__)

themes_bp = Blueprint("themes", __name__)


def extract_built_in_theme_data():
    """Extract hardcoded built-in theme data for merging with database records"""
    return {
        "default": {
            # Default theme variables
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
        "cyber": {
            # Cyber theme variables with updated button color
            "--bg-primary": "#000000",
            "--bg-secondary": "#0d1117",
            "--bg-tertiary": "#161b22",
            "--text-primary": "#00fff7",
            "--text-secondary": "#7dd3fc",
            "--text-accent": "#00fff7",
            "--btn-primary-bg": "#78f5fc",
            "--btn-primary-text": "#000000",
            "--border-primary": "#00fff7",
            "--success": "#00ff00",
            "--warning": "#ffff00",
            "--error": "#ff0000",
            "--info": "#00ffff",
            "--sidebar-bg": "#000000",
            "--search-bar-bg": "#161b22",
            "--top-bar-bg": "#0d1117",
        },
        # Add other themes as needed when they require updates
    }


def simple_auth_required(f):
    """
    Simple authentication decorator compatible with MVidarr's simple auth system
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated using simple auth session
        if not session.get("authenticated", False):
            return (
                jsonify(
                    {"error": "Authentication required", "login_url": "/simple-login"}
                ),
                401,
            )

        # Get username from session and find user
        username = session.get("username", "admin")

        try:
            with get_db() as db_session:
                user = db_session.query(User).filter_by(username=username).first()
                if not user:
                    # Create a mock admin user for compatibility
                    class MockUser:
                        def __init__(self, username):
                            self.id = 1
                            self.username = username
                            self.is_admin = True

                    user = MockUser(username)

                # Add user to request context for compatibility
                request.current_user = user
                return f(*args, **kwargs)

        except Exception as e:
            logger.error(f"Error in simple auth: {e}")

            # Fallback to mock user
            class MockUser:
                def __init__(self, username):
                    self.id = 1
                    self.username = username
                    self.is_admin = True

            request.current_user = MockUser(username)
            return f(*args, **kwargs)

    return decorated_function


@themes_bp.route("", methods=["GET"])
@simple_auth_required
def get_themes():
    """Get all available themes (built-in and custom)"""
    try:
        user_id = request.current_user.id
        logger.info(f"Loading themes for user {user_id}")

        with get_db() as session:
            # Get all themes that are either public, built-in, or created by the current user
            try:
                themes = (
                    session.query(CustomTheme)
                    .filter(
                        or_(
                            CustomTheme.is_public == True,
                            CustomTheme.is_built_in == True,
                            CustomTheme.created_by == user_id,
                        )
                    )
                    .all()
                )
                logger.info(f"Found {len(themes)} custom themes in database")
            except Exception as db_error:
                logger.error(f"Database error querying themes: {db_error}")
                # Continue with empty themes list if database query fails
                themes = []

            # Built-in CSS themes (these are loaded from CSS files, not database)
            built_in_themes = [
                {
                    "id": "default",
                    "name": "default",
                    "display_name": "Default",
                    "description": "Default MVidarr theme",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "cyber",
                    "name": "cyber",
                    "display_name": "Cyber",
                    "description": "Cyberpunk-inspired theme",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "vaporwave",
                    "name": "vaporwave",
                    "display_name": "VaporWave",
                    "description": "Synthwave/vaporwave aesthetic",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "tardis",
                    "name": "tardis",
                    "display_name": "TARDIS",
                    "description": "Its bigger on the inside",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "punk_77",
                    "name": "punk_77",
                    "display_name": "Punk 77",
                    "description": "Raw punk rock aesthetic inspired by aggressive colors on early Punk Albums",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "mtv",
                    "name": "mtv",
                    "display_name": "MTV",
                    "description": "Early 80s MTV neon aesthetic with electric colors and bold contrasts",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
                {
                    "id": "lcars",
                    "name": "lcars",
                    "display_name": "LCARS",
                    "description": "Step into the 23rd century with this Color way.",
                    "is_built_in": True,
                    "is_public": True,
                    "theme_data": None,
                    "light_theme_data": None,
                },
            ]

            # Convert custom themes to dict format safely
            custom_themes = []
            custom_theme_names = (
                set()
            )  # Track which built-in themes have been customized

            # Get the latest hardcoded built-in theme definitions
            hardcoded_themes = extract_built_in_theme_data()

            for theme in themes:
                try:
                    theme_dict = theme.to_dict()

                    # If this is a built-in theme with a database record, merge with latest hardcoded definition
                    if theme.is_built_in and theme.name in hardcoded_themes:
                        hardcoded_data = hardcoded_themes[theme.name]
                        # Update the database theme with any new properties from hardcoded definition
                        if theme.theme_data:
                            # Merge hardcoded updates into existing theme data
                            updated_theme_data = hardcoded_data.copy()
                            updated_theme_data.update(theme.theme_data)
                            theme_dict["theme_data"] = updated_theme_data
                        else:
                            # Use hardcoded data if no database theme_data exists
                            theme_dict["theme_data"] = hardcoded_data

                    custom_themes.append(theme_dict)
                    if theme.is_built_in:
                        custom_theme_names.add(theme.name)
                except Exception as theme_error:
                    logger.error(
                        f"Error converting theme {theme.id} to dict: {theme_error}"
                    )
                    continue

            # Filter out built-in themes that have database records (avoid duplicates)
            filtered_built_in_themes = [
                theme
                for theme in built_in_themes
                if theme["name"] not in custom_theme_names
            ]

            logger.info(f"Successfully converted {len(custom_themes)} custom themes")
            logger.info(
                f"Filtered {len(filtered_built_in_themes)} built-in themes (avoiding {len(custom_theme_names)} duplicates)"
            )

            all_themes = filtered_built_in_themes + custom_themes
            logger.info(f"Returning {len(all_themes)} total themes")

            return jsonify({"themes": all_themes, "total": len(all_themes)})

    except Exception as e:
        logger.error(f"Error loading themes: {e}")
        return jsonify({"error": "Failed to load themes", "details": str(e)}), 500


@themes_bp.route("", methods=["POST"])
@simple_auth_required
def create_theme():
    """Create a new custom theme"""
    try:
        data = request.get_json()
        user_id = request.current_user.id

        # Validate required fields
        if not data.get("name"):
            return jsonify({"error": "Theme name is required"}), 400
        if not data.get("display_name"):
            return jsonify({"error": "Display name is required"}), 400
        if not data.get("theme_data"):
            return jsonify({"error": "Theme data is required"}), 400

        with get_db() as session:
            # Check if theme name already exists
            existing = session.query(CustomTheme).filter_by(name=data["name"]).first()
            if existing:
                return jsonify({"error": "Theme name already exists"}), 409

            # Create new theme
            theme = CustomTheme(
                name=data["name"],
                display_name=data["display_name"],
                description=data.get("description", ""),
                created_by=user_id,
                is_public=data.get("is_public", False),
                is_built_in=False,
                theme_data=data["theme_data"],
                light_theme_data=data.get("light_theme_data"),
            )

            session.add(theme)
            session.commit()

            logger.info(f"Created theme '{theme.name}' by user {user_id}")
            return jsonify(theme.to_dict()), 201

    except Exception as e:
        logger.error(f"Error creating theme: {e}")
        return jsonify({"error": "Failed to create theme", "details": str(e)}), 500


@themes_bp.route("/<int:theme_id>", methods=["GET"])
@simple_auth_required
def get_theme(theme_id):
    """Get a specific theme by ID"""
    try:
        user_id = request.current_user.id

        with get_db() as session:
            theme = session.query(CustomTheme).filter_by(id=theme_id).first()
            if not theme:
                return jsonify({"error": "Theme not found"}), 404

            # Check permissions
            if (
                not theme.is_public
                and not theme.is_built_in
                and theme.created_by != user_id
            ):
                return jsonify({"error": "Access denied"}), 403

            return jsonify(theme.to_dict())

    except Exception as e:
        logger.error(f"Error getting theme {theme_id}: {e}")
        return jsonify({"error": "Failed to get theme", "details": str(e)}), 500


@themes_bp.route("/<int:theme_id>", methods=["PUT"])
@simple_auth_required
def update_theme(theme_id):
    """Update a custom theme"""
    try:
        data = request.get_json()
        user_id = request.current_user.id

        with get_db() as session:
            theme = session.query(CustomTheme).filter_by(id=theme_id).first()
            if not theme:
                return jsonify({"error": "Theme not found"}), 404

            # Check permissions - only creator can edit (unless admin)
            if theme.created_by != user_id and not getattr(
                request.current_user, "is_admin", False
            ):
                return jsonify({"error": "Access denied"}), 403

            # Update theme fields if provided
            if "display_name" in data:
                theme.display_name = data["display_name"]
            if "description" in data:
                theme.description = data["description"]
            if "theme_data" in data:
                theme.theme_data = data["theme_data"]
            if "light_theme_data" in data:
                theme.light_theme_data = data["light_theme_data"]
            if "is_public" in data:
                theme.is_public = data["is_public"]

            session.commit()
            logger.info(f"Updated theme '{theme.name}' by user {user_id}")
            return jsonify(theme.to_dict())

    except Exception as e:
        logger.error(f"Error updating theme {theme_id}: {e}")
        return jsonify({"error": "Failed to update theme", "details": str(e)}), 500


@themes_bp.route("/<int:theme_id>", methods=["DELETE"])
@simple_auth_required
def delete_theme(theme_id):
    """Delete a custom theme"""
    try:
        user_id = request.current_user.id

        with get_db() as session:
            theme = session.query(CustomTheme).filter_by(id=theme_id).first()
            if not theme:
                return jsonify({"error": "Theme not found"}), 404

            # Check permissions - only creator can delete (unless admin)
            if theme.created_by != user_id and not getattr(
                request.current_user, "is_admin", False
            ):
                return jsonify({"error": "Access denied"}), 403

            # Don't allow deleting built-in themes
            if theme.is_built_in:
                return jsonify({"error": "Cannot delete built-in themes"}), 400

            theme_name = theme.name
            session.delete(theme)
            session.commit()

            logger.info(f"Deleted theme '{theme_name}' by user {user_id}")
            return jsonify({"message": "Theme deleted successfully"})

    except Exception as e:
        logger.error(f"Error deleting theme {theme_id}: {e}")
        return jsonify({"error": "Failed to delete theme", "details": str(e)}), 500


@themes_bp.route("/<int:theme_id>/duplicate", methods=["POST"])
@simple_auth_required
def duplicate_theme(theme_id):
    """Duplicate an existing theme"""
    try:
        data = request.get_json()
        user_id = request.current_user.id

        with get_db() as session:
            original_theme = session.query(CustomTheme).filter_by(id=theme_id).first()
            if not original_theme:
                return jsonify({"error": "Theme not found"}), 404

            # Check permissions for original theme
            if (
                not original_theme.is_public
                and not original_theme.is_built_in
                and original_theme.created_by != user_id
            ):
                return jsonify({"error": "Access denied"}), 403

            # Get new theme name from request or generate one
            new_name = data.get("name", f"{original_theme.name}_copy")
            new_display_name = data.get(
                "display_name", f"{original_theme.display_name} (Copy)"
            )

            # Check if new name already exists
            existing = session.query(CustomTheme).filter_by(name=new_name).first()
            if existing:
                return jsonify({"error": "Theme name already exists"}), 409

            # Create duplicate
            new_theme = CustomTheme(
                name=new_name,
                display_name=new_display_name,
                description=data.get("description", original_theme.description),
                created_by=user_id,
                is_public=data.get("is_public", False),
                is_built_in=False,  # Duplicates are never built-in
                theme_data=(
                    original_theme.theme_data.copy()
                    if original_theme.theme_data
                    else {}
                ),
                light_theme_data=(
                    original_theme.light_theme_data.copy()
                    if original_theme.light_theme_data
                    else None
                ),
            )

            session.add(new_theme)
            session.commit()

            logger.info(
                f"Duplicated theme '{original_theme.name}' as '{new_name}' by user {user_id}"
            )
            return jsonify(new_theme.to_dict()), 201

    except Exception as e:
        logger.error(f"Error duplicating theme {theme_id}: {e}")
        return jsonify({"error": "Failed to duplicate theme", "details": str(e)}), 500


@themes_bp.route("/apply", methods=["POST"])
@simple_auth_required
def apply_theme():
    """Apply a theme to the current user"""
    try:
        data = request.get_json()
        theme_name = data.get("theme_name")

        if not theme_name:
            return jsonify({"error": "Theme name is required"}), 400

        # Save theme preference using settings service
        try:
            from src.services.settings_service import SettingsService

            success = SettingsService.set("ui_theme", theme_name)
            if success:
                # Don't try to log with request.current_user.id as it causes SQLAlchemy session errors
                logger.info(
                    f"Applied theme '{theme_name}' for user {getattr(request.current_user, 'username', 'unknown')}"
                )
                return jsonify(
                    {"message": f"Theme '{theme_name}' applied successfully"}
                )
            else:
                logger.error(
                    f"Settings service failed to save theme preference for '{theme_name}'"
                )
                return jsonify({"error": "Failed to save theme preference"}), 500
        except Exception as settings_error:
            # Check if it's the known SQLAlchemy session error but theme was actually saved
            error_str = str(settings_error)
            if "is not bound to a Session" in error_str:
                logger.warning(
                    f"SQLAlchemy session error after successful theme save: {settings_error}"
                )
                # Check if theme was actually saved despite the error
                try:
                    from src.services.settings_service import SettingsService

                    current_theme = SettingsService.get("ui_theme", "default")
                    if current_theme == theme_name:
                        logger.info(
                            f"Theme '{theme_name}' was successfully saved despite session error"
                        )
                        return jsonify(
                            {"message": f"Theme '{theme_name}' applied successfully"}
                        )
                except Exception:
                    pass

            logger.error(f"Error saving theme preference: {settings_error}")
            return jsonify({"error": "Failed to save theme preference"}), 500

    except Exception as e:
        logger.error(f"Error applying theme: {e}")
        return jsonify({"error": "Failed to apply theme", "details": str(e)}), 500


@themes_bp.route("/current", methods=["GET"])
@simple_auth_required
def get_current_theme():
    """Get the currently applied theme"""
    try:
        from src.services.settings_service import SettingsService

        current_theme = SettingsService.get("ui_theme", "default")
        return jsonify({"current_theme": current_theme})
    except Exception as e:
        logger.error(f"Error getting current theme: {e}")
        return jsonify({"error": "Failed to get current theme", "details": str(e)}), 500


# Note: Built-in theme extraction/editing functionality has been simplified
# Old LCARS themes (DS9, Voy, TNG-E) have been removed
# Built-in themes now primarily use CSS files rather than hardcoded definitions


@themes_bp.route("/built-in/<theme_name>/extract", methods=["POST"])
@simple_auth_required
def extract_built_in_theme(theme_name):
    """Extract CSS variables from built-in themes (simplified version)"""
    try:
        # Simplified built-in theme definitions - only the essential ones
        built_in_themes = {
            "default": {
                # Default theme variables
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
                # Extended variables
                "--shadow": "#000000",
                "--shadow-hover": "#000000",
                "--border-focus-shadow": "#4a9eff",
                "--modalBackgroundColor": "#2d2d2d",
                "--modalBackdropBackgroundColor": "#000000",
                "--modal-overlay": "#00000080",
                "--modalCloseButtonHoverColor": "#ff0000",
                "--inputHoverBackgroundColor": "#3a3a3a",
                "--inputSelectedBackgroundColor": "#4a9eff",
                "--inputReadOnlyBackgroundColor": "#1a1a1a",
                "--inputErrorBorderColor": "#dc3545",
                "--inputWarningBorderColor": "#ffc107",
                "--menuItemColor": "#ffffff",
                "--menuItemHoverBackgroundColor": "#4a9eff",
                "--popoverBodyBackgroundColor": "#2d2d2d",
                "--popoverTitleBackgroundColor": "#1a1a1a",
                "--disabledColor": "#666666",
                "--helpTextColor": "#888888",
                "--linkHoverColor": "#6bb6ff",
                "--iconButtonHoverColor": "#4a9eff",
            },
            "cyber": {
                # Cyber theme variables
                "--bg-primary": "#000000",
                "--bg-secondary": "#0d1117",
                "--bg-tertiary": "#161b22",
                "--text-primary": "#00fff7",
                "--text-secondary": "#7dd3fc",
                "--text-accent": "#00fff7",
                "--btn-primary-bg": "#78f5fc",
                "--btn-primary-text": "#000000",
                "--border-primary": "#00fff7",
                "--success": "#00ff00",
                "--warning": "#ffff00",
                "--error": "#ff0000",
                "--info": "#00ffff",
                "--sidebar-bg": "#000000",
                "--search-bar-bg": "#161b22",
                "--top-bar-bg": "#0d1117",
                # Extended variables
                "--shadow": "#00fff720",
                "--shadow-hover": "#00fff740",
                "--border-focus-shadow": "#00fff7",
                "--modalBackgroundColor": "#0d1117",
                "--modalBackdropBackgroundColor": "#000000",
                "--modal-overlay": "#00000080",
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
            "vaporwave": {
                # VaporWave theme variables
                "--bg-primary": "#1a0d26",
                "--bg-secondary": "#2d1b3d",
                "--bg-tertiary": "#3d2852",
                "--text-primary": "#ff3cac",
                "--text-secondary": "#d4a5f2",
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
                # Extended variables
                "--shadow": "#ff3cac20",
                "--shadow-hover": "#ff3cac40",
                "--border-focus-shadow": "#ff3cac",
                "--modalBackgroundColor": "#2d1b3d",
                "--modalBackdropBackgroundColor": "#1a0d26",
                "--modal-overlay": "#00000080",
                "--modalCloseButtonHoverColor": "#ff073a",
                "--inputHoverBackgroundColor": "#3d2852",
                "--inputSelectedBackgroundColor": "#ff3cac",
                "--inputReadOnlyBackgroundColor": "#1a0d26",
                "--inputErrorBorderColor": "#ff073a",
                "--inputWarningBorderColor": "#ffee00",
                "--menuItemColor": "#ff3cac",
                "--menuItemHoverBackgroundColor": "#3d2852",
                "--popoverBodyBackgroundColor": "#2d1b3d",
                "--popoverTitleBackgroundColor": "#1a0d26",
                "--disabledColor": "#666666",
                "--helpTextColor": "#d4a5f2",
                "--linkHoverColor": "#ff3cac",
                "--iconButtonHoverColor": "#ff3cac",
            },
            "tardis": {
                # TARDIS theme variables - Doctor Who TARDIS aesthetic
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
                # Extended variables for modal and UI consistency
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
            "punk_77": {
                # Punk 77 theme variables - Raw punk rock aesthetic
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
                # Extended variables for modal and UI consistency
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
            "mtv": {
                # MTV theme variables - Early 80s MTV neon aesthetic
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
                # Extended variables for modal and UI consistency
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
            "lcars": {
                # LCARS theme variables - Star Trek 23rd century interface
                "--bg-primary": "#000000",
                "--bg-secondary": "#3d66ab",
                "--bg-tertiary": "#00468c",
                "--sidebar-bg": "#daa520",
                "--sidebar-bg-secondary": "#c2951d",
                "--search-bar-bg": "#daa520",
                "--bg-modal": "#00aaaa",
                "--bg-card": "#7937b5",
                "--bg-hover": "#404040",
                "--top-bar-bg": "#daa520",
                "--text-primary": "#ffffff",
                "--text-secondary": "#ffffff",
                "--text-accent": "#000000",
                "--text-muted": "#000000",
                "--text-inverse": "#ffffff",
                "--btn-primary-bg": "#ff9900",
                "--btn-primary-text": "#ffffff",
                "--btn-primary-hover": "#3a8eef",
                "--btn-secondary-bg": "#666666",
                "--btn-secondary-text": "#ffffff",
                "--btn-secondary-hover": "#777777",
                "--btn-danger-bg": "#dc3545",
                "--btn-danger-text": "#ffffff",
                "--btn-danger-hover": "#c82333",
                "--border-primary": "#000000",
                "--border-secondary": "#000000",
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
                "--nav-bg": "#06aa92",
                "--nav-text": "#cccccc",
                "--nav-hover": "#0c5a94",
                "--nav-active": "#4a9eff",
                "--accent-secondary": "#0099cc",
                "--accent-dark": "#007799",
                "--shadow": "#000000",
                "--shadow-hover": "#282828",
                "--border-focus-shadow": "#000000",
                "--modalBackgroundColor": "#26a269",
                "--modalBackdropBackgroundColor": "#c64600",
                "--modal-overlay": "#1a5fb4",
                "--modalCloseButtonHoverColor": "#ff0000",
                "--inputHoverBackgroundColor": "#3a3a3a",
                "--inputSelectedBackgroundColor": "#4a9eff",
                "--inputReadOnlyBackgroundColor": "#1a1a1a",
                "--inputErrorBorderColor": "#dc3545",
                "--inputWarningBorderColor": "#ffc107",
                "--menuItemColor": "#ffffff",
                "--menuItemHoverBackgroundColor": "#4a9eff",
                "--popoverBodyBackgroundColor": "#2d2d2d",
                "--popoverTitleBackgroundColor": "#a51d2d",
                "--disabledColor": "#666666",
                "--helpTextColor": "#888888",
                "--linkHoverColor": "#6bb6ff",
                "--iconButtonHoverColor": "#4a9eff",
            },
        }

        if theme_name not in built_in_themes:
            return jsonify({"error": "Built-in theme not found"}), 404

        return jsonify(
            {
                "theme_name": theme_name,
                "variables": built_in_themes[theme_name],
                "light_variables": {},  # Simplified - no light variants for now
            }
        )

    except Exception as e:
        logger.error(f"Error extracting built-in theme {theme_name}: {e}")
        return jsonify({"error": "Failed to extract theme", "details": str(e)}), 500


@themes_bp.route("/built-in/<theme_name>", methods=["PUT"])
@simple_auth_required
def update_built_in_theme(theme_name):
    """Update a built-in theme by creating or updating its database record"""
    try:
        user_id = (
            request.current_user.id if hasattr(request.current_user, "id") else None
        )
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate that the theme_name exists in our built-in themes
        built_in_theme_names = [
            "default",
            "cyber",
            "vaporwave",
            "tardis",
            "punk77",
            "mtv",
            "lcars",
        ]
        if theme_name not in built_in_theme_names:
            return jsonify({"error": f"Built-in theme '{theme_name}' not found"}), 404

        with get_db() as session:
            # Check if a database record already exists for this built-in theme
            existing_theme = (
                session.query(CustomTheme)
                .filter_by(name=theme_name, is_built_in=True)
                .first()
            )

            if existing_theme:
                # Update existing theme
                if "theme_data" in data:
                    existing_theme.theme_data = data["theme_data"]
                if "display_name" in data:
                    existing_theme.display_name = data["display_name"]
                if "description" in data:
                    existing_theme.description = data["description"]

                session.commit()
                logger.info(f"Updated built-in theme '{theme_name}' in database")
                return jsonify(existing_theme.to_dict())
            else:
                # Create new database record for this built-in theme
                new_theme = CustomTheme(
                    name=theme_name,
                    display_name=data.get("display_name", theme_name.title()),
                    description=data.get(
                        "description", f"Customized {theme_name} theme"
                    ),
                    created_by=user_id,
                    is_public=True,
                    is_built_in=True,
                    theme_data=data.get("theme_data", {}),
                )

                session.add(new_theme)
                session.commit()
                logger.info(
                    f"Created database record for built-in theme '{theme_name}'"
                )
                return jsonify(new_theme.to_dict())

    except Exception as e:
        logger.error(f"Error updating built-in theme {theme_name}: {e}")
        return jsonify({"error": "Failed to update theme", "details": str(e)}), 500


@themes_bp.route("/<int:theme_id>/export", methods=["GET"])
@simple_auth_required
def export_theme(theme_id):
    """Export a theme as a JSON file"""
    try:
        user_id = (
            request.current_user.id if hasattr(request.current_user, "id") else None
        )
        username = getattr(request.current_user, "username", "unknown")

        with get_db() as session:
            theme = session.query(CustomTheme).filter_by(id=theme_id).first()
            if not theme:
                return jsonify({"error": "Theme not found"}), 404

            # Check permissions
            if (
                not theme.is_public
                and not theme.is_built_in
                and theme.created_by != user_id
            ):
                return jsonify({"error": "Access denied"}), 403

            # Create export data
            export_data = {
                "mvidarr_theme_export": {
                    "version": "1.0",
                    "exported_at": datetime.utcnow().isoformat() + "Z",
                    "exported_by": username,
                },
                "theme": {
                    "name": theme.name,
                    "display_name": theme.display_name,
                    "description": theme.description or "",
                    "is_public": theme.is_public,
                    "theme_data": theme.theme_data,
                    "light_theme_data": theme.light_theme_data,
                },
            }

            # Create response with appropriate headers for file download
            import json

            from flask import make_response

            response_data = json.dumps(export_data, indent=2, ensure_ascii=False)
            response = make_response(response_data)
            response.headers["Content-Type"] = "application/json"
            response.headers["Content-Disposition"] = (
                f'attachment; filename="{theme.name}_theme.json"'
            )

            logger.info(f"Exported theme '{theme.name}' by user {username}")
            return response

    except Exception as e:
        logger.error(f"Error exporting theme {theme_id}: {e}")
        return jsonify({"error": "Failed to export theme", "details": str(e)}), 500


@themes_bp.route("/export/all", methods=["GET"])
@simple_auth_required
def export_all_themes():
    """Export all accessible themes as a JSON file"""
    try:
        user_id = (
            request.current_user.id if hasattr(request.current_user, "id") else None
        )
        username = getattr(request.current_user, "username", "unknown")

        with get_db() as session:
            # Get all themes that are either public, built-in, or created by the current user
            themes = (
                session.query(CustomTheme)
                .filter(
                    or_(
                        CustomTheme.is_public == True,
                        CustomTheme.is_built_in == True,
                        CustomTheme.created_by == user_id,
                    )
                )
                .all()
            )

            # Create export data
            export_data = {
                "mvidarr_theme_export": {
                    "version": "1.0",
                    "exported_at": datetime.utcnow().isoformat() + "Z",
                    "exported_by": username,
                    "theme_count": len(themes),
                },
                "themes": [],
            }

            for theme in themes:
                theme_data = {
                    "name": theme.name,
                    "display_name": theme.display_name,
                    "description": theme.description or "",
                    "is_public": theme.is_public,
                    "theme_data": theme.theme_data,
                    "light_theme_data": theme.light_theme_data,
                }
                export_data["themes"].append(theme_data)

            # Create response with appropriate headers for file download
            import json

            from flask import make_response

            response_data = json.dumps(export_data, indent=2, ensure_ascii=False)
            response = make_response(response_data)
            response.headers["Content-Type"] = "application/json"
            response.headers["Content-Disposition"] = (
                f'attachment; filename="mvidarr_themes_export.json"'
            )

            logger.info(f"Exported {len(themes)} themes by user {username}")
            return response

    except Exception as e:
        logger.error(f"Error exporting all themes: {e}")
        return jsonify({"error": "Failed to export themes", "details": str(e)}), 500


@themes_bp.route("/import", methods=["POST"])
@simple_auth_required
def import_themes():
    """Import themes from a JSON file"""
    try:
        user_id = request.current_user.id if hasattr(request.current_user, "id") else 1
        username = getattr(request.current_user, "username", "unknown")

        # Get the uploaded file or JSON data
        if request.is_json:
            import_data = request.get_json()
        elif "file" in request.files:
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            if not file.filename.endswith(".json"):
                return jsonify({"error": "File must be a JSON file"}), 400

            try:
                import json

                import_data = json.loads(file.read().decode("utf-8"))
            except json.JSONDecodeError as e:
                return jsonify({"error": f"Invalid JSON file: {str(e)}"}), 400
        else:
            return jsonify({"error": "No import data provided"}), 400

        # Validate import data structure
        if not isinstance(import_data, dict):
            return jsonify({"error": "Invalid import data format"}), 400

        # Check if it's a MVidarr theme export file
        if "mvidarr_theme_export" not in import_data:
            return jsonify({"error": "Not a valid MVidarr theme export file"}), 400

        # Determine if it's a single theme or multiple themes
        themes_to_import = []
        if "theme" in import_data:
            # Single theme export
            themes_to_import = [import_data["theme"]]
        elif "themes" in import_data:
            # Multiple themes export
            themes_to_import = import_data["themes"]
        else:
            return jsonify({"error": "No themes found in import data"}), 400

        # Validate and import themes
        imported_themes = []
        skipped_themes = []
        errors = []

        with get_db() as session:
            for theme_data in themes_to_import:
                try:
                    # Validate required fields
                    if not all(
                        key in theme_data
                        for key in ["name", "display_name", "theme_data"]
                    ):
                        errors.append(
                            f"Theme missing required fields: {theme_data.get('name', 'Unknown')}"
                        )
                        continue

                    # Check if theme name already exists
                    existing = (
                        session.query(CustomTheme)
                        .filter_by(name=theme_data["name"])
                        .first()
                    )
                    if existing:
                        skipped_themes.append(theme_data["name"])
                        continue

                    # Validate theme_data structure
                    if not isinstance(theme_data["theme_data"], dict):
                        errors.append(
                            f"Invalid theme_data for theme: {theme_data['name']}"
                        )
                        continue

                    # Create new theme
                    new_theme = CustomTheme(
                        name=theme_data["name"],
                        display_name=theme_data["display_name"],
                        description=theme_data.get("description", ""),
                        created_by=user_id,
                        is_public=theme_data.get("is_public", False),
                        is_built_in=False,  # Imported themes are never built-in
                        theme_data=theme_data["theme_data"],
                        light_theme_data=theme_data.get("light_theme_data"),
                    )

                    session.add(new_theme)
                    imported_themes.append(theme_data["name"])

                except Exception as theme_error:
                    errors.append(
                        f"Error importing theme {theme_data.get('name', 'Unknown')}: {str(theme_error)}"
                    )

            # Commit all imported themes
            if imported_themes:
                session.commit()

        # Prepare response
        response_data = {
            "success": True,
            "imported_count": len(imported_themes),
            "skipped_count": len(skipped_themes),
            "error_count": len(errors),
            "imported_themes": imported_themes,
            "skipped_themes": skipped_themes,
            "errors": errors,
        }

        if errors:
            response_data["message"] = f"Import completed with {len(errors)} errors"
        elif skipped_themes:
            response_data["message"] = (
                f"Import completed. {len(skipped_themes)} themes skipped (already exist)"
            )
        else:
            response_data["message"] = (
                f"Successfully imported {len(imported_themes)} themes"
            )

        logger.info(
            f"Theme import by user {username}: {len(imported_themes)} imported, {len(skipped_themes)} skipped, {len(errors)} errors"
        )
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error importing themes: {e}")
        return jsonify({"error": "Failed to import themes", "details": str(e)}), 500


@themes_bp.route("/import/validate", methods=["POST"])
@simple_auth_required
def validate_import():
    """Validate a theme import file without actually importing"""
    try:
        # Get the uploaded file or JSON data
        if request.is_json:
            import_data = request.get_json()
        elif "file" in request.files:
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            if not file.filename.endswith(".json"):
                return jsonify({"error": "File must be a JSON file"}), 400

            try:
                import json

                import_data = json.loads(file.read().decode("utf-8"))
            except json.JSONDecodeError as e:
                return jsonify({"error": f"Invalid JSON file: {str(e)}"}), 400
        else:
            return jsonify({"error": "No import data provided"}), 400

        # Validate import data structure
        if not isinstance(import_data, dict):
            return jsonify({"error": "Invalid import data format", "valid": False}), 400

        # Check if it's a MVidarr theme export file
        if "mvidarr_theme_export" not in import_data:
            return (
                jsonify(
                    {"error": "Not a valid MVidarr theme export file", "valid": False}
                ),
                400,
            )

        # Determine if it's a single theme or multiple themes
        themes_to_validate = []
        if "theme" in import_data:
            themes_to_validate = [import_data["theme"]]
        elif "themes" in import_data:
            themes_to_validate = import_data["themes"]
        else:
            return (
                jsonify({"error": "No themes found in import data", "valid": False}),
                400,
            )

        # Validate themes
        valid_themes = []
        invalid_themes = []
        existing_themes = []
        validation_errors = []

        with get_db() as session:
            for theme_data in themes_to_validate:
                theme_name = theme_data.get("name", "Unknown")

                try:
                    # Validate required fields
                    if not all(
                        key in theme_data
                        for key in ["name", "display_name", "theme_data"]
                    ):
                        invalid_themes.append(theme_name)
                        validation_errors.append(
                            f"Theme '{theme_name}' missing required fields"
                        )
                        continue

                    # Check if theme name already exists
                    existing = (
                        session.query(CustomTheme)
                        .filter_by(name=theme_data["name"])
                        .first()
                    )
                    if existing:
                        existing_themes.append(theme_name)
                        continue

                    # Validate theme_data structure
                    if not isinstance(theme_data["theme_data"], dict):
                        invalid_themes.append(theme_name)
                        validation_errors.append(
                            f"Theme '{theme_name}' has invalid theme_data structure"
                        )
                        continue

                    # Theme is valid
                    valid_themes.append(
                        {
                            "name": theme_name,
                            "display_name": theme_data["display_name"],
                            "description": theme_data.get("description", ""),
                        }
                    )

                except Exception as theme_error:
                    invalid_themes.append(theme_name)
                    validation_errors.append(
                        f"Error validating theme '{theme_name}': {str(theme_error)}"
                    )

        # Prepare response
        response_data = {
            "valid": len(validation_errors) == 0,
            "export_info": import_data.get("mvidarr_theme_export", {}),
            "total_themes": len(themes_to_validate),
            "valid_themes_count": len(valid_themes),
            "invalid_themes_count": len(invalid_themes),
            "existing_themes_count": len(existing_themes),
            "valid_themes": valid_themes,
            "invalid_themes": invalid_themes,
            "existing_themes": existing_themes,
            "validation_errors": validation_errors,
        }

        if validation_errors:
            response_data["message"] = (
                f"Validation failed with {len(validation_errors)} errors"
            )
        elif existing_themes:
            response_data["message"] = (
                f"Validation passed. {len(existing_themes)} themes already exist and will be skipped"
            )
        else:
            response_data["message"] = (
                f"Validation passed. All {len(valid_themes)} themes can be imported"
            )

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error validating import: {e}")
        return jsonify({"error": "Failed to validate import", "details": str(e)}), 500
