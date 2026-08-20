"""Real behavioral tests for #383: queue_video_download() (POST
/{video_id}/download) and queue_download_video() (POST
/{video_id}/queue-download) must revert video.status -- and mark the
staged Download row failed -- on a falsy/{"success": False} dispatch
result from ytdlp_service.add_music_video_download(), not just on a
raised exception. bulk_download_videos() already got this exact fix
(#379.6); these two single-video siblings were explicitly left out of
that fix's scope.

Uses real SQLAlchemy models against an in-memory SQLite database
rather than static source-text assertions (see #384): importing
src.api.fastapi.videos_downloads succeeds fine in this test venv --
the RuntimeError("yt-dlp executable not found") only fires from
unified_download_service's real singleton construction, which is only
reached via the function-local `from
src.services.download_service_adapter import ytdlp_service` inside
these routes' dispatch try blocks. A sys.modules pre-registration of a
fake module bypasses that import entirely, so the route functions can
be called directly and their real behavior verified end to end.
"""

import asyncio
import sys
import types
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.fastapi.videos_downloads import (
    queue_download_video,
    queue_video_download,
)
from src.database.connection import Base
from src.database.models import Artist, Download, Video, VideoStatus


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Artist.__table__, Video.__table__, Download.__table__]
    )
    return sessionmaker(bind=engine)


def _seed_video(session_factory, status=VideoStatus.WANTED):
    session = session_factory()
    artist = Artist(name="Test Artist")
    session.add(artist)
    session.commit()

    video = Video(
        artist_id=artist.id,
        title="Test Song",
        status=status,
        url="https://youtube.com/watch?v=abc123",
        youtube_id="abc123",
    )
    session.add(video)
    session.commit()
    video_id = video.id
    session.close()
    return video_id


@contextmanager
def _dispatch_result(result, session_factory):
    """Shim src.services.download_service_adapter.ytdlp_service so the
    function-local import inside the route under test resolves to a
    fake whose add_music_video_download() returns `result` (or raises
    it, if it's an exception instance) instead of touching the real
    yt-dlp-backed singleton.

    Also fakes claim_video_for_redownload() -- in production it flips
    video.status to DOWNLOADING on its own, separate DB connection
    (see its docstring), so a bare `return_value=True` mock would never
    actually touch this test's SQLite-backed video row. Instead, the
    fake performs that same status flip for real, on a fresh session
    from the same in-memory engine -- a faithful, fast stand-in for the
    real separate-connection claim.
    """

    def _fake_add_music_video_download(**kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    def _fake_claim(video_id):
        claim_session = session_factory()
        try:
            video = claim_session.query(Video).filter(Video.id == video_id).first()
            if video is None or video.status == VideoStatus.DOWNLOADING:
                return False
            video.status = VideoStatus.DOWNLOADING
            claim_session.commit()
            return True
        finally:
            claim_session.close()

    fake_module = types.ModuleType("src.services.download_service_adapter")
    fake_module.ytdlp_service = types.SimpleNamespace(
        add_music_video_download=_fake_add_music_video_download
    )
    with patch.dict(
        sys.modules, {"src.services.download_service_adapter": fake_module}
    ):
        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim,
        ):
            yield


class TestQueueDownloadVideoRevertsOnFalsyResult:
    """POST /{video_id}/queue-download"""

    def test_reverts_video_status_and_marks_download_failed_on_falsy_result(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with _dispatch_result(
            {"success": False, "error": "yt-dlp exploded"}, session_factory
        ):
            result = asyncio.run(
                queue_download_video(
                    video_id=video_id,
                    current_user={"user_id": 1, "username": "test"},
                    session=session,
                )
            )

        assert result["success"] is False
        assert "yt-dlp exploded" in result["error"]

        session.expire_all()
        video = session.query(Video).filter(Video.id == video_id).first()
        assert video.status == VideoStatus.WANTED

        download = session.query(Download).filter(Download.video_id == video_id).first()
        assert download is not None
        assert download.status == "failed"
        assert download.error_message == "yt-dlp exploded"

    def test_succeeds_normally_on_a_truthy_result(self, session_factory):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with _dispatch_result({"success": True, "id": 999}, session_factory):
            result = asyncio.run(
                queue_download_video(
                    video_id=video_id,
                    current_user={"user_id": 1, "username": "test"},
                    session=session,
                )
            )

        assert result["success"] is True

        session.expire_all()
        video = session.query(Video).filter(Video.id == video_id).first()
        assert video.status == VideoStatus.DOWNLOADING

        download = session.query(Download).filter(Download.video_id == video_id).first()
        assert download is not None
        assert download.status == "queued"


class TestQueueVideoDownloadRevertsOnFalsyResult:
    """POST /{video_id}/download"""

    def test_reverts_video_status_and_marks_download_failed_on_falsy_result(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with _dispatch_result(
            {"success": False, "error": "yt-dlp exploded"}, session_factory
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(
                    queue_video_download(
                        video_id=video_id,
                        request={},
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert exc_info.value.status_code == 500
        assert "yt-dlp exploded" in exc_info.value.detail

        session.expire_all()
        video = session.query(Video).filter(Video.id == video_id).first()
        assert video.status == VideoStatus.WANTED

        download = session.query(Download).filter(Download.video_id == video_id).first()
        assert download is not None
        assert download.status == "failed"
        assert download.error_message == "yt-dlp exploded"

    def test_succeeds_normally_on_a_truthy_result(self, session_factory):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with _dispatch_result({"success": True, "id": 999}, session_factory):
            result = asyncio.run(
                queue_video_download(
                    video_id=video_id,
                    request={},
                    current_user={"user_id": 1, "username": "test"},
                    session=session,
                )
            )

        assert result["video_id"] == video_id

        session.expire_all()
        video = session.query(Video).filter(Video.id == video_id).first()
        assert video.status == VideoStatus.DOWNLOADING

        download = session.query(Download).filter(Download.video_id == video_id).first()
        assert download is not None
        assert download.status == "queued"
