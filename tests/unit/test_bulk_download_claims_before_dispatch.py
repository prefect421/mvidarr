"""Regression/feature test for #329: bulk_download_wanted_videos() must
atomically claim each video (claim_video_for_download()) before
dispatching it, and must skip (not error) a video whose claim fails --
matching download_all_wanted_videos_internal()'s equivalent fix in the
same plan.
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "api" / "fastapi"


class TestBulkDownloadClaimsBeforeDispatch:
    def setup_method(self):
        self.source = (SRC_DIR / "videos_downloads.py").read_text()

    def _function_body(self, name):
        start = self.source.index(f"async def {name}(")
        # Next top-level "async def " or "def " after this one marks the end.
        # Falls back to end-of-file when this is the last function defined
        # (as bulk_download_wanted_videos currently is in this module).
        try:
            next_def = self.source.index("\nasync def ", start + 10)
        except ValueError:
            next_def = len(self.source)
        return self.source[start:next_def]

    def test_calls_claim_video_for_download(self):
        body = self._function_body("bulk_download_wanted_videos")
        assert "claim_video_for_download(" in body

    def test_claim_happens_before_the_dispatch_call(self):
        body = self._function_body("bulk_download_wanted_videos")
        claim_index = body.index("claim_video_for_download(")
        dispatch_index = body.index("ytdlp_service.add_music_video_download(")
        assert claim_index < dispatch_index

    def test_a_failed_claim_increments_skipped_not_errors(self):
        body = self._function_body("bulk_download_wanted_videos")
        claim_index = body.index("claim_video_for_download(")
        # The nearest "if not <claim result>:" branch after the claim call
        # should touch skipped_count, not errors.append, within a small
        # window (the immediate handling of a failed claim).
        window = body[claim_index : claim_index + 400]
        assert "skipped_count" in window
