"""
Authentication Integration for MVidarr
Integrates authentication middleware, routes, and endpoint protection.
"""

from flask import Flask

from src.api.auth import register_auth_routes
from src.api.protected_endpoints import (
    apply_authentication_protection,
    create_endpoint_protection_report,
)
from src.api.users import register_users_routes
from src.middleware.auth_middleware import AuthMiddleware
from src.services.auth_service import AuthService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth.integration")


class AuthenticationIntegration:
    """Main authentication integration class"""

    def __init__(self, app=None):
        self.app = app
        self.auth_middleware = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        """Initialize authentication system with Flask app"""
        try:
            logger.info("Initializing MVidarr authentication system...")

            # Step 1: Initialize authentication middleware
            logger.info("Step 1: Initializing authentication middleware...")
            self.auth_middleware = AuthMiddleware(app)

            # Step 2: Register authentication routes
            logger.info("Step 2: Registering authentication routes...")
            register_auth_routes(app)
            register_users_routes(app)

            # Step 3: Create default admin user if needed
            logger.info("Step 3: Checking for default admin user...")
            self._ensure_default_admin()

            # Step 4: Apply endpoint protection (after all routes are registered)
            # Using app.before_request instead of deprecated before_first_request
            self._setup_endpoint_protection_delayed(app)

            # Step 5: Add authentication context to app
            app.auth_integration = self

            logger.info("✅ Authentication system initialization complete!")

            return True

        except Exception as e:
            logger.error(f"❌ Authentication system initialization failed: {e}")
            raise

    def _ensure_default_admin(self):
        """Ensure default admin user exists"""
        try:
            created, message = AuthService.create_default_admin()
            if created:
                logger.info(f"✅ Default admin user created: {message}")
            else:
                logger.info("ℹ️  Default admin user check complete")
        except Exception as e:
            logger.error(f"Error checking default admin user: {e}")

    def get_protection_status(self):
        """Get current endpoint protection status"""
        if hasattr(self.app, "auth_protection_report"):
            return self.app.auth_protection_report
        return None

    def get_authentication_status(self):
        """Get authentication system status"""
        try:
            status = {
                "initialized": True,
                "middleware_active": self.auth_middleware is not None,
                "routes_registered": True,
                "database_connected": False,
                "default_admin_exists": False,
                "oauth_providers": [],
            }

            # Check database connection
            try:
                from src.database.connection import get_db

                with get_db() as session:
                    status["database_connected"] = True

                    # Check for admin users
                    from src.database.models import User, UserRole

                    admin_count = (
                        session.query(User).filter_by(role=UserRole.ADMIN).count()
                    )
                    status["default_admin_exists"] = admin_count > 0
                    status["admin_user_count"] = admin_count

                    # Get total user count
                    total_users = session.query(User).count()
                    status["total_users"] = total_users

            except Exception as e:
                logger.error(f"Database check failed: {e}")
                status["database_error"] = str(e)

            # Check OAuth providers
            try:
                from src.services.oauth_service import oauth_service

                status["oauth_enabled"] = oauth_service.is_oauth_enabled()
                status["oauth_providers"] = list(
                    oauth_service.get_available_providers().keys()
                )
            except Exception as e:
                logger.error(f"OAuth check failed: {e}")
                status["oauth_error"] = str(e)

            return status

        except Exception as e:
            logger.error(f"Failed to get authentication status: {e}")
            return {"initialized": False, "error": str(e)}

    def _setup_endpoint_protection_delayed(self, app):
        """Setup endpoint protection using modern Flask approach"""
        protection_applied = False

        @app.before_request
        def apply_protection_once():
            nonlocal protection_applied
            if not protection_applied:
                logger.info("Step 4: Applying endpoint protection...")
                try:
                    from src.api.protected_endpoints import (
                        apply_authentication_protection,
                        create_endpoint_protection_report,
                    )

                    protected_count = apply_authentication_protection(app)

                    # Generate protection report
                    report = create_endpoint_protection_report(app)
                    logger.info(f"Endpoint Protection Summary:")
                    logger.info(
                        f"  - Total endpoints: {report['summary']['total_endpoints']}"
                    )
                    logger.info(
                        f"  - Protected: {report['summary']['protected_endpoints']}"
                    )
                    logger.info(f"  - Public: {report['summary']['public_endpoints']}")
                    logger.info(
                        f"  - Coverage: {report['summary']['protection_coverage']}%"
                    )

                    if report["unprotected_endpoints"]:
                        logger.warning(
                            f"  - Unprotected: {len(report['unprotected_endpoints'])} endpoints"
                        )
                        for endpoint in report["unprotected_endpoints"][
                            :5
                        ]:  # Log first 5
                            logger.warning(
                                f"    * {endpoint['endpoint']} {endpoint['methods']}"
                            )

                    app.auth_protection_report = report
                    protection_applied = True
                except Exception as e:
                    logger.error(f"Error applying endpoint protection: {e}")
                    protection_applied = True  # Don't keep trying


# Global authentication integration instance
auth_integration = AuthenticationIntegration()


def init_authentication(app: Flask):
    """
    Initialize authentication system for MVidarr

    Args:
        app: Flask application instance

    Returns:
        bool: True if initialization successful
    """
    try:
        logger.info("🔐 Initializing MVidarr Authentication System")
        logger.info("=" * 60)

        # Initialize authentication integration
        success = auth_integration.init_app(app)

        if success:
            logger.info("🎉 Authentication system ready!")
            logger.info("=" * 60)

            # Log authentication status
            status = auth_integration.get_authentication_status()
            logger.info("📊 Authentication Status:")
            logger.info(
                f"   - Database Connected: {status.get('database_connected', False)}"
            )
            logger.info(f"   - Admin Users: {status.get('admin_user_count', 0)}")
            logger.info(f"   - Total Users: {status.get('total_users', 0)}")
            logger.info(f"   - OAuth Enabled: {status.get('oauth_enabled', False)}")
            logger.info(
                f"   - OAuth Providers: {', '.join(status.get('oauth_providers', []))}"
            )

            return True
        else:
            logger.error("❌ Authentication system initialization failed")
            return False

    except Exception as e:
        logger.error(f"❌ Authentication initialization error: {e}")
        return False


def get_auth_status():
    """Get current authentication system status"""
    return auth_integration.get_authentication_status()


def get_protection_status():
    """Get current endpoint protection status"""
    return auth_integration.get_protection_status()


# Authentication health check endpoint
def register_auth_health_endpoint(app: Flask):
    """Register authentication health check endpoint"""

    @app.route("/api/auth/health", methods=["GET"])
    def auth_health():
        """Authentication system health check"""
        try:
            status = get_auth_status()
            protection = get_protection_status()

            health_data = {
                "status": "healthy" if status.get("initialized") else "unhealthy",
                "authentication": status,
                "protection": {
                    "summary": protection["summary"] if protection else None,
                    "coverage": (
                        protection["summary"]["protection_coverage"]
                        if protection
                        else 0
                    ),
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Determine overall health
            is_healthy = (
                status.get("database_connected", False)
                and status.get("default_admin_exists", False)
                and status.get("initialized", False)
            )

            health_data["status"] = "healthy" if is_healthy else "degraded"

            return jsonify(health_data), 200 if is_healthy else 503

        except Exception as e:
            logger.error(f"Auth health check failed: {e}")
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ),
                500,
            )
