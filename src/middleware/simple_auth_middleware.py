"""
Simple authentication middleware for single-user system
"""

from functools import wraps

from flask import jsonify, redirect, request, url_for

from src.services.settings_service import SettingsService
from src.services.simple_auth_service import SimpleAuthService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.simple_auth.middleware")


def auth_required(f):
    """
    Decorator to require authentication for routes
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if authentication is required
        require_auth = SettingsService.get_bool("require_authentication", False)

        if not require_auth:
            return f(*args, **kwargs)

        # Check if user is authenticated
        if not SimpleAuthService.is_authenticated():
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            else:
                return redirect(url_for("simple_auth.login_page"))

        return f(*args, **kwargs)

    return decorated_function


def init_simple_auth_middleware(app):
    """
    Initialize simple authentication middleware
    """

    @app.before_request
    def check_authentication():
        """
        Check authentication for all requests
        """
        # Skip authentication check for login/logout routes
        if request.endpoint in [
            "simple_auth.login_page",
            "simple_auth.login",
            "simple_auth.logout",
        ]:
            return

        # Skip authentication check for static files
        if request.path.startswith("/static/"):
            return

        # Skip authentication check for subtitle files (needed for HTML5 video player)
        if "/subtitles/" in request.path:
            return

        # Skip authentication check for endpoints marked as public
        if request.endpoint:
            from flask import current_app

            endpoint_func = current_app.view_functions.get(request.endpoint)
            if endpoint_func and hasattr(endpoint_func, "_auth_protected"):
                return

        # Check if authentication is required
        require_auth = SettingsService.get_bool("require_authentication", False)

        if not require_auth:
            return

        # Initialize default credentials if they don't exist
        username, has_credentials = SimpleAuthService.get_credentials()
        if not has_credentials:
            (
                created,
                username,
                password,
                message,
            ) = SimpleAuthService.initialize_default_credentials()
            if created:
                logger.info("Default credentials initialized automatically")

        # Check if user is authenticated
        if not SimpleAuthService.is_authenticated():
            # Allow access to auth check endpoint for frontend
            if request.path == "/auth/check":
                return

            if request.is_json or request.path.startswith("/api/"):
                # Return JSON response for API requests
                return (
                    jsonify(
                        {"error": "Authentication required", "redirect": "/auth/login"}
                    ),
                    401,
                )
            else:
                # Redirect to login page for web requests
                return redirect(url_for("simple_auth.login_page"))

    logger.info("Simple authentication middleware initialized")


def get_current_user():
    """
    Get current authenticated user
    Returns username if authenticated, None otherwise
    """
    return SimpleAuthService.get_current_username()


# Decorator for protecting routes
def login_required(f):
    """
    Simple login required decorator
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        require_auth = SettingsService.get_bool("require_authentication", False)

        if require_auth and not SimpleAuthService.is_authenticated():
            if request.is_json:
                return jsonify({"error": "Login required"}), 401
            else:
                return redirect(url_for("simple_auth.login_page"))

        return f(*args, **kwargs)

    return decorated_function
