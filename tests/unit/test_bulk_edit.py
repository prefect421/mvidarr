"""#636: Videos-page bulk edit. The page crashed on controls that do not exist and
sent a request shape the API silently ignored (reporting success for 0 videos)."""

import asyncio
import re

import pytest

from src.api.fastapi.videos_bulk import bulk_edit_videos
from src.api.fastapi.videos_models import BulkEditRequest
from src.database.connection import get_db
from src.database.models import Artist, Video


@pytest.fixture
def library():
    with get_db() as s:
        old = Artist(name="Old Artist")
        s.add(old)
        s.commit()
        ids = []
        for i in range(2):
            v = Video(
                artist_id=old.id, title=f"t{i}", youtube_id=f"bulkvid000{i}", url="u"
            )
            s.add(v)
            s.commit()
            ids.append(v.id)
        oid = old.id
    yield oid, ids
    with get_db() as s:
        s.query(Video).filter(Video.id.in_(ids)).delete(synchronize_session=False)
        s.query(Artist).filter(
            Artist.name.in_(["Old Artist", "Brand New Artist", "Existing Target"])
        ).delete(synchronize_session=False)
        s.commit()


def _bulk(**fields):
    with get_db() as s:
        return asyncio.run(
            bulk_edit_videos(
                request=BulkEditRequest(**fields),
                current_user={"user_id": 1},
                session=s,
            )
        )


def test_artist_name_creates_or_finds_one_artist_for_every_video(library):
    _, ids = library
    res = _bulk(video_ids=ids, artist_name="Brand New Artist", year=1999)
    assert res["updated_count"] == 2
    with get_db() as s:
        videos = s.query(Video).filter(Video.id.in_(ids)).all()
        artists = {v.artist_id for v in videos}
        assert len(artists) == 1  # one artist, not one per video
        assert s.get(Artist, artists.pop()).name == "Brand New Artist"
        assert {v.year for v in videos} == {1999}


def test_existing_artist_is_reused_not_duplicated(library):
    _, ids = library
    with get_db() as s:
        s.add(Artist(name="Existing Target"))
        s.commit()
    _bulk(video_ids=ids, artist_name="Existing Target")
    with get_db() as s:
        assert s.query(Artist).filter(Artist.name == "Existing Target").count() == 1


def test_applybulkedit_only_references_controls_that_exist():
    html = open("frontend/templates/videos.html", encoding="utf-8").read()
    start = html.index("function applyBulkEdit(")
    body = html[start : html.index("\n}\n", start)]
    referenced = set(re.findall(r"getElementById\('(bulk\w+)'\)", body))
    missing = [i for i in referenced if f'id="{i}"' not in html]
    assert missing == [], f"applyBulkEdit reads controls that do not exist: {missing}"


def test_applybulkedit_sends_fields_at_the_top_level_the_api_expects():
    html = open("frontend/templates/videos.html", encoding="utf-8").read()
    start = html.index("function applyBulkEdit(")
    body = html[start : html.index("\n}\n", start)]
    assert "updates: updates" not in body  # the API has no `updates` wrapper
    assert "updated_count" in body and "=== 0" in body  # 0 videos is not 'success'
