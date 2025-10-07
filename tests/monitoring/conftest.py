"""
Monitoring Configuration and Fixtures
====================================

Fixtures and configuration for test monitoring and analysis.
"""

import json
import logging
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import pytest


@dataclass
class TestExecutionMetrics:
    """Test execution metrics and metadata."""

    test_id: str
    test_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    status: str = "running"  # running, passed, failed, skipped
    memory_usage: Optional[float] = None
    cpu_usage: Optional[float] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    log_entries: List[Dict] = None

    def __post_init__(self):
        if self.log_entries is None:
            self.log_entries = []


class TestMonitoringLogger:
    """Centralized test monitoring and logging."""

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(exist_ok=True)

        # Test execution tracking
        self.current_tests: Dict[str, TestExecutionMetrics] = {}
        self.completed_tests: List[TestExecutionMetrics] = []
        self._lock = threading.Lock()

        # Setup structured logging
        self.setup_structured_logging()

        # Performance monitoring
        self.start_performance_monitoring()

    def setup_structured_logging(self):
        """Setup structured JSON logging for tests."""
        # Create test-specific logger
        self.logger = logging.getLogger("mvidarr.test.monitoring")
        self.logger.setLevel(logging.DEBUG)

        # JSON log file handler
        json_log_file = (
            self.logs_dir
            / f'test_execution_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jsonl'
        )
        json_handler = logging.FileHandler(json_log_file)
        json_handler.setLevel(logging.DEBUG)

        # Console handler for immediate feedback
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Formatters
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }

                # Add test context if available
                if hasattr(record, "test_id"):
                    log_entry["test_id"] = record.test_id
                if hasattr(record, "test_name"):
                    log_entry["test_name"] = record.test_name
                if hasattr(record, "correlation_id"):
                    log_entry["correlation_id"] = record.correlation_id

                return json.dumps(log_entry)

        json_handler.setFormatter(JSONFormatter())

        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # Add handlers
        if not self.logger.handlers:
            self.logger.addHandler(json_handler)
            self.logger.addHandler(console_handler)

        self.json_log_file = json_log_file

    def start_performance_monitoring(self):
        """Start system performance monitoring."""
        self.process = psutil.Process()
        self.system_metrics = []

    def generate_test_id(self) -> str:
        """Generate unique test ID."""
        return str(uuid.uuid4())

    def start_test(self, test_name: str) -> str:
        """Start monitoring a test."""
        test_id = self.generate_test_id()

        with self._lock:
            metrics = TestExecutionMetrics(
                test_id=test_id,
                test_name=test_name,
                start_time=time.time(),
                memory_usage=self.get_memory_usage(),
                cpu_usage=self.get_cpu_usage(),
            )
            self.current_tests[test_id] = metrics

        # Log test start
        self.logger.info(
            f"Test started: {test_name}",
            extra={
                "test_id": test_id,
                "test_name": test_name,
                "event": "test_start",
                "memory_mb": metrics.memory_usage,
                "cpu_percent": metrics.cpu_usage,
            },
        )

        return test_id

    def end_test(self, test_id: str, status: str, error_info: Optional[Dict] = None):
        """End monitoring a test."""
        with self._lock:
            if test_id not in self.current_tests:
                return

            metrics = self.current_tests[test_id]
            metrics.end_time = time.time()
            metrics.duration = metrics.end_time - metrics.start_time
            metrics.status = status

            if error_info:
                metrics.error_message = error_info.get("message")
                metrics.error_type = error_info.get("type")

            # Move to completed tests
            self.completed_tests.append(metrics)
            del self.current_tests[test_id]

        # Log test completion
        log_data = {
            "test_id": test_id,
            "test_name": metrics.test_name,
            "event": "test_end",
            "status": status,
            "duration_seconds": metrics.duration,
            "memory_mb": self.get_memory_usage(),
            "cpu_percent": self.get_cpu_usage(),
        }

        if error_info:
            log_data.update(error_info)

        log_level = logging.ERROR if status == "failed" else logging.INFO
        self.logger.log(
            log_level, f"Test ended: {metrics.test_name} - {status}", extra=log_data
        )

    def log_test_event(
        self,
        test_id: str,
        event_type: str,
        message: str,
        extra_data: Optional[Dict] = None,
    ):
        """Log a test event with correlation."""
        log_data = {
            "test_id": test_id,
            "event": event_type,
            "correlation_id": f"{test_id}_{int(time.time())}",
        }

        if extra_data:
            log_data.update(extra_data)

        if test_id in self.current_tests:
            log_data["test_name"] = self.current_tests[test_id].test_name

        self.logger.info(message, extra=log_data)

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return self.process.cpu_percent()
        except Exception:
            return 0.0

    def get_test_summary(self) -> Dict[str, Any]:
        """Get test execution summary."""
        total_tests = len(self.completed_tests)
        if total_tests == 0:
            return {"total_tests": 0, "summary": "No tests completed"}

        passed = sum(1 for t in self.completed_tests if t.status == "passed")
        failed = sum(1 for t in self.completed_tests if t.status == "failed")
        skipped = sum(1 for t in self.completed_tests if t.status == "skipped")

        durations = [t.duration for t in self.completed_tests if t.duration]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "success_rate": (passed / total_tests) * 100 if total_tests > 0 else 0,
            "average_duration": avg_duration,
            "total_duration": sum(durations) if durations else 0,
            "log_file": str(self.json_log_file),
        }

    def analyze_errors(self) -> Dict[str, Any]:
        """Analyze errors and failures."""
        failed_tests = [t for t in self.completed_tests if t.status == "failed"]

        if not failed_tests:
            return {"error_count": 0, "error_analysis": "No errors detected"}

        # Categorize errors
        error_categories = {}
        for test in failed_tests:
            error_type = test.error_type or "Unknown"
            if error_type not in error_categories:
                error_categories[error_type] = []
            error_categories[error_type].append(
                {
                    "test_name": test.test_name,
                    "error_message": test.error_message,
                    "duration": test.duration,
                }
            )

        return {
            "error_count": len(failed_tests),
            "error_categories": error_categories,
            "most_common_error": (
                max(error_categories.keys(), key=lambda k: len(error_categories[k]))
                if error_categories
                else None
            ),
        }

    def export_metrics(self, output_file: Optional[Path] = None) -> Path:
        """Export all metrics to JSON file."""
        if output_file is None:
            output_file = (
                self.logs_dir
                / f"test_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        metrics_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": self.get_test_summary(),
            "error_analysis": self.analyze_errors(),
            "completed_tests": [asdict(test) for test in self.completed_tests],
            "running_tests": [asdict(test) for test in self.current_tests.values()],
        }

        with open(output_file, "w") as f:
            json.dump(metrics_data, f, indent=2, default=str)

        return output_file


# Global test monitor instance
_test_monitor = None


@pytest.fixture(scope="session")
def monitoring_logs_dir():
    """Get monitoring logs directory."""
    logs_path = Path(__file__).parent / "logs"
    logs_path.mkdir(exist_ok=True)
    return logs_path


@pytest.fixture(scope="session")
def test_monitor(monitoring_logs_dir):
    """Get global test monitor instance."""
    global _test_monitor
    if _test_monitor is None:
        _test_monitor = TestMonitoringLogger(monitoring_logs_dir)
    return _test_monitor


@pytest.fixture(scope="function")
def monitored_test(test_monitor, request):
    """Monitor individual test execution."""
    test_name = f"{request.module.__name__}::{request.function.__name__}"
    test_id = test_monitor.start_test(test_name)

    class MonitoredTest:
        def __init__(self, test_id, test_monitor):
            self.test_id = test_id
            self.monitor = test_monitor
            self.start_time = time.time()

        def log_event(self, event_type: str, message: str, **kwargs):
            """Log a test event."""
            self.monitor.log_test_event(self.test_id, event_type, message, kwargs)

        def log_error(self, error: Exception):
            """Log an error during test execution."""
            self.monitor.log_test_event(
                self.test_id,
                "error",
                f"Test error: {str(error)}",
                {"error_type": type(error).__name__, "error_message": str(error)},
            )

        def log_performance(self, operation: str, duration: float, **kwargs):
            """Log performance metrics."""
            self.monitor.log_test_event(
                self.test_id,
                "performance",
                f"{operation} took {duration:.3f}s",
                {"operation": operation, "duration_seconds": duration, **kwargs},
            )

    monitored = MonitoredTest(test_id, test_monitor)

    def pytest_runtest_makereport(item, call):
        """Hook to capture test results."""
        if call.when == "call":
            error_info = None
            if call.excinfo:
                error_info = {
                    "type": call.excinfo.type.__name__,
                    "message": str(call.excinfo.value),
                    "traceback": call.excinfo.traceback,
                }

            status = "failed" if call.excinfo else "passed"
            test_monitor.end_test(test_id, status, error_info)

    # Register the hook
    request.node.add_report_hook = pytest_runtest_makereport

    yield monitored

    # Ensure test is ended if not already done
    if test_id in test_monitor.current_tests:
        test_monitor.end_test(test_id, "skipped")


class ErrorAnalyzer:
    """Analyze and categorize test errors."""

    ERROR_PATTERNS = {
        "connection_error": [
            "connection refused",
            "connection timeout",
            "network error",
            "unable to connect",
            "connection lost",
        ],
        "timeout_error": [
            "timeout",
            "timed out",
            "deadline exceeded",
            "operation timeout",
            "response timeout",
        ],
        "assertion_error": ["assert", "assertion failed", "expected", "actual"],
        "import_error": [
            "import error",
            "module not found",
            "cannot import",
            "no module named",
        ],
        "configuration_error": ["config", "configuration", "setting", "environment"],
        "database_error": [
            "database",
            "sql",
            "query",
            "connection",
            "integrity error",
            "constraint",
        ],
        "file_error": [
            "file not found",
            "permission denied",
            "no such file",
            "directory",
            "path",
        ],
    }

    @classmethod
    def categorize_error(cls, error_message: str, error_type: str) -> str:
        """Categorize an error based on message and type."""
        message_lower = error_message.lower()

        for category, patterns in cls.ERROR_PATTERNS.items():
            if any(pattern in message_lower for pattern in patterns):
                return category

        # Fallback to error type
        type_mapping = {
            "ConnectionError": "connection_error",
            "TimeoutError": "timeout_error",
            "AssertionError": "assertion_error",
            "ImportError": "import_error",
            "FileNotFoundError": "file_error",
            "PermissionError": "file_error",
        }

        return type_mapping.get(error_type, "unknown_error")


@pytest.fixture(scope="function")
def error_analyzer():
    """Get error analyzer instance."""
    return ErrorAnalyzer
