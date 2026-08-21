"""Regression test for a live-reported bug: bulk_download_videos()
(POST /api/videos/bulk/download, the "Download Selected" button on the
artist page) never included a "success" key in its response, unlike
every other endpoint in this file. The frontend
(bulkDownloadSelected() in artist_detail.html) checks `if
(data.success)` to decide whether to show a success or error toast --
since that key was always undefined (falsy), it *always* took the
error branch and showed "Error: undefined", even when the batch
genuinely succeeded (live-reproduced 2026-08-21: 3 videos were queued
and actually downloaded, but the button still reported an error).

Fix: include "success": True on the endpoint's normal completion path,
matching every sibling endpoint in this file (queue_video_download,
queue_download_video, bulk_download_wanted_videos, etc. all already
do this).
"""

import ast
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.fastapi.videos_downloads import bulk_download_videos
from src.api.fastapi.videos_models import BulkDownloadRequest
from src.database.connection import Base
from src.database.models import Artist, Download, Video, VideoStatus

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_downloads.py"
)


def _function_source() -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "bulk_download_videos"
        ):
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError("Could not find bulk_download_videos in source")


class TestBulkDownloadVideosResponseHasSuccessKey:
    def test_final_result_dict_includes_a_success_key(self):
        source = _function_source()
        # "total_requested" only appears once, inside the final
        # response dict (not the per-video dispatch `result` variable
        # inside the loop, which is a different binding of the same
        # name) -- anchor on it and look back to that dict's opening
        # `result = {` for a "success" key.
        total_requested_pos = source.index('"total_requested"')
        dict_start = source.rindex("result = {", 0, total_requested_pos)
        block = source[dict_start:total_requested_pos]
        assert '"success"' in block


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
def _dispatch_success(session_factory):
    """Shim the ytdlp_service import and fake claim_video_for_redownload()
    to actually flip the video's status, mirroring
    test_single_video_download_reverts_on_falsy_result.py's approach."""

    def _fake_add_music_video_download(**kwargs):
        return {"success": True, "id": 999}

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


class TestBulkDownloadVideosBehavioralSuccessKey:
    def test_a_successful_batch_reports_success_true(self, session_factory):
        video_id = _seed_video(session_factory, status=VideoStatus.WANTED)
        session = session_factory()

        with _dispatch_success(session_factory):
            result = _run(
                bulk_download_videos(
                    request=BulkDownloadRequest(video_ids=[video_id]),
                    current_user={"user_id": 1, "username": "test"},
                    session=session,
                )
            )

        assert result["success"] is True
        assert result["queued_count"] == 1


def _run(coro):
    import asyncio

    return asyncio.run(coro)
