"""Defense-in-depth fix for #444: get_download_queue()'s DB-backed filter
only recognized "queued"/"downloading" status, not "pending" -- the
Download model's own default status. A download genuinely left at
"pending" for any reason (not just the retry_download() bug this report
was root-caused to -- see test_retry_download_redispatches.py) was
invisible here, and also invisible in get_download_history()'s
completed/failed/cancelled filter, with no indication anything was ever
attempted. Now included alongside "queued"/"downloading".

Uses conftest.py's _wire_real_sqlite_db fixture (real SQLite behind
get_db(), the same real, unpatched database access this endpoint and
unified_download_service.get_download_queue() both use).
"""

import asyncio

import pytest

from src.api.fastapi.metube import get_download_queue
from src.database.connection import get_db
from src.database.models import Artist, Download, Video, VideoStatus


@pytest.fixture
def seeded_pending_download():
    with get_db() as session:
        artist = Artist(name="Test Artist")
        session.add(artist)
        session.flush()

        video = Video(
            artist_id=artist.id,
            title="Test Song",
            status=VideoStatus.WANTED,
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
            status="pending",
        )
        session.add(download)
        session.flush()
        download_id = download.id

    return download_id


def _run(coro):
    return asyncio.run(coro)


class TestDownloadQueueIncludesPendingDownloads:
    def test_a_pending_download_appears_in_the_queue(self, seeded_pending_download):
        download_id = seeded_pending_download

        with get_db() as session:
            result = _run(
                get_download_queue(
                    current_user={"user_id": 1, "username": "test"},
                    session=session,
                )
            )

        db_download_ids = {
            item.get("db_download_id")
            for item in result.queue
            if item.get("db_download_id") is not None
        }
        assert download_id in db_download_ids
