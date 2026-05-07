"""
Security configuration and initialization for MVidarr
"""

import os

from flask import Flask

from src.utils.logger import get_logger
from src.utils.security import SecureConfig, apply_security_headers

logger = get_logger("mvidarr.security")


class SecurityManager:
    """Central security configuration manager"""

    def __init__(self, app: Flask = None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        """Initialize security configurations for Flask app"""

        # Apply security headers to all responses
        app.after_request(apply_security_headers)

        # Configure secure session settings
        self._configure_session_security(app)

        # Set up secure file upload settings
        self._configure_file_upload_security(app)

        # Configure database security
        self._configure_database_security(app)

        # Set up logging for security events
        self._configure_security_logging(app)

        # Configure SSL/TLS enforcement
        self._configure_ssl_enforcement(app)

        logger.info("Security configurations applied successfully")

    def _configure_session_security(self, app: Flask):
        """Configure secure session settings"""

        # Ensure secret key is set and secure
        if not app.config.get("SECRET_KEY"):
            logger.warning("No SECRET_KEY configured, generating one...")
            app.config["SECRET_KEY"] = SecureConfig.generate_secret_key()

        # Secure session cookie settings
        # Check if we're in development mode (accessing via HTTP)
        is_development = os.getenv("FLASK_ENV") != "production"

        # Don't override session settings that are already configured in app.py
        # Only set security-specific settings that aren't conflicting
        app.config.update(
            SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript access
            SESSION_COOKIE_SAMESITE="Lax",  # CSRF protection
        )

        # Don't override PERMANENT_SESSION_LIFETIME - let app.py handle it
        logger.info(
            f"Session lifetime from app config: {app.config.get('PERMANENT_SESSION_LIFETIME', 'not set')}"
        )

        if is_development:
            logger.warning(
                "Development mode: SESSION_COOKIE_SECURE disabled for HTTP access"
            )

        logger.info("Session security configured")

    def _configure_file_upload_security(self, app: Flask):
        """Configure secure file upload settings"""

        # Maximum file upload size (100MB)
        app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

        # Allowed file extensions for uploads
        app.config["ALLOWED_EXTENSIONS"] = {
            "images": {"png", "jpg", "jpeg", "gif", "webp"},
            "videos": {"mp4", "mkv", "avi", "webm", "mov"},
            "subtitles": {"srt", "vtt", "ass", "ssa", "sub"},
            "metadata": {"json", "nfo", "xml"},
        }

        # Upload directories with restricted permissions
        upload_dirs = [
            "data/thumbnails",
            "data/downloads",
            "data/cache",
            "data/backups",
        ]

        for dir_path in upload_dirs:
            os.makedirs(dir_path, mode=0o750, exist_ok=True)

        logger.info("File upload security configured")

    def _configure_database_security(self, app: Flask):
        """Configure database security settings"""

        # Database connection security
        db_config = {
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                "connect_args": {
                    "charset": "utf8mb4",
                    "sql_mode": "STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION",
                    "autocommit": False,
                },
            }
        }

        app.config.update(db_config)
        logger.info("Database security configured")

    def _configure_security_logging(self, app: Flask):
        """Configure security event logging"""

        # Security events to log
        security_events = [
            "failed_authentication",
            "rate_limit_exceeded",
            "invalid_input_detected",
            "file_upload_rejected",
            "suspicious_activity",
        ]

        app.config["SECURITY_LOG_EVENTS"] = security_events
        logger.info("Security logging configured")

    def _configure_ssl_enforcement(self, app: Flask):
        """Configure SSL/TLS enforcement based on settings"""

        # Check if SSL enforcement is enabled in settings
        try:
            from src.services.settings_service import SettingsService

            ssl_required = SettingsService.get_bool("ssl_required", False)

            if ssl_required:
                logger.info("SSL enforcement enabled - configuring HTTPS redirects")

                # Add before_request handler to enforce HTTPS
                @app.before_request
                def force_https():
                    from flask import redirect, request, url_for

                    # Skip SSL enforcement for health checks
                    if request.endpoint and "health" in request.endpoint:
                        return None

                    # Skip if already HTTPS or if localhost (development)
                    if (
                        request.is_secure
                        or request.host.startswith("localhost")
                        or request.host.startswith("127.0.0.1")
                    ):
                        return None

                    # Redirect to HTTPS
                    url = request.url.replace("http://", "https://", 1)
                    return redirect(url, code=301)

                # Update security headers for HTTPS
                app.config.update(
                    SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https"
                )

                logger.info("SSL enforcement configured - HTTPS redirects active")
            else:
                logger.info("SSL enforcement disabled")

        except Exception as e:
            logger.warning(f"Could not configure SSL enforcement: {e}")
            logger.info("SSL enforcement disabled due to configuration error")


class ProductionSecurityConfig:
    """Production-specific security configurations"""

    @staticmethod
    def apply_production_settings(app: Flask):
        """Apply production security settings"""

        # Configure debug and testing mode from environment
        import os

        app.config["DEBUG"] = os.environ.get("MVIDARR_DEBUG", "false").lower() == "true"
        app.config["TESTING"] = (
            os.environ.get("MVIDARR_TESTING", "false").lower() == "true"
        )

        # Hide Flask version and server info
        app.config["SERVER_NAME"] = None

        # Secure cookie settings for production
        # Only set SESSION_COOKIE_SECURE=True if SSL_REQUIRED is explicitly enabled
        # This allows production deployments over HTTP for development/local use
        try:
            from src.services.settings_service import SettingsService

            ssl_required = SettingsService.get_bool("ssl_required", False)
            secure_cookies = ssl_required
        except Exception:
            # Fallback: check if we're likely running over HTTPS
            # If no SSL setting available, assume HTTP for safety
            secure_cookies = False

        app.config.update(
            SESSION_COOKIE_SECURE=secure_cookies,
            SESSION_COOKIE_DOMAIN=None,  # Set to your domain in production
            WTF_CSRF_TIME_LIMIT=None,  # No CSRF token timeout
        )

        logger.info(
            f"Production cookies secure setting: {secure_cookies} (SSL required: {ssl_required if 'ssl_required' in locals() else 'unknown'})"
        )

        # Database security for production
        app.config.update(
            SQLALCHEMY_ECHO=False,  # Don't log SQL queries
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )

        # File system security
        app.config.update(
            UPLOAD_FOLDER_PERMISSIONS=0o750,
            LOG_FILE_PERMISSIONS=0o640,
        )

        logger.info("Production security settings applied")


def validate_environment_security():
    """Validate security of environment configuration"""

    security_issues = []

    # Check for default passwords
    db_password = os.getenv("DB_PASSWORD", "")
    if db_password in ["", "password", "root", "admin", "change_me_to_your_password"]:
        security_issues.append("Database password is default or weak")

    # Check for default secret key
    secret_key = os.getenv("SECRET_KEY", "")
    if secret_key in [
        "",
        "dev",
        "development",
        "change_me_to_random_string_for_production",
    ]:
        security_issues.append("SECRET_KEY is default or weak")

    # Check for debug mode in production
    if (
        os.getenv("FLASK_ENV") == "production"
        and os.getenv("FLASK_DEBUG", "").lower() == "true"
    ):
        security_issues.append("Debug mode enabled in production")

    # Check file permissions
    sensitive_files = [".env", "data/mvidarr.db", "data/logs/mvidarr.log"]

    for file_path in sensitive_files:
        if os.path.exists(file_path):
            file_perms = oct(os.stat(file_path).st_mode)[-3:]
            if file_perms in ["777", "666", "755"]:
                security_issues.append(
                    f"Insecure permissions on {file_path}: {file_perms}"
                )

    # Log security issues
    if security_issues:
        logger.warning("Security issues detected:")
        for issue in security_issues:
            logger.warning(f"  - {issue}")
        return False
    else:
        logger.info("Environment security validation passed")
        return True


def setup_security_monitoring():
    """Set up security monitoring and alerting"""

    import atexit

    def security_cleanup():
        """Cleanup function for security on app shutdown"""
        logger.info("Security cleanup completed")

    atexit.register(security_cleanup)

    # Set up security event handlers
    security_handlers = {
        "rate_limit": lambda: logger.warning("Rate limit exceeded"),
        "invalid_input": lambda data: logger.warning(f"Invalid input detected: {data}"),
        "file_upload_error": lambda error: logger.error(
            f"File upload security error: {error}"
        ),
    }

    return security_handlers


# Security middleware configuration
SECURITY_MIDDLEWARE_CONFIG = {
    "rate_limiting": {
        "enabled": True,
        "default_limits": {
            "api_calls": 1000,  # per hour
            "file_uploads": 50,  # per hour
            "authentication": 10,  # per 15 minutes
        },
    },
    "input_validation": {
        "enabled": True,
        "max_payload_size": 10 * 1024 * 1024,  # 10MB
        "strict_validation": True,
    },
    "file_security": {
        "scan_uploads": True,
        "allowed_mime_types": [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "video/mp4",
            "video/x-msvideo",
            "video/quicktime",
            "text/plain",
            "application/json",
        ],
        "max_file_size": 100 * 1024 * 1024,  # 100MB
    },
}
