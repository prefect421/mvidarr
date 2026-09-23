"""Live-reported (2026-09-23): the search_results.html page shows "no
results" for YouTube even when a valid API key is configured. Root cause:
three frontend files (search_results.html, discover.html,
add_video_modal.html) all independently call POST /api/youtube/search and
parse its response as the raw YouTube Data API v3 shape --
`items[].id.videoId`, `items[].snippet.{title,channelTitle,publishedAt,
thumbnails}` -- but the route (week29_integration.py's
search_youtube_videos) returns a differently-shaped, custom-flattened body
under a "results" key instead, and even that flattened body reads the
wrong source field ("id" instead of "youtube_id" on the video dicts
youtube_search_service.search_artist_videos() actually returns), so
videoId was always None regardless.

Fix: return the shape every existing frontend consumer already expects,
built from the correct source field names.
"""

import sys
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# week29_integration.py transitively imports src.services.local_network_share,
# which does a module-level `import netifaces`, not installed in the test
# venv. Shim it out before importing, same as test_week29_integration_auth.py.
sys.modules.setdefault("netifaces", MagicMock())

from src.api.fastapi.auth_dependencies import require_admin
from src.api.fastapi.week29_integration import youtube_router


class TestYoutubeSearchRouteResponseShape:
    def _client(self):
        app = FastAPI()
        app.include_router(youtube_router, prefix="/api")
        app.dependency_overrides[require_admin] = lambda: {
            "authenticated": True,
            "role": "admin",
            "user_id": 1,
        }
        return TestClient(app)

    def test_returns_items_wrapper_with_raw_api_shaped_video_entries(self):
        fake_service = MagicMock()
        fake_service.api_key = "fake-key"
        fake_service.search_artist_videos.return_value = {
            "videos": [
                {
                    "youtube_id": "abc123",
                    "title": "Rats",
                    "channel_title": "GhostVEVO",
                    "published_at": "2018-05-31T00:00:00Z",
                    "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
                }
            ],
            "total_results": 1,
        }

        with patch(
            "src.services.youtube_search_service.youtube_search_service",
            fake_service,
        ):
            response = self._client().post(
                "/api/youtube/search", json={"q": "ghost rats", "maxResults": 10}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "items" in data

        item = data["items"][0]
        assert item["id"]["videoId"] == "abc123"
        assert item["snippet"]["title"] == "Rats"
        assert item["snippet"]["channelTitle"] == "GhostVEVO"
        assert item["snippet"]["publishedAt"] == "2018-05-31T00:00:00Z"
        assert (
            item["snippet"]["thumbnails"]["default"]["url"]
            == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
        )
        assert (
            item["snippet"]["thumbnails"]["medium"]["url"]
            == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
        )

    def test_returns_success_false_with_empty_items_when_api_key_missing(self):
        fake_service = MagicMock()
        fake_service.api_key = None

        with patch(
            "src.services.youtube_search_service.youtube_search_service",
            fake_service,
        ):
            response = self._client().post(
                "/api/youtube/search", json={"q": "ghost rats"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["items"] == []
