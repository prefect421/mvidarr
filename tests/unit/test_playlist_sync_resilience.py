"""#630: videos.view_count must hold >2.1 billion, and one bad row must not
roll back an entire playlist sync."""

from unittest.mock import MagicMock, patch

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


# --- #632: playlist "Auto-download" uses MVidarr's own downloader, not MeTube ---


@pytest.fixture
def auto_playlist():
    with get_db() as s:
        a = Artist(name="Chan")
        s.add(a)
        s.add(
            PlaylistMonitor(
                playlist_id="PLAUTO",
                playlist_url="u",
                name="n",
                auto_download=True,
                quality="720p",
                keywords=None,
            )
        )
        s.commit()
        aid = a.id
    yield aid
    with get_db() as s:
        s.query(Video).filter(Video.artist_id == aid).delete()
        s.query(PlaylistMonitor).delete()
        s.query(Artist).filter(Artist.id == aid).delete()
        s.commit()


def _sync(svc, vids, dispatch_result, claim=True):
    from src.services import video_batch_service

    adapter = MagicMock()
    adapter.add_music_video_download.return_value = dispatch_result
    from src.services import download_service_adapter

    with patch.object(svc, "get_playlist_videos", return_value=vids), patch.object(
        svc, "get_video_details", return_value={}
    ), patch.object(
        video_batch_service, "claim_video_for_download", return_value=claim
    ) as claim_mock, patch.object(
        download_service_adapter, "ytdlp_service", adapter
    ), patch(
        "src.services.settings_service.settings.get_bool", return_value=False
    ), patch(
        "src.services.settings_service.settings.get", return_value="en"
    ):
        with get_db() as s:
            res = svc.sync_playlist_videos("PLAUTO", s)
    return res, adapter, claim_mock


def test_auto_download_dispatches_through_the_real_downloader(auto_playlist):
    svc = YouTubePlaylistService.__new__(YouTubePlaylistService)
    res, adapter, claim = _sync(svc, [_pv("DDDDDDDDDDD")], {"success": True, "id": 7})
    kw = adapter.add_music_video_download.call_args.kwargs
    assert kw["quality"] == "720p"  # the monitor's quality is finally used
    assert kw["url"] == "https://www.youtube.com/watch?v=DDDDDDDDDDD"
    assert kw["artist"] == "Chan" and kw["video_id"]
    claim.assert_called_once()
    assert res["downloaded_videos"] == 1 and res["errors"] == []
    with get_db() as s:
        v = s.query(Video).filter(Video.youtube_id == "DDDDDDDDDDD").one()
        assert v.url == "https://www.youtube.com/watch?v=DDDDDDDDDDD"  # was NULL


def test_failed_dispatch_reverts_the_video_to_wanted(auto_playlist):
    from src.database.models import VideoStatus

    svc = YouTubePlaylistService.__new__(YouTubePlaylistService)
    res, adapter, _ = _sync(
        svc, [_pv("EEEEEEEEEEE")], {"success": False, "error": "no"}
    )
    assert res["downloaded_videos"] == 0 and len(res["errors"]) == 1
    with get_db() as s:
        v = s.query(Video).filter(Video.youtube_id == "EEEEEEEEEEE").one()
        assert v.status == VideoStatus.WANTED


def test_already_claimed_video_is_skipped_quietly(auto_playlist):
    svc = YouTubePlaylistService.__new__(YouTubePlaylistService)
    res, adapter, _ = _sync(svc, [_pv("FFFFFFFFFFF")], {"success": True}, claim=False)
    adapter.add_music_video_download.assert_not_called()
    assert res["downloaded_videos"] == 0 and res["errors"] == []


def test_no_metube_dependency_remains():
    assert not hasattr(YouTubePlaylistService, "download_video")
