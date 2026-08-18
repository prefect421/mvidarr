"""Static source-assertion tests for bulk_download_videos()'s claim
wiring (#377). See test_internal_download_claims_before_dispatch.py
(#329) for why this style is used instead of importing the module --
videos_downloads.py transitively imports a module-level
yt-dlp-dependent singleton that raises RuntimeError in this test venv.
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
    """Extract a top-level function's full source text by parsing the
    file with ast and slicing the original text using the node's
    line-number span (robust to decorators and to whichever function
    happens to follow it in the file)."""
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestBulkDownloadByIdsClaimsBeforeDispatch:
    def test_calls_claim_video_for_redownload(self):
        source = _function_source("bulk_download_videos")
        assert "claim_video_for_redownload(" in source

    def test_claim_is_called_before_dispatch(self):
        source = _function_source("bulk_download_videos")
        claim_pos = source.index("claim_video_for_redownload(")
        dispatch_pos = source.index("ytdlp_service.add_music_video_download(")
        assert claim_pos < dispatch_pos

    def test_claim_is_called_after_url_resolution(self):
        """Regression test for the reordering fix: the claim must not
        fire until the video's URL has been confirmed resolvable,
        otherwise a video whose URL can't be resolved gets stranded in
        DOWNLOADING status with no Download row and no way to be
        reclaimed by this endpoint. Assert the claim call's text
        position comes after the URL-resolution block's key marker
        text, and before the Download row is constructed."""
        source = _function_source("bulk_download_videos")
        url_resolution_pos = source.index("resolved_url = await resolve_video_url(")
        claim_pos = source.index("claim_video_for_redownload(")
        download_row_pos = source.index("download = Download(")
        assert url_resolution_pos < claim_pos < download_row_pos

    def test_skips_dispatch_when_claim_fails(self):
        source = _function_source("bulk_download_videos")
        # The claim-failure branch must `continue` rather than falling
        # through to dispatch -- assert the claim call is immediately
        # followed (within a small window) by a continue statement.
        claim_pos = source.index("claim_video_for_redownload(")
        window = source[claim_pos : claim_pos + 200]
        assert "continue" in window

    def test_no_longer_unconditionally_sets_downloading_status(self):
        """The manual video.status = VideoStatus.DOWNLOADING write must
        be gone -- claim_video_for_redownload() now owns that write."""
        source = _function_source("bulk_download_videos")
        assert "video.status = VideoStatus.DOWNLOADING" not in source

    def test_downloaded_check_compares_to_enum_not_string(self):
        """Regression test for the dead check this task also fixes:
        `video.status == "downloaded"` can never match, since
        Video.status hydrates as a VideoStatus enum member, not a
        string (same bug class as #329's Critical finding)."""
        source = _function_source("bulk_download_videos")
        assert 'video.status == "downloaded"' not in source
        assert "video.status == VideoStatus.DOWNLOADED" in source
