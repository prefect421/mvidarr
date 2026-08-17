"""Regression/feature test for #329: download_all_wanted_videos_internal()
must atomically claim each video (claim_video_for_download()) before
dispatching it -- today it dispatches first and only updates status
afterward, conditionally on success, meaning there is no claim attempt
at all before the download is fired off. A failed claim must skip that
video (not dispatch, not count as failed) and move to the next one.
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "services"


class TestInternalDownloadClaimsBeforeDispatch:
    def setup_method(self):
        self.source = (SRC_DIR / "video_batch_service.py").read_text()

    def _function_body(self, name):
        start = self.source.index(f"def {name}(")
        next_def = self.source.index("\ndef ", start + 10)
        return self.source[start:next_def]

    def test_calls_claim_video_for_download(self):
        body = self._function_body("download_all_wanted_videos_internal")
        assert "claim_video_for_download(" in body

    def test_claim_happens_before_the_dispatch_call(self):
        body = self._function_body("download_all_wanted_videos_internal")
        claim_index = body.index("claim_video_for_download(")
        dispatch_index = body.index("ytdlp_service.add_music_video_download(")
        assert claim_index < dispatch_index

    def test_a_failed_claim_does_not_dispatch(self):
        body = self._function_body("download_all_wanted_videos_internal")
        claim_index = body.index("claim_video_for_download(")
        dispatch_index = body.index("ytdlp_service.add_music_video_download(")
        # Between the claim and the dispatch call, there must be a
        # "continue" (or equivalent skip) reachable when the claim fails --
        # confirmed by requiring a "continue" to appear in that window.
        window = body[claim_index:dispatch_index]
        assert "continue" in window
