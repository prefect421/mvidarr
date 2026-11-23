"""#613: imported YouTube videos must get a YouTube thumbnail straight away."""

import asyncio

import pytest

from src.api.fastapi.videos_import import import_from_youtube
from src.database.connection import get_db
from src.database.models import Artist, Video


@pytest.fixture
def artist_id():
    with get_db() as session:
        a = Artist(name="Thumb Import Artist")
        session.add(a)
        session.commit()
        aid = a.id
    yield aid
    with get_db() as session:
        session.query(Video).filter(Video.artist_id == aid).delete()
        session.query(Artist).filter(Artist.id == aid).delete()
        session.commit()


def test_import_sets_youtube_thumbnail(artist_id):
    with get_db() as session:
        asyncio.run(
            import_from_youtube(
                request={
                    "youtube_id": "thumbvid01",
                    "title": "Song",
                    "artist_id": artist_id,
                    "auto_download": False,
                },
                current_user={"user_id": 1},
                session=session,
            )
        )
    with get_db() as session:
        v = session.query(Video).filter(Video.youtube_id == "thumbvid01").one()
        assert v.thumbnail_url == "https://img.youtube.com/vi/thumbvid01/hqdefault.jpg"
        assert v.thumbnail_source == "youtube"


def test_refresh_thumbnails_prefers_youtube_url_over_ffmpeg(artist_id):
    from unittest.mock import patch

    from src.api.fastapi.videos_bulk import refresh_video_thumbnails

    with get_db() as session:
        v = Video(
            artist_id=artist_id,
            title="Imported earlier",
            youtube_id="refreshvid1",
            url="https://youtube.com/watch?v=refreshvid1",
            local_path="/nonexistent/file.webm",
        )
        session.add(v)
        session.commit()
        vid = v.id

    with get_db() as session, patch(
        "src.jobs.metadata_tasks.submit_bulk_thumbnail_url_download_task",
        return_value="job-1",
    ) as submit:
        res = asyncio.run(
            refresh_video_thumbnails(
                body={"video_ids": [vid]},
                current_user={"user_id": 1},
                session=session,
            )
        )

    assert res["url_videos"] == 1 and res["ffmpeg_videos"] == 0
    assert submit.call_args.kwargs["url_video_ids"] == [vid]
    with get_db() as session:
        v = session.get(Video, vid)
        assert v.thumbnail_url == "https://img.youtube.com/vi/refreshvid1/hqdefault.jpg"
