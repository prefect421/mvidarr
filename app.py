#!/usr/bin/env python3
"""
MVidarr - Main Application Entry Point
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from flask import Flask

from src.api.routes import register_routes
from src.config.config import Config
from src.database.connection import init_db
from src.middleware.dynamic_auth_middleware import dynamic_auth_middleware
from src.security_config import (
    ProductionSecurityConfig,
    SecurityManager,
    validate_environment_security,
)
from src.utils.logger import setup_logging


def create_app():
    """Create and configure the Flask application"""
    # Define template and static directories
    template_dir = Path(__file__).parent / "frontend" / "templates"
    static_dir = Path(__file__).parent / "frontend" / "static"

    app = Flask(
        __name__, template_folder=str(template_dir), static_folder=str(static_dir)
    )

    # Load configuration
    config = Config()
    app.config.from_object(config)

    # Ensure secret key is set for sessions - must be bytes or very secure string
    import os
    import secrets

    # Use environment variable or generate a consistent secret key
    secret_key = os.environ.get("MVIDARR_SECRET_KEY")
    if not secret_key:
        # Use a fixed secret key for development (consistent across restarts)
        secret_key = "mvidarr-dev-session-key-fixed-for-persistence-c1c224b03cd9bc7b6a86d77f5dace40191766c485cd55dc48caf9ac873335d6f"

    app.config["SECRET_KEY"] = secret_key

    # Session configuration for authentication
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config[
        "SESSION_COOKIE_SECURE"
    ] = False  # CRITICAL: Must be False for HTTP development
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "mvidarr_session"
    app.config["SESSION_COOKIE_PATH"] = "/"
    app.config["SESSION_COOKIE_DOMAIN"] = None  # Allow any domain for development

    # Force disable secure cookies for development
    app.config["SESSION_COOKIE_SECURE"] = False

    # Additional session configuration for better persistence
    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_USE_SIGNER"] = True

    # Set permanent session lifetime (24 hours)
    from datetime import timedelta

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)

    # Setup logging
    setup_logging(app)

    # Initialize security configurations
    security_manager = SecurityManager(app)

    # Validate environment security
    if not validate_environment_security():
        app.logger.warning("Security validation found issues - please review and fix")

    # Apply production security settings if in production
    if os.getenv("FLASK_ENV") == "production":
        ProductionSecurityConfig.apply_production_settings(app)
        app.logger.info("Production security settings applied")
    else:
        app.logger.info("Development mode detected")

    # CRITICAL: Always override SESSION_COOKIE_SECURE for development regardless of other settings
    # This must come AFTER ProductionSecurityConfig to ensure it takes precedence
    if os.getenv("FLASK_ENV") != "production":
        app.config["SESSION_COOKIE_SECURE"] = False
        app.logger.info(
            "Development mode: SESSION_COOKIE_SECURE forcibly disabled for HTTP access"
        )
    else:
        # Even in production, allow HTTP access if SSL is not explicitly required
        # This handles cases where production apps run locally over HTTP
        try:
            from src.services.settings_service import SettingsService

            if not SettingsService.get_bool("ssl_required", False):
                app.config["SESSION_COOKIE_SECURE"] = False
                app.logger.info(
                    "Production mode: SESSION_COOKIE_SECURE disabled (SSL not required)"
                )
        except Exception as e:
            app.logger.warning(f"Could not check SSL requirement setting: {e}")
            app.config["SESSION_COOKIE_SECURE"] = False
            app.logger.info(
                "Production mode: SESSION_COOKIE_SECURE disabled (fallback for HTTP)"
            )

    # Initialize database
    init_db(app)

    # Load database settings now that database is available
    config.load_from_database()

    # Register API routes
    register_routes(app)
    
    # Initialize background job system with SocketIO
    try:
        from src.services.flask_job_integration import FlaskJobSystemIntegrator
        from flask_socketio import SocketIO
        
        # Initialize SocketIO
        socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
        
        # Initialize job system integrator with app and socketio
        job_integrator = FlaskJobSystemIntegrator(app=app, socketio=socketio)
        
        app.logger.info("Background job system with SocketIO initialized successfully")
        
        # Store SocketIO instance for access
        app.socketio = socketio
        
    except Exception as e:
        app.logger.error(f"Failed to initialize background job system: {e}")
        # Continue without job system - app will still work
        app.socketio = None

    # Initialize dynamic authentication middleware
    dynamic_auth_middleware.init_app(app)

    # Initialize and start scheduler service
    try:
        from src.services.settings_service import SettingsService

        # Ensure settings cache is loaded before checking scheduler setting
        # Reset the cache loaded flag in case it failed during config.load_from_database()
        SettingsService._cache_loaded = False
        SettingsService.load_cache()

        # Ensure default authentication credentials exist
        try:
            from src.services.simple_auth_service import SimpleAuthService

            SimpleAuthService.ensure_default_credentials()
        except Exception as e:
            app.logger.error(f"Failed to ensure default credentials: {e}")

        if SettingsService.get_bool("auto_download_schedule_enabled", False):
            app.logger.info(
                "Auto-download scheduling is enabled, starting scheduler..."
            )
            
            # Check if enhanced scheduler should be used (Docker environment)
            use_enhanced = os.getenv("MVIDARR_USE_ENHANCED_SCHEDULER", "false").lower() == "true"
            
            if use_enhanced:
                app.logger.info("Using enhanced Docker-native scheduler")
                from src.services.enhanced_scheduler_service import enhanced_scheduler_service
                enhanced_scheduler_service.start()
            else:
                app.logger.info("Using standard scheduler")
                from src.services.scheduler_service import scheduler_service
                scheduler_service.start()
        else:
            app.logger.info("Auto-download scheduling is disabled")
    except Exception as e:
        app.logger.error(f"Failed to initialize scheduler: {e}")

    return app


def main():
    """Main entry point"""
    app = create_app()

    # Get port from settings (default 5000)
    port = app.config.get("PORT", 5000)

    app.logger.info(f"Starting MVidarr on port {port}")

    try:
        # Use SocketIO's run method if available, otherwise use Flask's run method
        if hasattr(app, 'socketio') and app.socketio is not None:
            app.logger.info("Starting with SocketIO support for background jobs")
            app.socketio.run(app, host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
        else:
            app.logger.info("Starting without SocketIO support")
            app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
    except Exception as e:
        app.logger.error(f"Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
