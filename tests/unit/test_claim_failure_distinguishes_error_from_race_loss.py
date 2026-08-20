"""Tests for a live-reported bug: queue_video_download() and
queue_download_video() both treated ANY claim_video_for_redownload()
failure identically -- reporting "Video is currently downloading" to
the caller, with no trace left in download history. In practice this
message is only accurate when the video genuinely lost a race to a
concurrent claim (its status really is DOWNLOADING). If the claim call
instead failed because of a transient DB error (live-observed:
`pymysql.err.OperationalError` 1205 "Lock wait timeout exceeded"),
the video's status is NOT DOWNLOADING -- but the caller reported the
same misleading message anyway, and the staged (uncommitted) Download
row was silently discarded when the session closed, leaving the user
with no record that anything was attempted at all.

Fix: after a claim failure, re-check the video's actual status. Only
report "already downloading" when it genuinely is. Otherwise, roll back
the staged Download row explicitly and report a real, retriable error.
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


class TestQueueVideoDownloadDistinguishesClaimFailureCause:
    FUNCTION_NAME = "queue_video_download"

    def test_rechecks_video_status_after_claim_failure(self):
        source = _function_source(self.FUNCTION_NAME)
        claim_pos = source.index("if not claim_video_for_redownload(")
        refresh_pos = source.index('session.refresh(video, attribute_names=["status"])')
        assert claim_pos < refresh_pos

    def test_only_reports_already_downloading_when_status_genuinely_downloading(self):
        source = _function_source(self.FUNCTION_NAME)
        assert "if video.status == VideoStatus.DOWNLOADING:" in source

    def test_reports_a_real_error_when_status_is_not_downloading(self):
        source = _function_source(self.FUNCTION_NAME)
        # After the genuine-race-loss branch, the fallback path must
        # report success: False with a real, non-misleading message --
        # not silently return the same "currently downloading" text.
        downloading_check_pos = source.index(
            "if video.status == VideoStatus.DOWNLOADING:"
        )
        tail = source[downloading_check_pos:]
        assert '"success": False' in tail

    def test_explicitly_discards_the_staged_download_row_on_claim_error(self):
        source = _function_source(self.FUNCTION_NAME)
        downloading_check_pos = source.index(
            "if video.status == VideoStatus.DOWNLOADING:"
        )
        tail = source[downloading_check_pos:]
        assert "session.rollback()" in tail


class TestQueueDownloadVideoDistinguishesClaimFailureCause:
    FUNCTION_NAME = "queue_download_video"

    def test_rechecks_video_status_after_claim_failure(self):
        source = _function_source(self.FUNCTION_NAME)
        claim_pos = source.index("if not claim_video_for_redownload(")
        refresh_pos = source.index('session.refresh(video, attribute_names=["status"])')
        assert claim_pos < refresh_pos

    def test_only_reports_already_downloading_when_status_genuinely_downloading(self):
        source = _function_source(self.FUNCTION_NAME)
        assert "if video.status == VideoStatus.DOWNLOADING:" in source

    def test_reports_a_real_error_when_status_is_not_downloading(self):
        source = _function_source(self.FUNCTION_NAME)
        downloading_check_pos = source.index(
            "if video.status == VideoStatus.DOWNLOADING:"
        )
        tail = source[downloading_check_pos:]
        assert '"success": False' in tail

    def test_explicitly_discards_the_staged_download_row_on_claim_error(self):
        source = _function_source(self.FUNCTION_NAME)
        downloading_check_pos = source.index(
            "if video.status == VideoStatus.DOWNLOADING:"
        )
        tail = source[downloading_check_pos:]
        assert "session.rollback()" in tail
