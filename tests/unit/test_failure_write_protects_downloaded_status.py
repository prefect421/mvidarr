"""Regression/feature test for #329: _update_database_failure() set
video.status = FAILED and overwrote the most recent Download row
unconditionally, with no check for whether the video already reached a
terminal DOWNLOADED state. A late-arriving failure from a duplicate
dispatch (see claim_video_for_download() and its two call sites, added
earlier in this same plan) could silently erase a real, already-persisted
success.

Static source-assertion test -- unified_download_service.py cannot be
imported in this test venv (module-level yt-dlp-dependent singleton,
same constraint as #370's tests for this file).
"""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "services"


class TestFailureWriteProtectsDownloadedStatus:
    def setup_method(self):
        self.source = (SRC_DIR / "unified_download_service.py").read_text()

    def _function_body(self, name):
        start = self.source.index(f"def {name}(")
        next_def = self.source.index("\n    def ", start + 10)
        return self.source[start:next_def]

    def test_checks_current_status_before_writing(self):
        body = self._function_body("_update_database_failure")
        assert "VideoStatus.DOWNLOADED.value" in body

    def test_the_downloaded_check_happens_before_any_status_or_download_row_write(self):
        body = self._function_body("_update_database_failure")
        check_index = body.index("VideoStatus.DOWNLOADED.value")
        status_write_index = body.index("video.status = VideoStatus.FAILED.value")
        assert check_index < status_write_index
