"""Regression test for issue #321: process_pending_downloads() crashed with
`AttributeError: 'Artist' object has no attribute 'replace'` when retrying a
previously-failed download.

Root cause: download_service_adapter.py's process_pending_downloads() passed
`artist=video.artist` (the Artist ORM object) into add_music_video_download,
instead of `video.artist.name` (a string) like every other of the 11 call
sites of that function in this codebase. The object flows unchanged into
FilenameCleanup.sanitize_folder_name(name), which unconditionally calls
name.replace(...) — hence the AttributeError.

Trigger: a user retries a failed/stopped download (retry_download() just
flips its status to "pending"), and the next process_pending_downloads()
run (scheduler-triggered) picks it up and crashes on this line.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.download_service_adapter import DownloadServiceAdapter
from src.utils.filename_cleanup import FilenameCleanup


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Artist.__table__, Video.__table__, Download.__table__]
    )
    return sessionmaker(bind=engine)


def _seed_pending_download(session_factory):
    session = session_factory()
    artist = Artist(name="Some Artist")
    session.add(artist)
    session.commit()

    video = Video(
        title="Some Video",
        artist_id=artist.id,
        url="https://youtube.com/watch?v=abc123",
        status=VideoStatus.WANTED,
    )
    session.add(video)
    session.commit()

    download = Download(
        video_id=video.id,
        artist_id=artist.id,
        title=video.title,
        original_url=video.url,
        status="pending",
        priority=1,
    )
    session.add(download)
    session.commit()
    session.close()


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    return patch(
        "src.database.connection.get_db",
        lambda: _fake_get_db(session_factory),
    )


class TestProcessPendingDownloadsArtistArgument:
    def test_passes_artist_name_string_not_the_artist_object(self, session_factory):
        _seed_pending_download(session_factory)
        adapter = DownloadServiceAdapter.__new__(DownloadServiceAdapter)

        captured = {}

        def fake_add_music_video_download(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        adapter.add_music_video_download = fake_add_music_video_download

        with _patch_get_db(session_factory):
            result = adapter.process_pending_downloads()

        assert result["processed_count"] == 1
        assert captured["artist"] == "Some Artist"
        assert isinstance(captured["artist"], str)


class TestSanitizeFolderNameFailureMode:
    """Documents the exact failure mode process_pending_downloads used to
    trigger, at the point where it actually broke — so a future caller that
    reintroduces "pass the ORM object, not .name" gets a clear, specific
    failure rather than a mysterious one three layers away.
    """

    def test_raises_attribute_error_on_a_non_string_object(self):
        artist = Artist(name="Some Artist")
        with pytest.raises(AttributeError, match="replace"):
            FilenameCleanup.sanitize_folder_name(artist)

    def test_accepts_the_real_string_the_fix_now_passes(self):
        assert FilenameCleanup.sanitize_folder_name("Some Artist") == "Some Artist"
