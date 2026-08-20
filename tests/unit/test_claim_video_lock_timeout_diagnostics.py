"""Tests for diagnostic instrumentation added to
claim_video_for_redownload() after a live-reported bug: multiple videos
(106, 133, others) intermittently failed to claim with
`pymysql.err.OperationalError (1205, 'Lock wait timeout exceeded')`,
recurring in bursts over several minutes. Direct investigation (manual
reproduction, live information_schema.innodb_trx queries between
failures) could not catch the blocking transaction in the act -- by the
time each failure was noticed, the lock had already cleared.

Since the root cause couldn't be pinned down after live investigation,
this adds diagnostic capture: when a lock-wait-timeout is caught, query
information_schema.innodb_trx / processlist via a fresh connection and
log what else was active at that moment, so the NEXT occurrence leaves
hard evidence instead of requiring another live chase. This is
diagnostic-only and must never itself raise past this function or
change its return value -- claim_video_for_redownload() must keep
behaving exactly as before on every path.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "services" / "video_batch_service.py"
)


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestDiagnosticCaptureIsPresent:
    def test_detects_lock_wait_timeout_specifically(self):
        source = _function_source("claim_video_for_redownload")
        assert "1205" in source or "Lock wait timeout" in source

    def test_queries_innodb_trx_for_diagnostics(self):
        source = _function_source("claim_video_for_redownload")
        assert "innodb_trx" in source

    def test_diagnostic_capture_is_itself_exception_safe(self):
        """The diagnostic query must be wrapped in its own try/except --
        a failure to gather diagnostics (e.g. against non-MariaDB
        backends, or a second connection failure) must never escape and
        must never replace the original error being diagnosed."""
        source = _function_source("claim_video_for_redownload")
        # Count try/except pairs: the original function had exactly one
        # (the outer claim try/except). Adding diagnostic capture with
        # its own safety net means there must now be at least two.
        try_count = source.count("try:")
        assert try_count >= 2


class TestDiagnosticCaptureNeverChangesBehavior:
    def test_still_returns_false_on_any_claim_failure(self):
        source = _function_source("claim_video_for_redownload")
        assert "return False" in source

    def test_original_error_still_logged(self):
        source = _function_source("claim_video_for_redownload")
        assert "Failed to claim video" in source


class TestDiagnosticCaptureBehavioral:
    """Real behavioral test: force claim_video_for_redownload() to hit
    a lock-wait-timeout-shaped exception and confirm the function still
    returns False cleanly even if the diagnostic-gathering code itself
    also raises (e.g. because this test's fake DB has no
    information_schema.innodb_trx to query)."""

    def test_returns_false_even_if_diagnostic_query_itself_fails(self):
        import src.database.connection as db_connection
        from src.services.video_batch_service import claim_video_for_redownload

        class FakeConn:
            def execute(self, *args, **kwargs):
                raise Exception("(1205, 'Lock wait timeout exceeded')")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeEngine:
            def begin(self):
                return FakeConn()

            def connect(self):
                raise Exception("diagnostic connection also failed")

        fake_db_manager = MagicMock()
        fake_db_manager.create_engine.return_value = FakeEngine()

        with patch.object(db_connection, "db_manager", fake_db_manager):
            result = claim_video_for_redownload(999999)

        assert result is False
