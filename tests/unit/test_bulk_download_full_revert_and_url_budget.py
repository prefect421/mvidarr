"""Static source-assertion tests for bulk_download_videos()'s (#379.6,
#379.3, #380.1) fixes: full revert on ANY dispatch failure (not just
raised exceptions), a fresh original_status read for every video (not
just relying on expire-on-commit for videos after the first), and a
bulk-specific URL-resolution time budget.
"""

import ast
from pathlib import Path

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_downloads.py"
)


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestBulkDownloadFullRevertOnDispatchFailure:
    def test_checks_result_success_key_not_just_exceptions(self):
        source = _function_source("bulk_download_videos")
        assert 'result.get("success")' in source or "result and result.get" in source

    def test_reverts_video_status_on_falsy_result(self):
        source = _function_source("bulk_download_videos")
        assert "video.status = original_status" in source

    def test_marks_download_row_failed_on_dispatch_failure(self):
        source = _function_source("bulk_download_videos")
        assert 'download.status = "failed"' in source
        assert "download.error_message" in source

    def test_tracks_a_separate_failed_count(self):
        source = _function_source("bulk_download_videos")
        assert "failed_count" in source


class TestBulkDownloadOriginalStatusFreshness:
    def test_refreshes_status_before_capturing_original_status(self):
        source = _function_source("bulk_download_videos")
        refresh_pos = source.index('session.refresh(video, attribute_names=["status"])')
        original_status_pos = source.index("original_status = video.status")
        assert refresh_pos < original_status_pos


class TestBulkDownloadUrlResolutionBudget:
    def test_defines_a_bulk_specific_timeout_and_budget(self):
        source = _function_source("bulk_download_videos")
        assert "BULK_URL_RESOLUTION_TIMEOUT_SECONDS" in source
        assert "BULK_URL_RESOLUTION_BUDGET_SECONDS" in source

    def test_passes_the_bulk_timeout_to_resolve_video_url(self):
        source = _function_source("bulk_download_videos")
        assert "timeout=BULK_URL_RESOLUTION_TIMEOUT_SECONDS" in source

    def test_stops_resolving_once_the_budget_is_exhausted(self):
        source = _function_source("bulk_download_videos")
        assert "BULK_URL_RESOLUTION_BUDGET_SECONDS" in source
        # the budget check must guard the resolve_video_url call, not
        # just be declared and unused
        budget_check_pos = source.index("url_resolution_time_used")
        resolve_call_pos = source.index("await resolve_video_url(")
        assert budget_check_pos < resolve_call_pos
