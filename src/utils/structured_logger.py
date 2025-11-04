"""
Enhanced Structured Logging System for MVidarr Production
Features: JSON logging, correlation IDs, request tracking, security audit trails
"""

import json
import logging
import logging.handlers
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from src.config.config import Config

# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON structured logging formatter with correlation tracking"""

    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation context if available
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        user_id = user_id_var.get()
        if user_id:
            log_entry["user_id"] = user_id

        request_id = request_id_var.get()
        if request_id:
            log_entry["request_id"] = request_id

        # Add exception information
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from the log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
            }:
                extra_fields[key] = value

        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class SecurityAuditFormatter(logging.Formatter):
    """Specialized formatter for security audit logs"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "security_audit",
            "level": record.levelname,
            "message": record.getMessage(),
            "source_ip": getattr(record, "source_ip", None),
            "user_agent": getattr(record, "user_agent", None),
            "endpoint": getattr(record, "endpoint", None),
            "method": getattr(record, "method", None),
            "status_code": getattr(record, "status_code", None),
            "user_id": user_id_var.get(),
            "correlation_id": correlation_id_var.get(),
        }

        # Add authentication specific fields
        auth_fields = ["auth_method", "auth_success", "failure_reason", "session_id"]
        for field in auth_fields:
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class CorrelationContext:
    """Context manager for correlation tracking"""

    def __init__(
        self, correlation_id: str = None, user_id: str = None, request_id: str = None
    ):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.user_id = user_id
        self.request_id = request_id or str(uuid.uuid4())
        self._correlation_token = None
        self._user_token = None
        self._request_token = None

    def __enter__(self):
        self._correlation_token = correlation_id_var.set(self.correlation_id)
        if self.user_id:
            self._user_token = user_id_var.set(self.user_id)
        if self.request_id:
            self._request_token = request_id_var.set(self.request_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._correlation_token:
            correlation_id_var.reset(self._correlation_token)
        if self._user_token:
            user_id_var.reset(self._user_token)
        if self._request_token:
            request_id_var.reset(self._request_token)


class StructuredLogger:
    """Enhanced structured logger with correlation tracking"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.name = name

    def _log_with_context(self, level: int, message: str, **kwargs):
        """Log with additional context"""
        extra = kwargs.copy()

        # Add correlation context
        extra["correlation_id"] = correlation_id_var.get()
        extra["user_id"] = user_id_var.get()
        extra["request_id"] = request_id_var.get()

        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        self._log_with_context(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log_with_context(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log_with_context(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log_with_context(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log_with_context(logging.CRITICAL, message, **kwargs)

    def audit(self, event: str, **kwargs):
        """Security audit logging"""
        kwargs["event_type"] = "security_audit"
        kwargs["audit_event"] = event
        self._log_with_context(logging.INFO, f"AUDIT: {event}", **kwargs)

    def performance(self, operation: str, duration: float, **kwargs):
        """Performance monitoring logs"""
        kwargs["event_type"] = "performance"
        kwargs["operation"] = operation
        kwargs["duration_ms"] = round(duration * 1000, 2)
        self._log_with_context(
            logging.INFO, f"PERF: {operation} completed in {duration:.3f}s", **kwargs
        )

    def api_request(
        self, method: str, endpoint: str, status_code: int, duration: float, **kwargs
    ):
        """API request logging"""
        kwargs.update(
            {
                "event_type": "api_request",
                "method": method,
                "endpoint": endpoint,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
            }
        )
        self._log_with_context(
            logging.INFO,
            f"API {method} {endpoint} -> {status_code} ({duration:.3f}s)",
            **kwargs,
        )


def setup_structured_logging():
    """
    Setup enhanced structured logging system

    Gracefully handles permission errors by falling back to console-only logging
    if file handlers can't be created (common in Docker environments with permission issues).
    """
    config = Config()

    # Create logs directory with proper error handling
    try:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"Warning: Cannot create logs directory {config.LOGS_DIR}: {e}")
        print("Falling back to console-only logging")

    # Configure logging level
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    # Create structured formatter
    structured_formatter = StructuredFormatter()

    # Create security audit formatter
    security_formatter = SecurityAuditFormatter()

    # File handlers list (will add handlers if permissions allow)
    file_handlers = []

    # Try to create file handlers - gracefully handle permission errors
    try:
        # Main application log file with structured JSON
        app_handler = logging.handlers.RotatingFileHandler(
            config.LOGS_DIR / "mvidarr_structured.log",
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT,
        )
        app_handler.setFormatter(structured_formatter)
        app_handler.setLevel(log_level)
        file_handlers.append(("app", app_handler))
    except (PermissionError, OSError) as e:
        print(f"Warning: Cannot create app log file: {e}. Using console-only logging.")

    try:
        # Security audit log file
        security_handler = logging.handlers.RotatingFileHandler(
            config.LOGS_DIR / "security_audit.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
        )
        security_handler.setFormatter(security_formatter)
        security_handler.setLevel(logging.INFO)
        file_handlers.append(("security", security_handler))
    except (PermissionError, OSError) as e:
        print(f"Warning: Cannot create security audit log file: {e}")

    try:
        # Performance log file
        performance_handler = logging.handlers.RotatingFileHandler(
            config.LOGS_DIR / "performance.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        performance_handler.setFormatter(structured_formatter)
        performance_handler.setLevel(logging.INFO)
        file_handlers.append(("performance", performance_handler))
    except (PermissionError, OSError) as e:
        print(f"Warning: Cannot create performance log file: {e}")

    # Console handler for development (human-readable)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Configure MVidarr application loggers
    app_loggers = [
        "mvidarr",
        "mvidarr.api",
        "mvidarr.services",
        "mvidarr.database",
        "mvidarr.jobs",
        "mvidarr.utils",
    ]

    for logger_name in app_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        # Only add app_handler if it was successfully created
        for handler_name, handler in file_handlers:
            if handler_name == "app":
                logger.addHandler(handler)
        logger.addHandler(console_handler)
        logger.propagate = False

    # Configure security audit loggers
    security_loggers = ["mvidarr.security", "mvidarr.auth", "mvidarr.audit"]

    for logger_name in security_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        # Only add security_handler if it was successfully created
        for handler_name, handler in file_handlers:
            if handler_name == "security":
                logger.addHandler(handler)
        logger.addHandler(console_handler)
        logger.propagate = False

    # Configure performance loggers
    performance_loggers = ["mvidarr.performance", "mvidarr.api.performance"]

    for logger_name in performance_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        # Only add performance_handler if it was successfully created
        for handler_name, handler in file_handlers:
            if handler_name == "performance":
                logger.addHandler(handler)
        logger.propagate = False

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Return handlers that were successfully created (may be None if permission errors occurred)
    handlers_dict = {"console_handler": console_handler}
    for handler_name, handler in file_handlers:
        if handler_name == "app":
            handlers_dict["structured_handler"] = handler
        elif handler_name == "security":
            handlers_dict["security_handler"] = handler
        elif handler_name == "performance":
            handlers_dict["performance_handler"] = handler

    return handlers_dict


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)


# Utility functions for context management
def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context"""
    return correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get correlation ID from current context"""
    return correlation_id_var.get()


def set_user_context(user_id: str):
    """Set user ID for current context"""
    return user_id_var.set(user_id)


def get_user_context() -> Optional[str]:
    """Get user ID from current context"""
    return user_id_var.get()


def generate_correlation_id() -> str:
    """Generate a new correlation ID"""
    return str(uuid.uuid4())
