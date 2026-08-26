"""Real behavioral tests for #384: bulk_download_videos(), queue_video_
download(), and queue_download_video()'s claim/dispatch/revert logic was
covered only by static source-assertion tests (ast-extracted function
text, grepped for expected strings/patterns) across 5 files (~35 tests) --
proving "the right strings appear in the right order," not that the
actual dispatch/revert behavior works. #384 found the premise for that
style ("videos_downloads.py can't be imported directly") was false or at
least narrower than assumed: the module imports fine; only the function-
local `from src.services.download_service_adapter import ytdlp_service`
at call time needs a sys.modules shim, proven by
test_bulk_download_response_includes_success_key.py's real, SQLite-backed
behavioral test for bulk_download_videos()'s success path. This file
extends that same technique to the properties the old static-assertion
files were checking indirectly: claim-before-dispatch ordering, revert-
to-real-original-status (not a hardcoded WANTED) on dispatch failure, and
distinguishing a genuine claim race-loss from an unrelated claim error.

Not a mechanical 1:1 port of all ~35 old assertions -- this covers the
behavioral properties that actually matter (and that a source-assertion
test can only gesture at), using real execution against an in-memory
SQLite session and a shimmed ytdlp_service, for all 3 functions #384
names. The now-redundant static-assertion files are removed in the same
change (see the accompanying commit message for the full list).
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
from sqlalchemy.pool import StaticPool

from src.api.fastapi.videos_downloads import (
    bulk_download_videos,
    queue_download_video,
    queue_video_download,
)
from src.api.fastapi.videos_models import BulkDownloadRequest
from src.database.connection import Base
from src.database.models import Artist, Download, Video, VideoStatus


@pytest.fixture
def session_factory():
    # #457: claim_video_for_redownload()/claim_video_for_download() now
    # run via asyncio.to_thread() -- a real, different OS thread. Plain
    # `sqlite:///:memory:` uses SQLAlchemy's SingletonThreadPool, which
    # hands a *different*, empty in-memory database to any thread other
    # than the one that created the engine. StaticPool forces every
    # connection (any thread) to share the single underlying DBAPI
    # connection, and check_same_thread=False lifts SQLite's own same-
    # thread guard (safe here: this fixture's usage is never truly
    # concurrent, just cross-thread).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _set_status_via_fresh_session(session_factory, video_id, status):
    """Simulate a concurrent request having already changed the video's
    status, independently of the session the route under test will use."""
    session = session_factory()
    video = session.query(Video).filter(Video.id == video_id).first()
    video.status = status
    session.commit()
    session.close()


def _fake_claim_always_fails(video_id):
    return False


def _fake_claim_succeeds(session_factory):
    """Mirrors the real claim_video_for_redownload(): commits
    status=DOWNLOADING on its own, separate connection."""

    def _claim(video_id):
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

    return _claim


@contextmanager
def _shim_ytdlp_dispatch(result=None, side_effect=None):
    """Shim download_service_adapter.ytdlp_service so dispatch never
    touches the real yt-dlp executable check. Records whether it was
    called, for claim-before-dispatch ordering assertions."""
    calls = []

    def _fake_add_music_video_download(**kwargs):
        calls.append(kwargs)
        if side_effect is not None:
            raise side_effect
        return result

    fake_module = types.ModuleType("src.services.download_service_adapter")
    fake_module.ytdlp_service = types.SimpleNamespace(
        add_music_video_download=_fake_add_music_video_download
    )
    with patch.dict(
        sys.modules, {"src.services.download_service_adapter": fake_module}
    ):
        yield calls


def _run(coro):
    return asyncio.run(coro)


class TestBulkDownloadVideosClaimBeforeDispatch:
    def test_claim_failure_skips_without_ever_dispatching(self, session_factory):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_always_fails,
        ):
            with _shim_ytdlp_dispatch(result={"success": True}) as calls:
                result = _run(
                    bulk_download_videos(
                        request=BulkDownloadRequest(video_ids=[video_id]),
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert calls == []  # dispatch never reached
        assert result["skipped_count"] == 1
        assert result["queued_count"] == 0

    def test_dispatch_falsy_result_reverts_to_real_original_status(
        self, session_factory
    ):
        # FAILED, not the default WANTED -- proves the revert restores
        # the video's actual pre-claim status rather than a hardcoded
        # WANTED (claim_video_for_redownload() can claim from FAILED,
        # MONITORED, or DOWNLOADED too).
        video_id = _seed_video(session_factory, status=VideoStatus.FAILED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_succeeds(session_factory),
        ):
            with _shim_ytdlp_dispatch(
                result={"success": False, "error": "yt-dlp exploded"}
            ):
                result = _run(
                    bulk_download_videos(
                        request=BulkDownloadRequest(video_ids=[video_id]),
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert result["failed_count"] == 1
        assert result["queued_count"] == 0

        verify_session = session_factory()
        reverted_video = (
            verify_session.query(Video).filter(Video.id == video_id).first()
        )
        assert reverted_video.status == VideoStatus.FAILED
        download = (
            verify_session.query(Download).filter(Download.video_id == video_id).first()
        )
        assert download.status == "failed"

    def test_successful_dispatch_queues_the_video(self, session_factory):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_succeeds(session_factory),
        ):
            with _shim_ytdlp_dispatch(result={"success": True, "id": "job-1"}):
                result = _run(
                    bulk_download_videos(
                        request=BulkDownloadRequest(video_ids=[video_id]),
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert result["queued_count"] == 1
        assert result["failed_count"] == 0


class TestQueueVideoDownloadClaimBeforeDispatch:
    def test_claim_failure_with_downloading_status_reports_already_downloading(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        # Simulate a concurrent request having already won the claim.
        _set_status_via_fresh_session(
            session_factory, video_id, VideoStatus.DOWNLOADING
        )
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_always_fails,
        ):
            with _shim_ytdlp_dispatch(result={"success": True}) as calls:
                result = _run(
                    queue_video_download(
                        video_id=video_id,
                        request={},
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert calls == []  # dispatch never reached
        assert result["message"] == "Video is currently downloading"
        assert result["download_id"] is None
        # No Download row should exist -- staging only happens after a
        # successful claim.
        verify_session = session_factory()
        assert (
            verify_session.query(Download).filter(Download.video_id == video_id).first()
            is None
        )

    def test_claim_failure_with_non_downloading_status_reports_a_real_error(
        self, session_factory
    ):
        # Status stays WANTED -- not a genuine race loss, so the claim
        # failure must be reported as a real, retriable error, not
        # misleadingly described as "already downloading."
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_always_fails,
        ):
            with _shim_ytdlp_dispatch(result={"success": True}) as calls:
                result = _run(
                    queue_video_download(
                        video_id=video_id,
                        request={},
                        current_user={"user_id": 1, "username": "test"},
                        session=session,
                    )
                )

        assert calls == []
        assert result["success"] is False
        assert "claim" in result["error"].lower()

    def test_dispatch_falsy_result_reverts_status_and_marks_download_failed(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.MONITORED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_succeeds(session_factory),
        ):
            with _shim_ytdlp_dispatch(
                result={"success": False, "error": "no space left on device"}
            ):
                with pytest.raises(HTTPException) as exc_info:
                    _run(
                        queue_video_download(
                            video_id=video_id,
                            request={},
                            current_user={"user_id": 1, "username": "test"},
                            session=session,
                        )
                    )

        assert exc_info.value.status_code == 500

        verify_session = session_factory()
        reverted_video = (
            verify_session.query(Video).filter(Video.id == video_id).first()
        )
        assert reverted_video.status == VideoStatus.MONITORED
        download = (
            verify_session.query(Download).filter(Download.video_id == video_id).first()
        )
        assert download.status == "failed"
        assert "no space left" in download.error_message


class TestQueueDownloadVideoClaimBeforeDispatch:
    def test_claim_failure_with_downloading_status_reports_already_downloading(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        _set_status_via_fresh_session(
            session_factory, video_id, VideoStatus.DOWNLOADING
        )
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_always_fails,
        ):
            with _shim_ytdlp_dispatch(result={"success": True}) as calls:
                result = _run(queue_download_video(video_id=video_id, session=session))

        assert calls == []
        assert result["success"] is True
        assert result["status"] == "already_downloading"

    def test_claim_failure_with_non_downloading_status_reports_a_real_error(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_always_fails,
        ):
            with _shim_ytdlp_dispatch(result={"success": True}) as calls:
                result = _run(queue_download_video(video_id=video_id, session=session))

        assert calls == []
        assert result["success"] is False
        assert "claim" in result["error"].lower()

    def test_dispatch_falsy_result_reverts_status_and_returns_error_dict(
        self, session_factory
    ):
        video_id = _seed_video(session_factory, status=VideoStatus.FAILED)
        session = session_factory()

        with patch(
            "src.services.video_batch_service.claim_video_for_redownload",
            side_effect=_fake_claim_succeeds(session_factory),
        ):
            with _shim_ytdlp_dispatch(result={"success": False, "error": "disk full"}):
                result = _run(queue_download_video(video_id=video_id, session=session))

        assert result["success"] is False

        verify_session = session_factory()
        reverted_video = (
            verify_session.query(Video).filter(Video.id == video_id).first()
        )
        assert reverted_video.status == VideoStatus.FAILED
        download = (
            verify_session.query(Download).filter(Download.video_id == video_id).first()
        )
        assert download.status == "failed"
