"""
Dynamic Authentication Middleware
Checks authentication requirements on each request based on database settings.
"""

from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for

from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.dynamic_auth")


class DynamicAuthMiddleware:
    """Middleware that checks authentication requirements dynamically"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the middleware with Flask app"""
        app.before_request(self.check_authentication_requirement)

        # Add auth routes
        self.register_auth_routes(app)

        logger.info("Dynamic authentication middleware initialized")

    def register_auth_routes(self, app):
        """Register basic authentication routes"""

        @app.route("/simple-login", methods=["GET"])
        def simple_login_page():
            """Show simple login page"""
            # Check if user is already authenticated
            is_authenticated = session.get("authenticated", False)
            client_ip = request.environ.get(
                "HTTP_X_FORWARDED_FOR", request.environ.get("REMOTE_ADDR", "unknown")
            )

            logger.info(
                f"Simple login page accessed - IP: {client_ip}, Authenticated: {is_authenticated}"
            )
            logger.info(f"Session contents: {dict(session)}")

            if is_authenticated:
                # User is already authenticated, safe redirect to dashboard
                next_url = request.args.get("next", "/")
                logger.info(f"User already authenticated, redirecting to: {next_url}")
                from src.utils.security import safe_redirect

                return safe_redirect(next_url)

            # Show login form for unauthenticated users
            return render_template(
                "auth/simple_login.html", error=request.args.get("error")
            )

        @app.route("/simple-login", methods=["POST"])
        def simple_login():
            """Handle login"""
            try:
                # Get login credentials
                data = request.get_json() if request.is_json else request.form
                username = data.get("username", "").strip()
                password = data.get("password", "")

                # Use SimpleAuthService for authentication
                from src.services.simple_auth_service import SimpleAuthService

                success, message = SimpleAuthService.authenticate(username, password)

                if success:
                    # Clear any existing session data
                    session.clear()

                    # Set authentication session data
                    session["authenticated"] = True
                    session["username"] = username
                    session["role"] = "admin"
                    session.permanent = True  # Make session permanent

                    # Force session to be saved
                    session.modified = True

                    logger.info(f"User {username} authenticated successfully")
                    logger.info(f"Session contents after login: {dict(session)}")
                    logger.info(f"Session permanent flag: {session.permanent}")
                    logger.info(f"Session modified flag: {session.modified}")

                    # Debug session configuration
                    from flask import current_app

                    logger.info(
                        f"App SECRET_KEY length: {len(current_app.config.get('SECRET_KEY', ''))}"
                    )
                    logger.info(
                        f"App SESSION_COOKIE_NAME: {current_app.config.get('SESSION_COOKIE_NAME')}"
                    )
                    logger.info(
                        f"App SESSION_COOKIE_SECURE: {current_app.config.get('SESSION_COOKIE_SECURE')}"
                    )
                    logger.info(
                        f"App SESSION_COOKIE_HTTPONLY: {current_app.config.get('SESSION_COOKIE_HTTPONLY')}"
                    )
                    logger.info(
                        f"App PERMANENT_SESSION_LIFETIME: {current_app.config.get('PERMANENT_SESSION_LIFETIME')}"
                    )

                    if request.is_json:
                        return jsonify({"success": True, "message": "Login successful"})
                    else:
                        next_url = request.args.get("next", "/")
                        logger.debug(f"Redirecting authenticated user to: {next_url}")
                        from src.utils.security import safe_redirect

                        return safe_redirect(next_url)
                else:
                    logger.warning(
                        f"Failed login attempt for user: {username} - {message}"
                    )

                    if request.is_json:
                        return jsonify({"error": message}), 401
                    else:
                        return redirect(url_for("simple_login_page", error=message))

            except Exception as e:
                logger.error(f"Login error: {e}")

                if request.is_json:
                    return jsonify({"error": "Login failed"}), 500
                else:
                    return redirect(url_for("simple_login_page", error="Login failed"))

        @app.route("/auth/dynamic-logout", methods=["POST", "GET"])
        def logout():
            """Handle logout"""
            username = session.get("username", "unknown")
            session.clear()

            logger.info(f"User {username} logged out")

            if request.is_json:
                return jsonify({"success": True, "message": "Logged out successfully"})
            else:
                return redirect(url_for("simple_login_page"))

        @app.route("/auth/test-session", methods=["GET"])
        def test_session():
            """Test session functionality"""
            try:
                from flask import make_response

                # Test session writing
                session["test_key"] = "test_value"
                session.permanent = True
                session.modified = True

                # Read back immediately
                test_value = session.get("test_key", "NOT_FOUND")

                logger.info(f"Session test - Set: test_value, Got: {test_value}")
                logger.info(f"Session test - Full session: {dict(session)}")

                # Create response and check if Flask sets cookies
                response_data = {
                    "success": True,
                    "test_value": test_value,
                    "session_contents": dict(session),
                    "session_id": session.get("_session_id", "no-id"),
                    "secret_key_set": bool(app.config.get("SECRET_KEY")),
                    "secret_key_length": len(app.config.get("SECRET_KEY", "")),
                }

                response = make_response(jsonify(response_data))

                # Manual cookie setting as fallback with security attributes
                response.set_cookie(
                    "test_cookie",
                    "test_value",
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                )

                logger.info(
                    f"Response cookies will be set: {response.headers.get('Set-Cookie', 'NONE')}"
                )

                return response
            except Exception as e:
                logger.error(f"Session test error: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/auth/change-password", methods=["POST"])
        def change_password():
            """Handle password change"""
            try:
                # Check if user is authenticated
                if not session.get("authenticated", False):
                    return jsonify({"error": "Authentication required"}), 401

                username = session.get("username")
                if not username:
                    return jsonify({"error": "Invalid session"}), 401

                data = request.get_json() if request.is_json else request.form
                current_password = data.get("current_password", "")
                new_password = data.get("new_password", "")

                if not current_password or not new_password:
                    return (
                        jsonify(
                            {"error": "Current password and new password are required"}
                        ),
                        400,
                    )

                # Verify current password using SimpleAuthService
                from src.services.simple_auth_service import SimpleAuthService

                success, _ = SimpleAuthService.authenticate(username, current_password)
                if not success:
                    return jsonify({"error": "Current password is incorrect"}), 400

                # Validate new password
                if len(new_password) < 8:
                    return (
                        jsonify(
                            {"error": "New password must be at least 8 characters long"}
                        ),
                        400,
                    )

                # For now, just log the password change attempt
                logger.info(
                    f"Password change request for user {username} (not implemented)"
                )

                # TODO: Implement actual password storage and hashing
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Password change functionality will be implemented in the next update",
                        }
                    ),
                    501,
                )

            except Exception as e:
                logger.error(f"Password change error: {e}")
                return jsonify({"error": "Password change failed"}), 500

    def check_authentication_requirement(self):
        """Check if authentication is required for this request"""
        try:
            # Skip check for certain paths
            if self.should_skip_auth_check():
                return None

            # Check if authentication is required
            require_auth = SettingsService.get_bool("require_authentication", False)

            if not require_auth:
                # Authentication not required, allow access
                return None

            # Authentication is required, check if user is authenticated
            is_authenticated = session.get("authenticated", False)
            username = session.get("username", "unknown")
            client_ip = request.environ.get(
                "HTTP_X_FORWARDED_FOR", request.environ.get("REMOTE_ADDR", "unknown")
            )

            # More detailed session debugging (temporary INFO level)
            session_data = dict(session)
            logger.info(f"Auth check - Path: {request.path}, IP: {client_ip}")
            logger.info(f"Session authenticated flag: {is_authenticated}")
            logger.info(f"Session username: {username}")
            logger.info(f"Full session contents: {session_data}")
            logger.info(f"Session object type: {type(session)}")

            # Check if session is empty or has authentication data
            if not session_data:
                logger.info("Session is completely empty")
            elif "authenticated" not in session_data:
                logger.info("Session exists but no 'authenticated' key found")

            if not is_authenticated:
                # User not authenticated, redirect to login
                logger.info(
                    f"Authentication required: redirecting unauthenticated request from {request.path}"
                )

                if request.is_json or request.path.startswith("/api/"):
                    return (
                        jsonify(
                            {
                                "error": "Authentication required",
                                "code": "AUTH_REQUIRED",
                                "login_url": "/simple-login",
                            }
                        ),
                        401,
                    )
                else:
                    return redirect(url_for("simple_login_page", next=request.url))

            # User is authenticated, allow access
            logger.debug(
                f"User {username} authenticated, allowing access to {request.path}"
            )
            return None

        except Exception as e:
            logger.error(f"Error checking authentication requirement: {e}")
            # On error, allow access (fail open for safety)
            return None

    def should_skip_auth_check(self):
        """Determine if authentication check should be skipped for this request"""
        # Skip auth check for login/logout pages and static files
        skip_paths = [
            "/auth/login",
            "/auth/logout",
            "/auth/check",  # Authentication status check
            "/auth/test-session",  # Session testing endpoint
            "/simple-login",  # Our dynamic login page
            "/api/health",  # Health check endpoint - must be accessible for Docker health checks
            "/health",  # Health endpoints - should be accessible for monitoring
            "/static/",
            "/css/",
            "/js/",
            "/favicon.ico",
        ]

        for path in skip_paths:
            if request.path.startswith(path):
                return True

        return False


# Global middleware instance
dynamic_auth_middleware = DynamicAuthMiddleware()
