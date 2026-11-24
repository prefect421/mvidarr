"""The thumbnail route must not hold a pooled DB connection while it awaits a
download or streams a file (pool exhaustion froze the whole UI when a page
requested hundreds of thumbnails at once)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import src.api.fastapi.videos_thumbnails as mod


def _session(video):
    s = MagicMock()
    s.closed = False
    s.query.return_value.filter.return_value.first.return_value = video

    def _close():
        s.closed = True

    s.close.side_effect = _close
    return s


def _call(session):
    return asyncio.run(
        mod.get_video_thumbnail(
            video_id=1, size=None, session=session, current_user={"id": 1}
        )
    )


def test_session_closed_before_serving_cached_file(tmp_path):
    f = tmp_path / "t.jpg"
    f.write_bytes(b"x")
    video = SimpleNamespace(thumbnail_path=str(f), thumbnail_url=None, youtube_id=None)
    session = _session(video)
    resp = _call(session)
    assert str(resp.path) == str(f)
    assert session.closed


def test_session_closed_before_network_download(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.Config, "THUMBNAILS_DIR", tmp_path)
    video = SimpleNamespace(
        thumbnail_path=None, thumbnail_url="http://x/y.jpg", youtube_id=None
    )
    session = _session(video)
    seen = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, timeout=10):
            seen["closed_during_download"] = session.closed
            raise RuntimeError("offline")

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    try:
        _call(session)
    except Exception:
        pass
    assert seen.get("closed_during_download") is True
