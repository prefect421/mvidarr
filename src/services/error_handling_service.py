"""
Enhanced error handling service for MVidarr
Provides comprehensive error categorization, recovery, and user feedback
"""

import sys
import traceback
from datetime import datetime
from enum import Enum
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.error_handling")


class ErrorCategory(Enum):
    """Error categories for better classification"""

    DATABASE_ERROR = "database_error"
    NETWORK_ERROR = "network_error"
    VALIDATION_ERROR = "validation_error"
    PERMISSION_ERROR = "permission_error"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    CONFIGURATION_ERROR = "configuration_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    SYSTEM_ERROR = "system_error"
    USER_ERROR = "user_error"


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorRecoveryStrategy(Enum):
    """Recovery strategies for different error types"""

    RETRY = "retry"
    FALLBACK = "fallback"
    IGNORE = "ignore"
    MANUAL_INTERVENTION = "manual_intervention"
    SYSTEM_RESTART = "system_restart"


class EnhancedErrorHandler:
    """Enhanced error handling with recovery strategies"""

    def __init__(self):
        self.error_stats = {
            "total_errors": 0,
            "by_category": {},
            "by_severity": {},
            "recovery_attempts": 0,
            "successful_recoveries": 0,
            "last_error": None,
        }

        # Error mapping for common exceptions
        self.error_mappings = {
            "sqlalchemy.exc.IntegrityError": ErrorCategory.DATABASE_ERROR,
            "sqlalchemy.exc.OperationalError": ErrorCategory.DATABASE_ERROR,
            "requests.exceptions.ConnectionError": ErrorCategory.NETWORK_ERROR,
            "requests.exceptions.Timeout": ErrorCategory.TIMEOUT_ERROR,
            "requests.exceptions.HTTPError": ErrorCategory.EXTERNAL_SERVICE_ERROR,
            "FileNotFoundError": ErrorCategory.RESOURCE_NOT_FOUND,
            "PermissionError": ErrorCategory.PERMISSION_ERROR,
            "ValueError": ErrorCategory.VALIDATION_ERROR,
            "KeyError": ErrorCategory.VALIDATION_ERROR,
            "AttributeError": ErrorCategory.SYSTEM_ERROR,
            "TypeError": ErrorCategory.SYSTEM_ERROR,
        }

        # Recovery strategies by category
        self.recovery_strategies = {
            ErrorCategory.DATABASE_ERROR: [
                ErrorRecoveryStrategy.RETRY,
                ErrorRecoveryStrategy.FALLBACK,
            ],
            ErrorCategory.NETWORK_ERROR: [
                ErrorRecoveryStrategy.RETRY,
                ErrorRecoveryStrategy.FALLBACK,
            ],
            ErrorCategory.VALIDATION_ERROR: [ErrorRecoveryStrategy.IGNORE],
            ErrorCategory.PERMISSION_ERROR: [ErrorRecoveryStrategy.MANUAL_INTERVENTION],
            ErrorCategory.RESOURCE_NOT_FOUND: [ErrorRecoveryStrategy.FALLBACK],
            ErrorCategory.RATE_LIMIT_ERROR: [ErrorRecoveryStrategy.RETRY],
            ErrorCategory.TIMEOUT_ERROR: [ErrorRecoveryStrategy.RETRY],
            ErrorCategory.CONFIGURATION_ERROR: [
                ErrorRecoveryStrategy.MANUAL_INTERVENTION
            ],
            ErrorCategory.EXTERNAL_SERVICE_ERROR: [
                ErrorRecoveryStrategy.RETRY,
                ErrorRecoveryStrategy.FALLBACK,
            ],
            ErrorCategory.SYSTEM_ERROR: [ErrorRecoveryStrategy.MANUAL_INTERVENTION],
            ErrorCategory.USER_ERROR: [ErrorRecoveryStrategy.IGNORE],
        }

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type and message"""
        error_type = type(error).__name__
        full_error_type = f"{type(error).__module__}.{error_type}"

        # Check full module path first
        if full_error_type in self.error_mappings:
            return self.error_mappings[full_error_type]

        # Check just the error type name
        if error_type in self.error_mappings:
            return self.error_mappings[error_type]

        # Check error message for specific patterns
        error_message = str(error).lower()

        if "connection" in error_message or "network" in error_message:
            return ErrorCategory.NETWORK_ERROR
        elif "timeout" in error_message:
            return ErrorCategory.TIMEOUT_ERROR
        elif "rate limit" in error_message or "too many requests" in error_message:
            return ErrorCategory.RATE_LIMIT_ERROR
        elif "not found" in error_message or "does not exist" in error_message:
            return ErrorCategory.RESOURCE_NOT_FOUND
        elif "permission" in error_message or "unauthorized" in error_message:
            return ErrorCategory.PERMISSION_ERROR
        elif "invalid" in error_message or "validation" in error_message:
            return ErrorCategory.VALIDATION_ERROR
        elif "configuration" in error_message or "config" in error_message:
            return ErrorCategory.CONFIGURATION_ERROR
        else:
            return ErrorCategory.SYSTEM_ERROR

    def determine_severity(
        self, error: Exception, category: ErrorCategory
    ) -> ErrorSeverity:
        """Determine error severity based on category and context"""
        severity_mapping = {
            ErrorCategory.DATABASE_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.NETWORK_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.VALIDATION_ERROR: ErrorSeverity.LOW,
            ErrorCategory.PERMISSION_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.RESOURCE_NOT_FOUND: ErrorSeverity.LOW,
            ErrorCategory.RATE_LIMIT_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.TIMEOUT_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.CONFIGURATION_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.EXTERNAL_SERVICE_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.USER_ERROR: ErrorSeverity.LOW,
        }

        base_severity = severity_mapping.get(category, ErrorSeverity.MEDIUM)

        # Upgrade severity for certain conditions
        error_message = str(error).lower()
        if "critical" in error_message or "fatal" in error_message:
            return ErrorSeverity.CRITICAL
        elif "corrupt" in error_message or "integrity" in error_message:
            return ErrorSeverity.CRITICAL

        return base_severity

    def create_error_context(
        self, error: Exception, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create comprehensive error context for logging and recovery"""
        category = self.categorize_error(error)
        severity = self.determine_severity(error, category)

        error_context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "category": category.value,
            "severity": severity.value,
            "timestamp": datetime.now().isoformat(),
            "traceback": traceback.format_exc(),
            "recovery_strategies": [
                strategy.value
                for strategy in self.recovery_strategies.get(category, [])
            ],
            "context": context or {},
        }

        # Add system context
        error_context["system_info"] = {
            "python_version": sys.version,
            "platform": sys.platform,
            "modules": list(sys.modules.keys())[:10],  # First 10 modules
        }

        return error_context

    def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any] = None,
        auto_recover: bool = True,
    ) -> Dict[str, Any]:
        """Handle an error with comprehensive logging and recovery"""
        error_context = self.create_error_context(error, context)

        # Update statistics
        self.error_stats["total_errors"] += 1
        category = error_context["category"]
        severity = error_context["severity"]

        if category not in self.error_stats["by_category"]:
            self.error_stats["by_category"][category] = 0
        self.error_stats["by_category"][category] += 1

        if severity not in self.error_stats["by_severity"]:
            self.error_stats["by_severity"][severity] = 0
        self.error_stats["by_severity"][severity] += 1

        self.error_stats["last_error"] = error_context

        # Log error based on severity
        if severity == ErrorSeverity.CRITICAL.value:
            logger.critical(
                f"Critical error: {error_context['error_message']}", extra=error_context
            )
        elif severity == ErrorSeverity.HIGH.value:
            logger.error(
                f"High severity error: {error_context['error_message']}",
                extra=error_context,
            )
        elif severity == ErrorSeverity.MEDIUM.value:
            logger.warning(
                f"Medium severity error: {error_context['error_message']}",
                extra=error_context,
            )
        else:
            logger.info(
                f"Low severity error: {error_context['error_message']}",
                extra=error_context,
            )

        # Attempt recovery if enabled
        recovery_result = None
        if auto_recover and error_context["recovery_strategies"]:
            recovery_result = self.attempt_recovery(error, error_context)

        return {
            "error_context": error_context,
            "recovery_result": recovery_result,
            "handled": True,
        }

    def attempt_recovery(
        self, error: Exception, error_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attempt to recover from an error using appropriate strategies"""
        self.error_stats["recovery_attempts"] += 1

        recovery_result = {
            "attempted": True,
            "successful": False,
            "strategy_used": None,
            "message": "Recovery failed",
        }

        strategies = error_context["recovery_strategies"]

        for strategy in strategies:
            if strategy == ErrorRecoveryStrategy.RETRY.value:
                # Implement retry logic
                recovery_result["strategy_used"] = strategy
                recovery_result[
                    "message"
                ] = "Retry recommended - operation should be attempted again"
                recovery_result["successful"] = True
                break

            elif strategy == ErrorRecoveryStrategy.FALLBACK.value:
                # Implement fallback logic
                recovery_result["strategy_used"] = strategy
                recovery_result[
                    "message"
                ] = "Fallback available - alternative approach recommended"
                recovery_result["successful"] = True
                break

            elif strategy == ErrorRecoveryStrategy.IGNORE.value:
                # Ignore the error
                recovery_result["strategy_used"] = strategy
                recovery_result["message"] = "Error can be safely ignored"
                recovery_result["successful"] = True
                break

            elif strategy == ErrorRecoveryStrategy.MANUAL_INTERVENTION.value:
                recovery_result["strategy_used"] = strategy
                recovery_result[
                    "message"
                ] = "Manual intervention required - please check system configuration"
                recovery_result["successful"] = False
                break

        if recovery_result["successful"]:
            self.error_stats["successful_recoveries"] += 1

        return recovery_result

    def create_user_friendly_message(
        self, error: Exception, context: Dict[str, Any] = None
    ) -> str:
        """Create user-friendly error message"""
        category = self.categorize_error(error)

        user_messages = {
            ErrorCategory.DATABASE_ERROR: "A database error occurred. Please try again in a moment.",
            ErrorCategory.NETWORK_ERROR: "Network connection issue. Please check your internet connection and try again.",
            ErrorCategory.VALIDATION_ERROR: "Invalid input provided. Please check your data and try again.",
            ErrorCategory.PERMISSION_ERROR: "Permission denied. You don't have access to this resource.",
            ErrorCategory.RESOURCE_NOT_FOUND: "The requested resource was not found.",
            ErrorCategory.RATE_LIMIT_ERROR: "Too many requests. Please wait a moment before trying again.",
            ErrorCategory.TIMEOUT_ERROR: "Request timed out. Please try again.",
            ErrorCategory.CONFIGURATION_ERROR: "System configuration error. Please contact support.",
            ErrorCategory.EXTERNAL_SERVICE_ERROR: "External service unavailable. Please try again later.",
            ErrorCategory.SYSTEM_ERROR: "System error occurred. Please try again or contact support.",
            ErrorCategory.USER_ERROR: "Invalid operation. Please check your input and try again.",
        }

        base_message = user_messages.get(category, "An unexpected error occurred.")

        # Add specific context if available
        if context and "operation" in context:
            base_message = f"Error during {context['operation']}: {base_message}"

        return base_message

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics"""
        return {
            "statistics": self.error_stats.copy(),
            "error_rate": self.error_stats["total_errors"]
            / max(self.error_stats.get("total_operations", 1), 1),
            "recovery_rate": self.error_stats["successful_recoveries"]
            / max(self.error_stats["recovery_attempts"], 1),
            "most_common_category": (
                max(self.error_stats["by_category"].items(), key=lambda x: x[1])[0]
                if self.error_stats["by_category"]
                else None
            ),
            "most_common_severity": (
                max(self.error_stats["by_severity"].items(), key=lambda x: x[1])[0]
                if self.error_stats["by_severity"]
                else None
            ),
        }

    def create_progress_indicator(
        self, operation: str, total: int, current: int, additional_info: str = None
    ) -> Dict[str, Any]:
        """Create progress indicator for long-running operations"""
        percentage = (current / total) * 100 if total > 0 else 0

        progress_info = {
            "operation": operation,
            "total": total,
            "current": current,
            "percentage": round(percentage, 1),
            "remaining": total - current,
            "status": "in_progress" if current < total else "completed",
            "timestamp": datetime.now().isoformat(),
        }

        if additional_info:
            progress_info["additional_info"] = additional_info

        # Calculate ETA if we have enough data
        if current > 0 and current < total:
            # This is a simplified ETA calculation
            progress_info["eta_estimate"] = f"{(total - current)} items remaining"

        return progress_info


# Global instance
error_handler = EnhancedErrorHandler()
