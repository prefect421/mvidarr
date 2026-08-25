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
        assert "claim_video_for_redownload" in source

    def test_claim_is_called_before_dispatch(self):
        source = _function_source("bulk_download_videos")
        # Anchor on the actual call site (asyncio.to_thread(...)), not
        # the earlier local `from ... import claim_video_for_redownload`
        # statement, which also contains this substring.
        claim_pos = source.index("asyncio.to_thread(claim_video_for_redownload")
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
        # Anchor on the actual call site (asyncio.to_thread(...)), not
        # the earlier local `from ... import claim_video_for_redownload`
        # statement, which also contains this substring.
        claim_pos = source.index("asyncio.to_thread(claim_video_for_redownload")
        download_row_pos = source.index("download = Download(")
        assert url_resolution_pos < claim_pos < download_row_pos

    def test_skips_dispatch_when_claim_fails(self):
        source = _function_source("bulk_download_videos")
        # The claim-failure branch must `continue` rather than falling
        # through to dispatch -- assert the claim call is immediately
        # followed (within a small window) by a continue statement.
        # Anchor on the actual call site (asyncio.to_thread(...)), not
        # the earlier local `from ... import claim_video_for_redownload`
        # statement, which also contains this substring.
        claim_pos = source.index("asyncio.to_thread(claim_video_for_redownload")
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


class TestBulkDownloadRevertPath:
    """Static source-assertion tests for the revert-path gaps closed by
    the final-review fix wave (#377 Finding 3): bulk_download_videos()
    had a full claim-then-dispatch treatment but no revert path, unlike
    the two single-video endpoints. See
    test_single_video_download_claims_before_dispatch.py for the same
    style of check applied to those endpoints."""

    def test_captures_original_status_before_claiming(self):
        """Must snapshot video.status before calling the claim, so a
        later failure can revert to the real pre-claim status instead
        of a hardcoded WANTED."""
        source = _function_source("bulk_download_videos")
        original_status_pos = source.index("original_status = video.status")
        # Anchor on the actual call site (asyncio.to_thread(...)), not
        # the earlier local `from ... import claim_video_for_redownload`
        # statement, which also contains this substring.
        claim_pos = source.index("asyncio.to_thread(claim_video_for_redownload")
        assert original_status_pos < claim_pos

    def test_terminal_commit_moved_inside_loop_right_after_flush(self):
        """The single end-of-loop `session.commit()` this task fixes
        must be gone -- replaced by a per-video commit immediately after
        `session.flush()`, narrowing the blast radius of a commit
        failure from 'the whole batch' to 'one video' and collapsing the
        FK-referencing flush's lock hold time to a single row."""
        source = _function_source("bulk_download_videos")

        # The old whole-loop-terminal commit (dedented back to the
        # try-block's outer level, directly before the summary log line)
        # must no longer be present.
        old_terminal_commit = (
            '        session.commit()\n\n        logger.info(f"Bulk queued'
        )
        assert old_terminal_commit not in source

        # A commit must now appear shortly after the Download-row flush.
        flush_marker = "session.flush()  # Get the download ID"
        flush_pos = source.index(flush_marker)
        window = source[flush_pos : flush_pos + 1200]
        assert "session.commit()" in window

    def test_reverts_to_original_status_in_exception_handler(self):
        """The per-video `except Exception as e:` handler must revert a
        successfully-claimed video back to its real pre-claim status --
        via a fresh session, not the (possibly broken) request session --
        mirroring download_all_wanted_videos_internal()'s
        revert-via-fresh-session pattern."""
        source = _function_source("bulk_download_videos")

        except_marker = (
            "except Exception as e:\n                video_id = getattr(video"
        )
        except_pos = source.index(except_marker)
        except_to_end = source[except_pos:]

        assert "claimed" in except_to_end
        assert "get_db()" in except_to_end
        assert "revert_video.status = original_status" in except_to_end
        # Must not fall back to a hardcoded WANTED.
        assert "revert_video.status = VideoStatus.WANTED" not in source

    def test_claimed_flag_reset_and_set_per_iteration(self):
        """`claimed` must be initialized False at the top of each loop
        iteration (not once outside the loop) and flipped True only
        after a successful claim -- otherwise a claim success for video N
        would incorrectly trigger a revert attempt for video N+1 if N+1
        fails before ever attempting its own claim."""
        source = _function_source("bulk_download_videos")
        for_pos = source.index("for video in videos:")
        claim_success_pos = source.index(
            "await asyncio.to_thread(claim_video_for_redownload, video_id):"
        )
        between = source[for_pos:claim_success_pos]
        assert "claimed = False" in between
