"""
Logging utilities for MVidarr
"""

import logging
import logging.handlers

from src.config.config import Config


def setup_logging(app):
    """Setup application logging"""
    config = Config()

    # Create logs directory if it doesn't exist
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Configure logging level
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_SIZE,
        backupCount=config.LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configure Flask app logger
    app.logger.setLevel(log_level)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

    # Configure werkzeug logger (Flask's internal logger)
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(log_level)
    werkzeug_logger.addHandler(file_handler)

    # Configure application loggers
    for logger_name in ["mvidarr", "imvdb", "metube", "youtube"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    # Configure authentication and security loggers
    auth_loggers = [
        "mvidarr.auth",
        "mvidarr.auth.decorators",
        "mvidarr.oauth",
        "mvidarr.security",
        "mvidarr.session",
    ]

    for logger_name in auth_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        # Authentication events should always be logged
        logger.propagate = True

    app.logger.info("Logging system initialized")


def get_logger(name):
    """Get a logger instance for a specific module"""
    return logging.getLogger(name)
