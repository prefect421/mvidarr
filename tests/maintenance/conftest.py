"""
Test Maintenance Configuration
=============================

Fixtures and configuration for test maintenance, health monitoring, and environment management tests.
"""

import sys
from pathlib import Path

import pytest

# Add monitoring fixtures to maintenance tests
sys.path.append(str(Path(__file__).parent.parent / "monitoring"))

from tests.monitoring.conftest import (
    error_analyzer,
    monitored_test,
    monitoring_logs_dir,
    test_monitor,
)

# Re-export monitoring fixtures for maintenance tests
__all__ = [
    "monitoring_logs_dir",
    "test_monitor",
    "monitored_test",
    "error_analyzer",
    "maintenance_workspace",
    "test_data_factory",
]


@pytest.fixture(scope="function")
def maintenance_workspace(tmp_path):
    """Provide a temporary workspace for maintenance testing."""

    class MaintenanceWorkspace:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.artifacts_dir = base_path / "artifacts"
            self.logs_dir = base_path / "logs"
            self.temp_dir = base_path / "temp"
            self.environments_dir = base_path / "environments"

            # Create directory structure
            for directory in [
                self.artifacts_dir,
                self.logs_dir,
                self.temp_dir,
                self.environments_dir,
            ]:
                directory.mkdir(parents=True, exist_ok=True)

            self.created_files = []

        def create_test_artifact(
            self, name: str, content: str = "test content", artifact_type: str = "test"
        ):
            """Create a test artifact file."""
            if artifact_type == "screenshot":
                artifact_path = self.artifacts_dir / "screenshots" / name
                artifact_path.parent.mkdir(exist_ok=True)
            elif artifact_type == "log":
                artifact_path = self.logs_dir / name
            elif artifact_type == "coverage":
                artifact_path = self.artifacts_dir / "coverage" / name
                artifact_path.parent.mkdir(exist_ok=True)
            else:
                artifact_path = self.temp_dir / name

            artifact_path.write_text(content)
            self.created_files.append(artifact_path)
            return artifact_path

        def create_test_environment_structure(
            self, env_name: str, env_type: str = "unit"
        ):
            """Create test environment directory structure."""
            env_dir = self.environments_dir / env_name
            env_dir.mkdir(exist_ok=True)

            if env_type == "integration":
                (env_dir / "database").mkdir(exist_ok=True)
                (env_dir / "services").mkdir(exist_ok=True)
            elif env_type == "visual":
                (env_dir / "screenshots").mkdir(exist_ok=True)
                (env_dir / "baselines").mkdir(exist_ok=True)
            elif env_type == "performance":
                (env_dir / "monitoring").mkdir(exist_ok=True)
                (env_dir / "results").mkdir(exist_ok=True)

            # Common directories
            (env_dir / "temp").mkdir(exist_ok=True)
            (env_dir / "logs").mkdir(exist_ok=True)

            return env_dir

        def get_artifact_paths(self, artifact_type: str = None):
            """Get paths of created artifacts, optionally filtered by type."""
            if artifact_type:
                return [f for f in self.created_files if artifact_type in str(f)]
            return self.created_files

        def cleanup(self):
            """Clean up created files and directories."""
            for file_path in self.created_files:
                if file_path.exists():
                    file_path.unlink()

    workspace = MaintenanceWorkspace(tmp_path)
    yield workspace
    workspace.cleanup()


@pytest.fixture(scope="function")
def test_data_factory():
    """Factory for creating test data structures."""
    import json
    from datetime import datetime, timedelta

    class TestDataFactory:
        def create_coverage_xml(
            self, overall_coverage: float = 80.0, files: dict = None
        ):
            """Create mock coverage XML content."""
            if files is None:
                files = {
                    "src/main.py": {
                        "coverage": 90.0,
                        "lines": [(1, 1), (2, 1), (3, 0), (4, 1)],
                    },
                    "src/utils.py": {
                        "coverage": 70.0,
                        "lines": [(1, 1), (2, 0), (3, 0), (4, 1)],
                    },
                }

            lines_covered = sum(
                len([line for line in file_data["lines"] if line[1] > 0])
                for file_data in files.values()
            )
            lines_valid = sum(len(file_data["lines"]) for file_data in files.values())

            xml_content = f"""<?xml version="1.0" ?>
<coverage version="4.5.4" timestamp="{int(datetime.now().timestamp())}" line-rate="{overall_coverage/100:.2f}" branch-rate="{(overall_coverage-5)/100:.2f}" lines-covered="{lines_covered}" lines-valid="{lines_valid}" branches-covered="0" branches-valid="0">
    <sources>
        <source>src</source>
    </sources>
    <packages>
        <package name="src" line-rate="{overall_coverage/100:.2f}" branch-rate="{(overall_coverage-5)/100:.2f}">
            <classes>"""

            for filename, file_data in files.items():
                xml_content += f"""
                <class name="{filename}" filename="{filename}" complexity="0.0" line-rate="{file_data['coverage']/100:.2f}" branch-rate="{(file_data['coverage']-5)/100:.2f}">
                    <methods>
                    </methods>
                    <lines>"""

                for line_num, hits in file_data["lines"]:
                    xml_content += f"""
                        <line number="{line_num}" hits="{hits}"/>"""

                xml_content += """
                    </lines>
                </class>"""

            xml_content += """
            </classes>
        </package>
    </packages>
</coverage>"""

            return xml_content

        def create_test_metrics_data(
            self, count: int = 10, base_coverage: float = 75.0
        ):
            """Create test metrics data over time."""
            base_time = datetime.now()
            metrics = []

            for i in range(count):
                # Add some variance to coverage
                coverage = (
                    base_coverage + (i * 2) + ((-1) ** i * 3)
                )  # Some up/down trend
                coverage = max(50.0, min(95.0, coverage))  # Keep within bounds

                metric = {
                    "timestamp": (base_time - timedelta(days=i)).isoformat(),
                    "total_lines": 1000 + i * 10,
                    "covered_lines": int((1000 + i * 10) * coverage / 100),
                    "coverage_percentage": coverage,
                    "branch_total": 500 + i * 5,
                    "branch_covered": int((500 + i * 5) * (coverage - 5) / 100),
                    "branch_percentage": coverage - 5,
                    "missing_lines": [
                        f"file{j}.py:{k}"
                        for j in range(1, 4)
                        for k in range(1, int((100 - coverage) / 10))
                    ],
                    "file_coverage": {
                        f"file{j}.py": coverage + ((-1) ** j * 5) for j in range(1, 6)
                    },
                }
                metrics.append(metric)

            return metrics

        def create_environment_configs(self, count: int = 4):
            """Create test environment configurations."""
            env_types = ["unit", "integration", "visual", "performance"]
            configs = []

            for i in range(count):
                env_type = env_types[i % len(env_types)]

                base_config = {
                    "type": env_type,
                    "created_at": (datetime.now() - timedelta(hours=i * 2)).isoformat(),
                    "python_version": "3.12",
                    "isolation": "process",
                }

                if env_type == "integration":
                    base_config.update(
                        {
                            "database": "sqlite",
                            "services": ["api", "cache", "worker"],
                            "ports": [5432, 6379, 5000],
                        }
                    )
                elif env_type == "visual":
                    base_config.update(
                        {
                            "browsers": ["chromium", "firefox"],
                            "screen_sizes": ["1280x720", "1920x1080"],
                            "headless": True,
                        }
                    )
                elif env_type == "performance":
                    base_config.update(
                        {
                            "load_profile": "standard",
                            "duration_minutes": 10,
                            "monitoring_enabled": True,
                        }
                    )

                configs.append(base_config)

            return configs

        def create_health_metrics(self, environment_id: str, metric_types: list = None):
            """Create health metrics for an environment."""
            if metric_types is None:
                metric_types = [
                    "test_duration",
                    "memory_usage",
                    "cpu_usage",
                    "failure_rate",
                ]

            metrics = []
            current_time = datetime.now()

            for i, metric_type in enumerate(metric_types):
                # Create different severity scenarios
                if metric_type == "test_duration":
                    values = [120.0, 350.0, 650.0]  # OK, Warning, Critical
                    thresholds = [300.0, 300.0, 300.0]
                    statuses = ["ok", "warning", "critical"]
                elif metric_type == "memory_usage":
                    values = [65.0, 85.0, 97.0]  # OK, Warning, Critical
                    thresholds = [80.0, 80.0, 80.0]
                    statuses = ["ok", "warning", "critical"]
                elif metric_type == "cpu_usage":
                    values = [45.0, 75.0, 92.0]  # OK, Warning, Critical
                    thresholds = [70.0, 70.0, 70.0]
                    statuses = ["ok", "warning", "critical"]
                else:  # failure_rate
                    values = [5.0, 15.0, 35.0]  # OK, Warning, Critical
                    thresholds = [10.0, 10.0, 10.0]
                    statuses = ["ok", "warning", "critical"]

                for j, (value, threshold, status) in enumerate(
                    zip(values, thresholds, statuses)
                ):
                    metric = {
                        "metric_name": metric_type,
                        "value": value,
                        "threshold": threshold,
                        "status": status,
                        "timestamp": (
                            current_time - timedelta(minutes=i * 10 + j * 5)
                        ).isoformat(),
                        "environment": environment_id,
                        "details": {
                            "measurement_id": f"{metric_type}_{i}_{j}",
                            "source": "test_data_factory",
                        },
                    }
                    metrics.append(metric)

            return metrics

        def create_maintenance_tasks(self, count: int = 5):
            """Create maintenance task configurations."""
            task_types = [
                "cleanup_artifacts",
                "scan_artifacts",
                "health_check",
                "environment_cleanup",
                "report_generation",
            ]
            schedules = ["daily", "weekly", "monthly", "hourly", "daily"]

            tasks = []
            base_time = datetime.now()

            for i in range(count):
                task_type = task_types[i % len(task_types)]
                schedule = schedules[i % len(schedules)]

                # Vary task status
                statuses = ["pending", "completed", "failed", "running"]
                status = statuses[i % len(statuses)]

                task = {
                    "task_id": f"maintenance_task_{i+1}",
                    "task_type": task_type,
                    "description": f"Automated {task_type.replace('_', ' ')} task",
                    "schedule": schedule,
                    "last_run": (
                        (base_time - timedelta(hours=i * 6)).isoformat()
                        if status != "pending"
                        else None
                    ),
                    "next_run": (base_time + timedelta(hours=i * 12)).isoformat(),
                    "status": status,
                    "metadata": self._get_task_metadata(task_type),
                }

                tasks.append(task)

            return tasks

        def _get_task_metadata(self, task_type: str):
            """Get metadata for specific task types."""
            if task_type == "cleanup_artifacts":
                return {
                    "max_age_days": 30,
                    "artifact_types": ["screenshots", "logs", "temporary"],
                }
            elif task_type == "scan_artifacts":
                return {
                    "scan_paths": ["/tmp/tests", "/tmp/artifacts"],
                    "include_hidden": False,
                }
            elif task_type == "health_check":
                return {
                    "check_types": ["memory", "disk", "cpu"],
                    "thresholds": {"memory": 80, "disk": 85, "cpu": 90},
                }
            elif task_type == "environment_cleanup":
                return {"max_age_hours": 24, "force_cleanup": False}
            else:  # report_generation
                return {
                    "report_types": ["health", "coverage", "performance"],
                    "format": "json",
                }

    return TestDataFactory()
