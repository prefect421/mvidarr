"""
Authentication middleware for MVidarr
Provides central authentication handling and request context setup.
"""

from flask import g, jsonify, redirect, request
from flask import session as flask_session
from flask import url_for
from src.services.audit_service import AuditEventType, AuditService
from src.services.auth_service import AuthService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth.middleware")


class AuthMiddleware:
    """Authentication middleware for Flask application"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize authentication middleware with Flask app"""
        app.before_request(self.load_user)
        app.teardown_appcontext(self.teardown_user)

        # Add authentication context processors
        app.context_processor(self.inject_auth_context)

        # Register authentication error handlers
        app.errorhandler(401)(self.handle_unauthorized)
        app.errorhandler(403)(self.handle_forbidden)

        logger.info("Authentication middleware initialized")

    def load_user(self):
        """Load current user from session before each request"""
        try:
            # Clear any existing user context
            g.current_user = None
            g.is_authenticated = False
            g.user_role = None

            # Check for session token
            session_token = flask_session.get("session_token")
            if session_token:
                user = AuthService.get_user_by_session_token(session_token)
                if user:
                    # Set user context
                    g.current_user = user
                    g.is_authenticated = True
                    g.user_role = user.role

                    # Add user to request for decorators
                    request.current_user = user

                    logger.debug(
                        f"User loaded: {user.username} (Role: {user.role.value})"
                    )
                else:
                    # Invalid session token, clear it
                    flask_session.pop("session_token", None)
                    logger.debug("Invalid session token cleared")

            # Check for API key authentication (future implementation)
            api_key = request.headers.get("X-API-Key")
            if api_key and not g.current_user:
                # TODO: Implement API key authentication
                logger.debug("API key authentication not yet implemented")

        except Exception as e:
            logger.error(f"Error loading user: {e}")
            # Clear session on error
            flask_session.pop("session_token", None)
            g.current_user = None
            g.is_authenticated = False
            g.user_role = None

    def teardown_user(self, exception):
        """Clean up user context after request"""
        pass  # Context automatically cleared by Flask

    def inject_auth_context(self):
        """Inject authentication context into templates"""
        return {
            "current_user": g.get("current_user"),
            "is_authenticated": g.get("is_authenticated", False),
            "user_role": g.get("user_role"),
            "user_can_admin": (
                g.get("current_user").can_access_admin()
                if g.get("current_user")
                else False
            ),
            "user_can_modify": (
                g.get("current_user").can_modify_content()
                if g.get("current_user")
                else False
            ),
            "user_can_delete": (
                g.get("current_user").can_delete_content()
                if g.get("current_user")
                else False
            ),
        }

    def handle_unauthorized(self, error):
        """Handle 401 Unauthorized errors"""
        user = g.get("current_user")

        # Log unauthorized access attempt
        AuditService.log_authorization_event(
            AuditEventType.ACCESS_DENIED,
            "Unauthorized access attempt",
            user=user,
            resource=request.endpoint,
            action="access",
            granted=False,
        )

        if request.is_json or request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": "Authentication required",
                        "code": "AUTH_REQUIRED",
                        "message": "Please log in to access this resource",
                    }
                ),
                401,
            )
        else:
            # Redirect to login page for web interface
            return redirect(url_for("auth.login", next=request.url))

    def handle_forbidden(self, error):
        """Handle 403 Forbidden errors"""
        user = g.get("current_user")

        # Log authorization failure
        AuditService.log_authorization_event(
            AuditEventType.ACCESS_DENIED,
            f"Insufficient permissions for {request.endpoint}",
            user=user,
            resource=request.endpoint,
            action="access",
            granted=False,
        )

        if request.is_json or request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "error": "Insufficient permissions",
                        "code": "INSUFFICIENT_PERMISSIONS",
                        "message": "You do not have permission to access this resource",
                    }
                ),
                403,
            )
        else:
            return (
                jsonify(
                    {
                        "error": "Access denied",
                        "message": "You do not have permission to access this resource",
                    }
                ),
                403,
            )


def require_authentication():
    """Helper function to check if user is authenticated"""
    if not g.get("is_authenticated"):
        return False
    return True


def get_current_user():
    """Helper function to get current authenticated user"""
    return g.get("current_user")


def has_role(required_role):
    """Helper function to check if user has required role"""
    user = g.get("current_user")
    if not user:
        return False
    return user.has_permission(required_role)


def is_admin():
    """Helper function to check if user is admin"""
    user = g.get("current_user")
    if not user:
        return False
    return user.can_access_admin()


def can_modify_content():
    """Helper function to check if user can modify content"""
    user = g.get("current_user")
    if not user:
        return False
    return user.can_modify_content()


def can_delete_content():
    """Helper function to check if user can delete content"""
    user = g.get("current_user")
    if not user:
        return False
    return user.can_delete_content()


# CSRF Protection for state-changing operations
def validate_csrf_token():
    """Validate CSRF token for state-changing operations"""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        session_token = flask_session.get("csrf_token")

        if not token or not session_token or token != session_token:
            AuditService.log_security_event(
                AuditEventType.CSRF_ATTEMPT,
                "CSRF token validation failed",
                severity="WARNING",
            )
            return False
    return True


def generate_csrf_token():
    """Generate and store CSRF token in session"""
    import secrets

    token = secrets.token_urlsafe(32)
    flask_session["csrf_token"] = token
    return token


# Rate limiting helpers
_rate_limit_storage = {}


def check_rate_limit(identifier, max_requests=100, window_seconds=3600):
    """Simple in-memory rate limiting"""
    import time

    current_time = time.time()
    window_start = current_time - window_seconds

    # Clean old entries
    if identifier in _rate_limit_storage:
        _rate_limit_storage[identifier] = [
            timestamp
            for timestamp in _rate_limit_storage[identifier]
            if timestamp > window_start
        ]
    else:
        _rate_limit_storage[identifier] = []

    # Check if limit exceeded
    if len(_rate_limit_storage[identifier]) >= max_requests:
        return False

    # Add current request
    _rate_limit_storage[identifier].append(current_time)
    return True


def log_request_info():
    """Log request information for audit purposes"""
    user = g.get("current_user")

    # Log significant requests (admin, modifications, etc.)
    if request.endpoint and (
        request.endpoint.startswith("admin")
        or request.method in ["POST", "PUT", "DELETE"]
        or request.path.startswith("/api/settings")
    ):
        AuditService.log_event(
            "request_processed",
            f"{request.method} {request.path}",
            user_id=user.id if user else None,
            username=user.username if user else None,
            additional_data={
                "endpoint": request.endpoint,
                "method": request.method,
                "path": request.path,
                "authenticated": g.get("is_authenticated", False),
            },
        )


# Initialize middleware instance
auth_middleware = AuthMiddleware()
