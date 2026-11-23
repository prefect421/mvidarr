"""#616: discovery must record last_discovery on every path, the bulk loop must
survive nested sessions, and each artist's own max_videos_per_discovery applies."""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services import video_discovery_service as vds


def _artist(id_, name, max_videos=None, last=None):
    return SimpleNamespace(
        id=id_,
        name=name,
        monitored=True,
        discovery_enabled=True,
        discovery_interval_hours=24,
        last_discovery=last,
        max_videos_per_discovery=max_videos,
    )


def _db_for(artists_by_id):
    """get_db() factory: each call yields a fresh session over the same artists."""

    @contextmanager
    def fake_get_db():
        session = MagicMock()

        def query(model):
            q = MagicMock()
            if model is vds.Artist:
                q.filter_by.side_effect = lambda **kw: MagicMock(
                    first=lambda: artists_by_id.get(kw.get("id")),
                    all=lambda: list(artists_by_id.values()),
                )
            else:
                q.filter_by.return_value.all.return_value = []
            return q

        session.query.side_effect = query
        yield session

    return fake_get_db


def _service():
    svc = vds.VideoDiscoveryService.__new__(vds.VideoDiscoveryService)
    svc.rate_limit_delay = 0
    svc.discovery_interval_hours = 24
    return svc


def test_per_artist_path_records_last_discovery():
    a = _artist(3, "Maphra")
    svc = _service()
    with patch.object(vds, "get_db", _db_for({3: a})), patch.object(
        svc, "_search_youtube_for_artist", return_value=[]
    ):
        res = svc.discover_videos_for_artist(3)
    assert res["success"] is True
    assert isinstance(a.last_discovery, datetime)


def test_failed_search_exception_does_not_record_last_discovery():
    a = _artist(3, "Maphra")
    svc = _service()
    with patch.object(vds, "get_db", _db_for({3: a})), patch.object(
        svc, "_search_youtube_for_artist", side_effect=RuntimeError("boom")
    ):
        res = svc.discover_videos_for_artist(3)
    assert res["success"] is False
    assert a.last_discovery is None


def test_bulk_path_processes_every_artist_and_uses_artist_limit():
    artists = {
        1: _artist(1, "A", max_videos=50),
        2: _artist(2, "B", max_videos=None),
        3: _artist(3, "C", max_videos=7),
    }
    svc = _service()
    seen = []

    def fake_discover(artist_id, limit=None):
        seen.append((artist_id, limit))
        return {"success": True, "discovered_count": 0, "stored_count": 0}

    with patch.object(vds, "get_db", _db_for(artists)), patch.object(
        svc, "discover_videos_for_artist", side_effect=fake_discover
    ), patch.object(vds.time, "sleep"):
        res = svc.discover_videos_for_all_artists(limit_per_artist=5)

    assert res["success"] is True
    # all three processed; own limit wins, global (5) only where unset
    assert seen == [(1, 50), (2, 5), (3, 7)]


def test_bulk_path_skips_recently_discovered_artist():
    artists = {
        1: _artist(1, "A", last=datetime.utcnow()),
        2: _artist(2, "B"),
    }
    svc = _service()
    with patch.object(vds, "get_db", _db_for(artists)), patch.object(
        svc,
        "discover_videos_for_artist",
        return_value={"success": True, "discovered_count": 0, "stored_count": 0},
    ) as d, patch.object(vds.time, "sleep"):
        svc.discover_videos_for_all_artists(limit_per_artist=5)
    assert [c.args[0] for c in d.call_args_list] == [2]
