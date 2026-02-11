"""
Dynamic Authentication Middleware
Checks authentication requirements on each request based on database settings.
"""

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
            is_authenticated = session.get("authenticated", False)

            if is_authenticated:
                next_url = request.args.get("next", "/")
                from src.utils.security import safe_redirect

                return safe_redirect(next_url)

            return render_template(
                "auth/simple_login.html", error=request.args.get("error")
            )

        @app.route("/simple-login", methods=["POST"])
        def simple_login():
            """Handle login"""
            try:
                data = request.get_json() if request.is_json else request.form
                username = data.get("username", "").strip()
                password = data.get("password", "")

                from src.services.simple_auth_service import SimpleAuthService

                success, message = SimpleAuthService.authenticate(username, password)

                if success:
                    session.clear()
                    session["authenticated"] = True
                    session["username"] = username
                    session["role"] = "admin"
                    session.permanent = True
                    session.modified = True

                    logger.info(f"User {username} authenticated successfully")

                    if request.is_json:
                        return jsonify({"success": True, "message": "Login successful"})
                    else:
                        next_url = request.args.get("next", "/")
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

        @app.route("/auth/change-password", methods=["POST"])
        def change_password():
            """Handle password change"""
            try:
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

                from src.services.simple_auth_service import SimpleAuthService

                success, _ = SimpleAuthService.authenticate(username, current_password)
                if not success:
                    return jsonify({"error": "Current password is incorrect"}), 400

                if len(new_password) < 8:
                    return (
                        jsonify(
                            {"error": "New password must be at least 8 characters long"}
                        ),
                        400,
                    )

                # Actually change the password
                pw_success, pw_message = SimpleAuthService.set_credentials(
                    username, new_password
                )
                if pw_success:
                    return jsonify(
                        {"success": True, "message": "Password changed successfully"}
                    )
                else:
                    return jsonify({"error": pw_message}), 500

            except Exception as e:
                logger.error(f"Password change error: {e}")
                return jsonify({"error": "Password change failed"}), 500

    def check_authentication_requirement(self):
        """Check if authentication is required for this request"""
        try:
            if self.should_skip_auth_check():
                return None

            require_auth = SettingsService.get_bool("require_authentication", False)

            if not require_auth:
                return None

            is_authenticated = session.get("authenticated", False)

            if not is_authenticated:
                logger.debug(
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

            return None

        except Exception as e:
            logger.error(f"Error checking authentication requirement: {e}")
            # Fail closed - deny access on error
            if request.is_json or request.path.startswith("/api/"):
                return (
                    jsonify(
                        {
                            "error": "Authentication check failed",
                            "code": "AUTH_ERROR",
                        }
                    ),
                    401,
                )
            else:
                return redirect(url_for("simple_login_page"))

    def should_skip_auth_check(self):
        """Determine if authentication check should be skipped for this request"""
        skip_paths = [
            "/auth/login",
            "/auth/logout",
            "/auth/check",
            "/simple-login",
            "/api/health",
            "/health",
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
