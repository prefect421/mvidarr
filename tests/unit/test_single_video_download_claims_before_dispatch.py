"""Static source-assertion tests for queue_video_download() and
queue_download_video()'s claim wiring, and the fix to their
revert-on-failure status bug (#377).
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


class TestQueueVideoDownloadClaimsBeforeDispatch:
    FUNCTION_NAME = "queue_video_download"

    def test_calls_claim_video_for_redownload(self):
        source = _function_source(self.FUNCTION_NAME)
        assert "claim_video_for_redownload(" in source

    def test_captures_original_status_before_claiming(self):
        """Must snapshot video.status before calling the claim, so a
        dispatch failure can revert to the real pre-claim status
        instead of a hardcoded WANTED (#377 design, Component 2)."""
        source = _function_source(self.FUNCTION_NAME)
        original_status_pos = source.index("original_status")
        claim_pos = source.index("claim_video_for_redownload(")
        assert original_status_pos < claim_pos

    def test_reverts_to_original_status_not_hardcoded_wanted(self):
        source = _function_source(self.FUNCTION_NAME)
        assert "video.status = original_status" in source
        assert "video.status = VideoStatus.WANTED" not in source

    def test_no_longer_unconditionally_sets_downloading_status_before_claim(self):
        source = _function_source(self.FUNCTION_NAME)
        # The old unconditional write must be gone; the claim now owns
        # the WANTED/etc-to-DOWNLOADING transition. (DOWNLOADING will
        # still appear in the claim call's arguments, so check for the
        # specific old assignment statement, not a bare substring.)
        assert (
            "video.status = VideoStatus.DOWNLOADING\n        video.updated_at"
            not in source
        )


class TestQueueDownloadVideoClaimsBeforeDispatch(
    TestQueueVideoDownloadClaimsBeforeDispatch
):
    FUNCTION_NAME = "queue_download_video"
