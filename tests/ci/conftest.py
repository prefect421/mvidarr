"""
CI/CD Integration Tests Configuration
====================================

Fixtures and configuration for CI/CD integration tests.
Provides test monitoring, performance baselines, and CI environment simulation.
"""

import sys
from pathlib import Path

import pytest

# Add monitoring fixtures to CI tests
sys.path.append(str(Path(__file__).parent.parent / "monitoring"))

from tests.monitoring.conftest import (
    error_analyzer,
    monitored_test,
    monitoring_logs_dir,
    test_monitor,
)

# Re-export monitoring fixtures for CI tests
__all__ = [
    "monitoring_logs_dir",
    "test_monitor",
    "monitored_test",
    "error_analyzer",
    "ci_environment",
    "parallel_executor",
]


@pytest.fixture(scope="session")
def ci_environment():
    """Simulate CI/CD environment characteristics."""
    import os

    # Store original environment
    original_env = os.environ.copy()

    # Set CI environment variables
    ci_vars = {
        "CI": "true",
        "CONTINUOUS_INTEGRATION": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW": "Test Suite",
        "GITHUB_RUN_ID": "test_run_12345",
        "RUNNER_OS": "Linux",
        "GITHUB_REF": "refs/heads/test-branch",
        "GITHUB_SHA": "abc123def456",
    }

    # Apply CI environment
    for key, value in ci_vars.items():
        os.environ[key] = value

    yield {"is_ci": True, "platform": "github_actions", "environment_vars": ci_vars}

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(scope="function")
def parallel_executor():
    """Provide parallel execution utilities for CI tests."""
    import concurrent.futures
    import threading

    class ParallelTestExecutor:
        def __init__(self, max_workers=3):
            self.max_workers = max_workers
            self.active_threads = set()

        def execute_parallel(self, tasks):
            """Execute tasks in parallel and return results."""
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = []

                for task_name, task_func, *args in tasks:
                    future = executor.submit(task_func, *args)
                    future.task_name = task_name
                    futures.append(future)

                results = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                        results.append(
                            {
                                "task_name": future.task_name,
                                "result": result,
                                "success": True,
                                "error": None,
                            }
                        )
                    except Exception as e:
                        results.append(
                            {
                                "task_name": future.task_name,
                                "result": None,
                                "success": False,
                                "error": str(e),
                            }
                        )

                return results

        def get_thread_info(self):
            """Get current thread information."""
            return {
                "thread_id": threading.get_ident(),
                "active_count": threading.active_count(),
            }

    return ParallelTestExecutor()


@pytest.fixture(scope="function")
def performance_tracker():
    """Track performance metrics during CI tests."""
    import time

    import psutil

    class PerformanceTracker:
        def __init__(self):
            self.start_time = time.time()
            self.process = psutil.Process()
            self.measurements = []

        def start_measurement(self, operation_name):
            """Start measuring an operation."""
            return {
                "operation": operation_name,
                "start_time": time.time(),
                "start_memory": self.process.memory_info().rss / 1024 / 1024,  # MB
                "start_cpu": self.process.cpu_percent(),
            }

        def end_measurement(self, measurement_context):
            """End measuring an operation."""
            end_time = time.time()
            end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            end_cpu = self.process.cpu_percent()

            measurement = {
                "operation": measurement_context["operation"],
                "duration": end_time - measurement_context["start_time"],
                "memory_delta": end_memory - measurement_context["start_memory"],
                "cpu_delta": end_cpu - measurement_context["start_cpu"],
                "timestamp": end_time,
            }

            self.measurements.append(measurement)
            return measurement

        def get_summary(self):
            """Get performance measurement summary."""
            if not self.measurements:
                return {"total_measurements": 0}

            total_duration = sum(m["duration"] for m in self.measurements)
            avg_duration = total_duration / len(self.measurements)
            max_memory_delta = max(abs(m["memory_delta"]) for m in self.measurements)

            return {
                "total_measurements": len(self.measurements),
                "total_duration": total_duration,
                "average_duration": avg_duration,
                "max_memory_delta_mb": max_memory_delta,
                "measurements": self.measurements,
            }

    return PerformanceTracker()


@pytest.fixture(scope="function")
def test_artifact_manager(tmp_path):
    """Manage test artifacts for CI integration."""

    class TestArtifactManager:
        def __init__(self, artifacts_dir):
            self.artifacts_dir = artifacts_dir
            self.artifacts_dir.mkdir(exist_ok=True)
            self.created_artifacts = []

        def create_artifact(self, name, content, artifact_type="text"):
            """Create a test artifact."""
            artifact_path = self.artifacts_dir / name

            if artifact_type == "json":
                import json

                with open(artifact_path, "w") as f:
                    json.dump(content, f, indent=2)
            else:
                with open(artifact_path, "w") as f:
                    f.write(str(content))

            artifact_info = {
                "name": name,
                "path": artifact_path,
                "type": artifact_type,
                "size": artifact_path.stat().st_size,
                "created_at": time.time(),
            }

            self.created_artifacts.append(artifact_info)
            return artifact_info

        def list_artifacts(self):
            """List all created artifacts."""
            return self.created_artifacts

        def cleanup(self):
            """Clean up created artifacts."""
            for artifact in self.created_artifacts:
                if artifact["path"].exists():
                    artifact["path"].unlink()

    artifacts_dir = tmp_path / "ci_artifacts"
    manager = TestArtifactManager(artifacts_dir)

    yield manager

    # Cleanup after test
    manager.cleanup()
