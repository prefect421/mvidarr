"""Fix for #444 (live-reported): clicking Retry on a failed download made
it vanish from both the download queue and history widgets. A couple
minutes later it silently appeared as downloaded, with no trace of the
retry ever having happened.

Two compounding bugs, both in DownloadServiceAdapter.retry_download():

1. It never actually re-dispatched anything -- it just set
   status="pending" and returned success, on the apparent assumption
   something else would notice and process it. Nothing does:
   process_queued_downloads() (the only code that queries for "pending"
   downloads) is only reachable via a manual POST /api/metube/
   process-queue call, never triggered automatically. The eventual
   "appeared as downloaded" was an unrelated coincidence -- most likely
   the separate auto-download scheduler independently redownloading the
   same still-eligible video through its own normal path -- not this
   retry succeeding.
2. "pending" isn't a status either the queue view
   (get_download_queue: queued/downloading) or the history view
   (get_download_history: completed/failed/cancelled) recognizes, so a
   download genuinely left at "pending" for any reason is invisible in
   both places -- exactly matching the reported symptom.

Fix: retry_download() now actually claims the video
(claim_video_for_redownload(), the same helper videos_downloads.py's
functions already use) and dispatches through
add_music_video_download(), mirroring the claim-then-dispatch-then-
revert-on-failure pattern established there. On success the download
settles at "queued" (a status the queue view recognizes); on failure it
reverts to "failed" with a real error message and the video's real
pre-claim status, exactly where it started.

Uses tests/unit/conftest.py's _wire_real_sqlite_db fixture (real SQLite
behind get_db(), the same real, unpatched database access
retry_download() and claim_video_for_redownload() actually use) rather
than mocking session objects -- this file needed Download.__table__
added to that fixture's schema creation, which it didn't have before
(only Artist/Video).
"""

from unittest.mock import patch

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.download_service_adapter import DownloadServiceAdapter


@pytest.fixture
def seeded_failed_download():
    """A video + a failed Download row pointing at it, ready to retry."""
    with get_db() as session:
        artist = Artist(name="Test Artist")
        session.add(artist)
        session.flush()

        video = Video(
            artist_id=artist.id,
            title="Test Song",
            status=VideoStatus.FAILED,
            url="https://youtube.com/watch?v=abc123",
            youtube_id="abc123",
        )
        session.add(video)
        session.flush()

        download = Download(
            artist_id=artist.id,
            video_id=video.id,
            title="Test Song",
            original_url="https://youtube.com/watch?v=abc123",
            status="failed",
            error_message="yt-dlp exploded",
        )
        session.add(download)
        session.flush()

        video_id = video.id
        download_id = download.id

    return video_id, download_id


def _adapter():
    """DownloadServiceAdapter.__init__() does real filesystem/settings
    work (_load_settings(), _restore_cookies_from_database()) that isn't
    relevant here -- bypass it via __new__, matching the established
    pattern for constructor-heavy classes elsewhere in this test suite
    (e.g. test_youtube_download_engine_pure_helpers.py)."""
    return DownloadServiceAdapter.__new__(DownloadServiceAdapter)


class TestRetryDownloadActuallyRedispatches:
    def test_successful_retry_settles_at_queued_not_pending(
        self, seeded_failed_download
    ):
        video_id, download_id = seeded_failed_download
        adapter = _adapter()

        with patch.object(
            DownloadServiceAdapter,
            "add_music_video_download",
            return_value={"success": True, "id": "job-1"},
        ) as mock_dispatch:
            result = adapter.retry_download(download_id)

        assert result["success"] is True
        mock_dispatch.assert_called_once()

        with get_db() as session:
            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            # The exact bug: this used to be "pending" -- a status
            # neither the queue nor the history view recognizes, so the
            # download vanished from both.
            assert download.status == "queued"
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.DOWNLOADING

    def test_dispatch_failure_reverts_to_failed_with_a_real_error(
        self, seeded_failed_download
    ):
        video_id, download_id = seeded_failed_download
        adapter = _adapter()

        with patch.object(
            DownloadServiceAdapter,
            "add_music_video_download",
            return_value={"success": False, "error": "disk full"},
        ):
            result = adapter.retry_download(download_id)

        assert result["success"] is False
        assert "disk full" in result["error"]

        with get_db() as session:
            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            assert download.status == "failed"
            assert "disk full" in download.error_message
            video = session.query(Video).filter(Video.id == video_id).first()
            # Reverted to the real pre-claim status (FAILED), not left
            # stuck at DOWNLOADING and not reset to some hardcoded value.
            assert video.status == VideoStatus.FAILED

    def test_dispatch_exception_reverts_to_failed(self, seeded_failed_download):
        video_id, download_id = seeded_failed_download
        adapter = _adapter()

        with patch.object(
            DownloadServiceAdapter,
            "add_music_video_download",
            side_effect=RuntimeError("connection reset"),
        ):
            result = adapter.retry_download(download_id)

        assert result["success"] is False

        with get_db() as session:
            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            assert download.status == "failed"
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.FAILED

    def test_download_not_found_reports_a_clear_error(self):
        adapter = _adapter()
        result = adapter.retry_download(999999)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_refuses_to_retry_a_download_that_is_not_retriable(
        self, seeded_failed_download
    ):
        video_id, download_id = seeded_failed_download
        with get_db() as session:
            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            download.status = "queued"  # already active, not retriable

        adapter = _adapter()
        with patch.object(
            DownloadServiceAdapter, "add_music_video_download"
        ) as mock_dispatch:
            result = adapter.retry_download(download_id)

        assert result["success"] is False
        mock_dispatch.assert_not_called()
