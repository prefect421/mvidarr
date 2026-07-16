"""Tests for recovering videos stuck in DOWNLOADING status via the queue stop/clear actions.

The download queue (GET /api/metube/queue) is built from Video.status ==
DOWNLOADING, but the historical stop/clear-stuck endpoints only ever touched
the Download table. A video stuck at DOWNLOADING with no matching Download
row (or one already past "queued"/"downloading"/"pending") could never be
unstuck through the UI. These tests cover the service-layer fix.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.unified_download_service import UnifiedDownloadService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Artist.__table__, Video.__table__, Download.__table__]
    )
    return sessionmaker(bind=engine)


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _service():
    # Bypass __init__: it constructs a real YtDlpManager(), which requires a
    # yt-dlp executable on PATH. reset_stuck_video only touches the database.
    return UnifiedDownloadService.__new__(UnifiedDownloadService)


def _seed_video(
    session_factory, status=VideoStatus.DOWNLOADING, with_stuck_download=False
):
    session = session_factory()
    artist = Artist(name="Test Artist")
    session.add(artist)
    session.commit()

    video = Video(artist_id=artist.id, title="Test Song", status=status)
    session.add(video)
    session.commit()

    if with_stuck_download:
        download = Download(
            artist_id=artist.id,
            video_id=video.id,
            title="Test Song",
            original_url="https://example.com/watch",
            status="downloading",
        )
        session.add(download)
        session.commit()

    video_id = video.id
    session.close()
    return video_id


class TestResetStuckVideo:
    def test_returns_false_when_video_not_found(self, session_factory):
        service = _service()
        with patch_get_db(session_factory):
            assert service.reset_stuck_video(999999) is False

    def test_resets_video_with_no_backing_download_row(self, session_factory):
        video_id = _seed_video(session_factory, with_stuck_download=False)
        service = _service()

        with patch_get_db(session_factory):
            assert service.reset_stuck_video(video_id) is True

        session = session_factory()
        video = session.get(Video, video_id)
        assert video.status == VideoStatus.WANTED

    def test_resets_video_and_stops_backing_download_row(self, session_factory):
        video_id = _seed_video(session_factory, with_stuck_download=True)
        service = _service()

        with patch_get_db(session_factory):
            assert service.reset_stuck_video(video_id) is True

        session = session_factory()
        video = session.get(Video, video_id)
        assert video.status == VideoStatus.WANTED
        download = session.query(Download).filter(Download.video_id == video_id).first()
        assert download.status == "stopped"

    def test_leaves_completed_download_row_alone(self, session_factory):
        """A video's download row that already finished should not be touched."""
        session = session_factory()
        artist = Artist(name="Test Artist")
        session.add(artist)
        session.commit()
        video = Video(
            artist_id=artist.id, title="Test Song", status=VideoStatus.DOWNLOADING
        )
        session.add(video)
        session.commit()
        download = Download(
            artist_id=artist.id,
            video_id=video.id,
            title="Test Song",
            original_url="https://example.com/watch",
            status="completed",
        )
        session.add(download)
        session.commit()
        video_id, download_id = video.id, download.id
        session.close()

        service = _service()
        with patch_get_db(session_factory):
            assert service.reset_stuck_video(video_id) is True

        session = session_factory()
        video = session.get(Video, video_id)
        download = session.get(Download, download_id)
        assert video.status == VideoStatus.WANTED
        assert download.status == "completed"


def patch_get_db(session_factory):
    from unittest.mock import patch

    return patch(
        "src.database.connection.get_db", lambda: _fake_get_db(session_factory)
    )
