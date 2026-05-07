"""
Authentication and authorization decorators for MVidarr
"""

from functools import wraps

from flask import jsonify, redirect, request
from flask import session as flask_session
from flask import url_for

from src.database.models import UserRole
from src.services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    AuthService,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth.decorators")


def login_required(f):
    """
    Decorator to require user authentication

    Usage:
        @login_required
        def protected_route():
            # User is guaranteed to be authenticated
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user = AuthService.require_authentication()
            # Add user to request context
            request.current_user = user
            return f(*args, **kwargs)
        except AuthenticationError:
            if request.is_json:
                return (
                    jsonify(
                        {"error": "Authentication required", "code": "AUTH_REQUIRED"}
                    ),
                    401,
                )
            else:
                return redirect(url_for("auth.login"))

    return decorated_function


def role_required(required_role: UserRole):
    """
    Decorator to require specific user role

    Args:
        required_role: Minimum required role

    Usage:
        @role_required(UserRole.ADMIN)
        def admin_only_route():
            # User is guaranteed to have admin role or higher
            pass
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user = AuthService.require_role(required_role)
                # Add user to request context
                request.current_user = user
                return f(*args, **kwargs)
            except AuthenticationError:
                if request.is_json:
                    return (
                        jsonify(
                            {
                                "error": "Authentication required",
                                "code": "AUTH_REQUIRED",
                            }
                        ),
                        401,
                    )
                else:
                    return redirect(url_for("auth.login"))
            except AuthorizationError as e:
                if request.is_json:
                    return (
                        jsonify({"error": str(e), "code": "INSUFFICIENT_PERMISSIONS"}),
                        403,
                    )
                else:
                    return jsonify({"error": "Access denied"}), 403

        return decorated_function

    return decorator


def admin_required(f):
    """
    Decorator to require admin role

    Usage:
        @admin_required
        def admin_route():
            # User is guaranteed to be admin
            pass
    """
    return role_required(UserRole.ADMIN)(f)


def manager_required(f):
    """
    Decorator to require manager role or higher

    Usage:
        @manager_required
        def manager_route():
            # User is guaranteed to be manager or admin
            pass
    """
    return role_required(UserRole.MANAGER)(f)


def user_required(f):
    """
    Decorator to require user role or higher (excludes readonly)

    Usage:
        @user_required
        def user_route():
            # User is guaranteed to have modification permissions
            pass
    """
    return role_required(UserRole.USER)(f)


def api_key_or_session_required(f):
    """
    Decorator to require either API key or session authentication

    Usage:
        @api_key_or_session_required
        def api_route():
            # User is authenticated via API key or session
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # TODO: Implement API key validation
            # For now, fallback to session auth
            pass

        # Fallback to session authentication
        try:
            user = AuthService.require_authentication()
            request.current_user = user
            return f(*args, **kwargs)
        except AuthenticationError:
            return (
                jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}),
                401,
            )

    return decorated_function


def optional_auth(f):
    """
    Decorator that adds user info if authenticated but doesn't require it

    Usage:
        @optional_auth
        def public_route():
            # request.current_user will be set if authenticated, None otherwise
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user = AuthService.get_current_user()
            request.current_user = user
        except Exception:
            request.current_user = None

        return f(*args, **kwargs)

    return decorated_function


def check_content_permissions(action: str):
    """
    Decorator to check content-specific permissions

    Args:
        action: The action being performed ('view', 'modify', 'delete')

    Usage:
        @check_content_permissions('delete')
        def delete_content():
            # User is guaranteed to have delete permissions
            pass
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user = AuthService.require_authentication()

                if action == "view":
                    # All authenticated users can view
                    pass
                elif action == "modify":
                    if not user.can_modify_content():
                        raise AuthorizationError("Content modification not allowed")
                elif action == "delete":
                    if not user.can_delete_content():
                        raise AuthorizationError("Content deletion not allowed")
                else:
                    raise AuthorizationError("Unknown action")

                request.current_user = user
                return f(*args, **kwargs)

            except AuthenticationError:
                if request.is_json:
                    return (
                        jsonify(
                            {
                                "error": "Authentication required",
                                "code": "AUTH_REQUIRED",
                            }
                        ),
                        401,
                    )
                else:
                    return redirect(url_for("auth.login"))
            except AuthorizationError as e:
                return (
                    jsonify({"error": str(e), "code": "INSUFFICIENT_PERMISSIONS"}),
                    403,
                )

        return decorated_function

    return decorator


def rate_limit_by_user(max_requests: int = 100, window_seconds: int = 3600):
    """
    Rate limiting decorator that uses user ID instead of IP

    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds

    Usage:
        @rate_limit_by_user(max_requests=50, window_seconds=3600)
        def user_specific_route():
            # Rate limited per user, not per IP
            pass
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user = AuthService.require_authentication()

                # Use existing rate limiting but with user ID as identifier
                from src.utils.security import RateLimiter

                identifier = f"user_{user.id}"

                if RateLimiter.is_rate_limited(
                    identifier, max_requests, window_seconds
                ):
                    return (
                        jsonify(
                            {
                                "error": "Rate limit exceeded",
                                "message": f"Maximum {max_requests} requests per {window_seconds} seconds per user",
                            }
                        ),
                        429,
                    )

                request.current_user = user
                return f(*args, **kwargs)

            except AuthenticationError:
                return (
                    jsonify(
                        {"error": "Authentication required", "code": "AUTH_REQUIRED"}
                    ),
                    401,
                )

        return decorated_function

    return decorator


def log_user_action(action: str):
    """
    Decorator to log user actions for audit trail

    Args:
        action: Description of the action being performed

    Usage:
        @log_user_action("deleted video")
        def delete_video():
            # Action will be logged with user info
            pass
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = getattr(request, "current_user", None)

            if user:
                logger.info(
                    f"User {user.username} (ID: {user.id}) {action} from {request.remote_addr}"
                )
            else:
                logger.info(f"Anonymous user {action} from {request.remote_addr}")

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def session_security_check(f):
    """
    Decorator to perform additional session security checks

    Usage:
        @session_security_check
        def sensitive_route():
            # Additional session validation performed
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user = AuthService.require_authentication()

            # Check if session is from same IP (optional security measure)
            session_token = flask_session.get("session_token")
            if session_token:
                from src.database.connection import get_db
                from src.database.models import UserSession

                with get_db() as db_session:
                    user_session = (
                        db_session.query(UserSession)
                        .filter_by(session_token=session_token)
                        .first()
                    )

                    if user_session and user_session.ip_address:
                        current_ip = request.environ.get(
                            "HTTP_X_FORWARDED_FOR", request.remote_addr
                        )
                        if user_session.ip_address != current_ip:
                            logger.warning(
                                f"Session IP mismatch for user {user.username}: "
                                f"session={user_session.ip_address}, current={current_ip}"
                            )
                            # Note: We don't block this as IPs can change legitimately

            request.current_user = user
            return f(*args, **kwargs)

        except AuthenticationError:
            return (
                jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}),
                401,
            )

    return decorated_function
