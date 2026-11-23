"""#628: MvTV filters. Genre options came from a key the API never returns, the
artist filter sent a name the API ignores (and limit=1000 -> 422), and the
quality filter was not implemented by the API at all."""

import asyncio
import re

import pytest

from src.api.fastapi.videos_search import quality_labels_at_least, search_videos
from src.database.connection import get_db
from src.database.models import Artist, Video


def test_quality_ladder_expansion():
    assert quality_labels_at_least("1080p") >= {"1080p", "1440p", "2160p", "4K"}
    assert "720p" not in quality_labels_at_least("1080p")
    assert "720p" in quality_labels_at_least("720p")
    assert (
        quality_labels_at_least("") == set()
        and quality_labels_at_least("junk") == set()
    )


@pytest.fixture
def lib():
    with get_db() as s:
        a = Artist(name="MvTV A")
        b = Artist(name="MvTV B")
        s.add_all([a, b])
        s.commit()
        vids = [
            Video(
                artist_id=a.id,
                title="a360",
                youtube_id="mvtvvid0001",
                url="u",
                quality="360p",
            ),
            Video(
                artist_id=a.id,
                title="a1080",
                youtube_id="mvtvvid0002",
                url="u",
                quality="1080p",
            ),
            Video(
                artist_id=b.id,
                title="b4k",
                youtube_id="mvtvvid0003",
                url="u",
                quality="4K",
            ),
        ]
        s.add_all(vids)
        s.commit()
        ids = (a.id, b.id, [v.id for v in vids])
    yield ids
    with get_db() as s:
        s.query(Video).filter(Video.id.in_(ids[2])).delete(synchronize_session=False)
        s.query(Artist).filter(Artist.id.in_([ids[0], ids[1]])).delete(
            synchronize_session=False
        )
        s.commit()


def _search(**kw):
    args = dict(
        query=None,
        artist_id=None,
        status=None,
        year=None,
        genre=None,
        quality=None,
        limit=50,
        offset=0,
        sort_by="created_at",
        sort_order="desc",
        current_user={"user_id": 1},
    )
    args.update(kw)
    with get_db() as s:
        res = asyncio.run(search_videos(session=s, **args))
    return {v["title"] for v in res["videos"]}


def test_quality_filter_means_at_least_that_resolution(lib):
    a, b, _ = lib
    assert _search(artist_id=a, quality="1080p") == {"a1080"}
    assert _search(quality="1080p") >= {"a1080", "b4k"}
    assert "a360" not in _search(quality="720p")


def test_artist_and_quality_combine(lib):
    a, b, _ = lib
    assert _search(artist_id=b, quality="1080p") == {"b4k"}
    assert _search(artist_id=a) == {"a360", "a1080"}


MVTV = open("frontend/templates/mvtv.html", encoding="utf-8").read()


def test_genre_options_use_the_key_the_api_returns():
    assert "genresData.genres" in MVTV


def test_filtered_loads_respect_the_api_limit_cap():
    assert "limit', '1000'" not in MVTV  # the API caps limit at 500 (422 above it)


def test_artist_filter_sends_an_id_not_a_name():
    assert "params.set('artist_id'" in MVTV
    assert "params.set('artist'," not in MVTV


def test_a_failed_request_is_an_error_not_an_empty_library():
    assert re.search(r"response\.ok", MVTV)
