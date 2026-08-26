"""Real (SQLite-backed) behavioral tests for claim_video_for_redownload()
(#377). See tests/unit/conftest.py's _REAL_DB_MODULES for why this test
module gets a real, unpatched get_db() instead of mocks.
"""

from datetime import datetime

import pytest

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.video_batch_service import claim_video_for_redownload


@pytest.fixture
def artist():
    with get_db() as session:
        a = Artist(name="Test Artist")
        session.add(a)
        session.flush()
        artist_id = a.id
    return artist_id


def _make_video(artist_id, status):
    with get_db() as session:
        v = Video(
            title="Test Video",
            artist_id=artist_id,
            status=status,
            youtube_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            discovered_date=datetime.utcnow(),
        )
        session.add(v)
        session.flush()
        return v.id


class TestClaimVideoForRedownload:
    def test_claims_a_wanted_video(self, artist):
        video_id = _make_video(artist, VideoStatus.WANTED)
        assert claim_video_for_redownload(video_id) is True
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.DOWNLOADING

    def test_claims_a_failed_video(self, artist):
        """Unlike claim_video_for_download() (WANTED-only), this must
        succeed for a FAILED video -- retrying a failed download is a
        supported use case in all 3 endpoints this backs."""
        video_id = _make_video(artist, VideoStatus.FAILED)
        assert claim_video_for_redownload(video_id) is True
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.DOWNLOADING

    def test_claims_a_downloaded_video(self, artist):
        """force_redownload support: must succeed even from DOWNLOADED."""
        video_id = _make_video(artist, VideoStatus.DOWNLOADED)
        assert claim_video_for_redownload(video_id) is True
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.DOWNLOADING

    def test_claims_a_monitored_video(self, artist):
        video_id = _make_video(artist, VideoStatus.MONITORED)
        assert claim_video_for_redownload(video_id) is True

    def test_refuses_a_video_already_downloading(self, artist):
        video_id = _make_video(artist, VideoStatus.DOWNLOADING)
        assert claim_video_for_redownload(video_id) is False
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            assert video.status == VideoStatus.DOWNLOADING  # unchanged

    def test_second_claim_on_the_same_video_fails(self, artist):
        video_id = _make_video(artist, VideoStatus.WANTED)
        assert claim_video_for_redownload(video_id) is True
        assert claim_video_for_redownload(video_id) is False

    def test_returns_false_for_a_nonexistent_video(self):
        assert claim_video_for_redownload(999999) is False
