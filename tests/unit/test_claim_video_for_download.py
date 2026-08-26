"""Regression/feature test for #329: two independently-implemented
"download all wanted videos" functions (bulk_download_wanted_videos() in
videos_downloads.py, download_all_wanted_videos_internal() in this same
module) could both select and dispatch the same WANTED video
concurrently -- one via a FastAPI background thread, one via a Celery
worker (a separate OS process) -- with no coordination. Whichever
finished writing last won, so a genuine success could be silently
overwritten by a stale duplicate-dispatch failure.

claim_video_for_download() closes the race: a single atomic
UPDATE ... WHERE status = 'WANTED' that only one concurrent caller can
ever win. Real behavioral tests against a real (SQLite-backed) DB, not
mocks -- video_batch_service.py imports cleanly in this test venv
(unlike unified_download_service.py, which has a module-level
yt-dlp-dependent singleton).
"""

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.video_batch_service import claim_video_for_download


@pytest.fixture
def wanted_video():
    """Creates a real WANTED video row, yields its id, cleans up after."""
    with get_db() as session:
        artist = Artist(name="Test Artist For Claim")
        session.add(artist)
        session.flush()
        video = Video(
            artist_id=artist.id,
            title="Test Video For Claim",
            status=VideoStatus.WANTED,
        )
        session.add(video)
        session.commit()
        video_id = video.id
    yield video_id
    with get_db() as session:
        session.query(Video).filter(Video.id == video_id).delete()
        session.query(Artist).filter(Artist.id == artist.id).delete()
        session.commit()


class TestClaimVideoForDownload:
    def test_claims_a_wanted_video(self, wanted_video):
        result = claim_video_for_download(wanted_video)
        assert result is True

        with get_db() as session:
            video = session.query(Video).filter(Video.id == wanted_video).first()
            assert video.status == VideoStatus.DOWNLOADING

    def test_second_claim_on_the_same_video_fails(self, wanted_video):
        first = claim_video_for_download(wanted_video)
        second = claim_video_for_download(wanted_video)

        assert first is True
        assert second is False

    def test_returns_false_for_a_video_that_is_not_wanted(self, wanted_video):
        with get_db() as session:
            video = session.query(Video).filter(Video.id == wanted_video).first()
            video.status = VideoStatus.DOWNLOADED
            session.commit()

        result = claim_video_for_download(wanted_video)

        assert result is False
        with get_db() as session:
            video = session.query(Video).filter(Video.id == wanted_video).first()
            # Must not have been touched -- still DOWNLOADED, not DOWNLOADING.
            assert video.status == VideoStatus.DOWNLOADED

    def test_returns_false_for_a_nonexistent_video(self):
        result = claim_video_for_download(999999999)
        assert result is False
