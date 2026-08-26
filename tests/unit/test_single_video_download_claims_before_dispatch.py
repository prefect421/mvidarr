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

    def test_download_row_commit_is_inside_dispatch_try_block(self):
        """The commit that persists the staged Download row (immediately
        after claim success) must live inside the same try/except that
        reverts video.status on failure -- not before it. Otherwise, if
        that commit itself raises (lock timeout, transient DB error,
        constraint violation), only the outer function-level except
        catches it, and video.status is left stuck at DOWNLOADING since
        the claim already committed it durably on its own separate
        connection (#377 fix round 1)."""
        source = _function_source(self.FUNCTION_NAME)

        # The dispatch try/except is nested one level deeper (8-space
        # indent) than the function's outer try/except (4-space indent),
        # so anchor on indentation to unambiguously find the right one.
        inner_try_marker = "\n        try:\n"
        except_marker = "except Exception as download_error:"

        claim_pos = source.index("claim_video_for_redownload(")
        try_pos = source.index(inner_try_marker)
        except_pos = source.index(except_marker)
        assert claim_pos < try_pos < except_pos

        # No bare session.commit() may sit between claim success and the
        # dispatch try block -- that's exactly the gap that let a commit
        # failure escape the revert logic.
        between_claim_and_try = source[claim_pos:try_pos]
        assert "session.commit()" not in between_claim_and_try

        # The Download-row-persisting commit must be inside the try body.
        try_body = source[try_pos:except_pos]
        assert "session.commit()" in try_body

        # And the revert-on-failure logic must still be in the except
        # handler, downstream of that commit.
        except_to_end = source[except_pos:]
        assert "video.status = original_status" in except_to_end

    def test_claim_refused_response_includes_download_id(self):
        source = _function_source(self.FUNCTION_NAME)
        assert '"download_id": None' in source


class TestQueueDownloadVideoClaimsBeforeDispatch(
    TestQueueVideoDownloadClaimsBeforeDispatch
):
    FUNCTION_NAME = "queue_download_video"

    def test_claim_refused_response_includes_download_id(self):
        # queue_download_video()'s claim-refused response does not
        # include a download_id key today, and this fix is scoped to
        # queue_video_download() alone per #380.2 -- don't force this
        # assertion onto a function whose response shape doesn't match.
        pass
