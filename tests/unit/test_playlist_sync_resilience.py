"""#630: videos.view_count must hold >2.1 billion, and one bad row must not
roll back an entire playlist sync."""

from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger

from src.database.connection import get_db
from src.database.models import Artist, PlaylistMonitor, Video
from src.services.youtube_playlist_service import YouTubePlaylistService


def test_count_columns_are_bigint():
    assert isinstance(Video.__table__.c.view_count.type, BigInteger)
    assert isinstance(Video.__table__.c.like_count.type, BigInteger)


def test_migration_026_widens_columns_idempotently():
    import importlib.util
    import pathlib
    from unittest.mock import MagicMock

    path = pathlib.Path("migrations/026_widen_video_count_columns.py")
    spec = importlib.util.spec_from_file_location("m026", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def run(types):
        conn = MagicMock()
        conn.execute.side_effect = lambda stmt, *a, **k: MagicMock(
            fetchall=lambda: [(c, t) for c, t in types.items()]
        )
        m.upgrade(conn)
        return [str(c.args[0]) for c in conn.execute.call_args_list]

    already = run({"view_count": "bigint", "like_count": "bigint"})
    assert not any("ALTER TABLE" in s for s in already)
    needs = run({"view_count": "int", "like_count": "int"})
    assert any("MODIFY view_count BIGINT" in s for s in needs)
    assert any("MODIFY like_count BIGINT" in s for s in needs)


@pytest.fixture
def playlist():
    with get_db() as s:
        a = Artist(name="Chan")
        s.add(a)
        s.add(
            PlaylistMonitor(
                playlist_id="PLTEST",
                playlist_url="u",
                name="n",
                auto_download=False,
                keywords=None,
            )
        )
        s.commit()
        aid = a.id
    yield
    with get_db() as s:
        s.query(Video).filter(Video.artist_id == aid).delete()
        s.query(PlaylistMonitor).delete()
        s.query(Artist).filter(Artist.id == aid).delete()
        s.commit()


def _pv(vid):
    return {
        "video_id": vid,
        "title": f"t {vid}",
        "channel_title": "Chan",
        "position": 0,
    }


def test_one_bad_row_does_not_discard_the_rest_of_the_sync(playlist):
    svc = YouTubePlaylistService.__new__(YouTubePlaylistService)
    # the same new id twice -> the second insert violates the unique constraint
    vids = [
        _pv("AAAAAAAAAAA"),
        _pv("BBBBBBBBBBB"),
        _pv("BBBBBBBBBBB"),
        _pv("CCCCCCCCCCC"),
    ]
    with patch.object(svc, "get_playlist_videos", return_value=vids), patch.object(
        svc, "get_video_details", return_value={}
    ):
        with get_db() as s:
            res = svc.sync_playlist_videos("PLTEST", s)

    with get_db() as s:
        stored = {
            v.youtube_id
            for v in s.query(Video).filter(
                Video.youtube_id.like("%AAAA%")
                | Video.youtube_id.like("%BBBB%")
                | Video.youtube_id.like("%CCCC%")
            )
        }
    assert stored == {"AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"}
    assert res["new_videos"] == 3  # the failed duplicate is not counted
    assert len(res["errors"]) == 1
