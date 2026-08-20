"""Tests for health_monitoring.py's get_recent_logs() path sandboxing fix.
Live investigation found this did a bare open(log_file, ...) on a fully
caller-controlled path with zero validation -- GET /api/health/logs?log_file=/etc/passwd
(or any file the app process can read) would return its contents. Fixed by
resolving the caller-supplied path and rejecting anything outside
Config.LOGS_DIR.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.services.health_monitoring import get_disk_usage, get_recent_logs


class TestGetRecentLogsSandboxing:
    def test_path_outside_logs_directory_is_rejected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("SECRET CONTENT\n")
            outside_path = f.name

        try:
            result = get_recent_logs(log_file=outside_path, lines=10)
            joined = "\n".join(result)
            assert "SECRET CONTENT" not in joined
        finally:
            os.unlink(outside_path)

    def test_path_traversal_attempt_is_rejected(self):
        result = get_recent_logs(log_file="/etc/passwd", lines=10)
        joined = "\n".join(result)
        assert "root:" not in joined

    def test_default_search_behavior_unchanged_when_log_file_is_none(self):
        # Must not raise, and must still return SOME list (either found
        # content or the "no log file found" message) -- proves the
        # log_file=None branch's existing default-search logic is untouched.
        result = get_recent_logs(log_file=None, lines=10)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_path_inside_logs_directory_still_works(self):
        from src.config.config import Config

        logs_dir = Path(Config.LOGS_DIR)
        logs_dir.mkdir(parents=True, exist_ok=True)
        test_log = logs_dir / "test_sandboxing_probe.log"
        test_log.write_text("line one\nline two\n")

        try:
            result = get_recent_logs(log_file=str(test_log), lines=10)
            joined = "\n".join(result)
            assert "line one" in joined
            assert "line two" in joined
        finally:
            test_log.unlink()


class TestGetDiskUsageNoLongerAcceptsArbitraryPaths:
    def test_paths_parameter_removed(self):
        import inspect

        sig = inspect.signature(get_disk_usage)
        assert "paths" not in sig.parameters

    def test_returns_the_fixed_default_paths(self):
        # Anchored to Config.DATA_DIR (which resolves to /app/data in
        # Docker, but not in a native-service/dev deployment -- see
        # health_monitoring.py's get_disk_usage() docstring), not a
        # hardcoded "/app/data" literal, so this must check against the
        # real constant to hold in both environments.
        from src.config.config import Config

        result = get_disk_usage()
        assert str(Config.DATA_DIR) in result
