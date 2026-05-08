"""Tests for quota-gated YouTube search service"""

import tempfile
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.services.youtube_search_service import YouTubeSearchService
from src.utils.youtube_quota_tracker import YouTubeQuotaTracker


def _make_service_with_tracker(tmp_path):
    """Return a YouTubeSearchService wired to an isolated quota tracker and no-op cache."""
    storage = str(tmp_path / "quota.json")
    tracker = YouTubeQuotaTracker(storage_path=storage)
    service = YouTubeSearchService()
    service._quota_tracker = tracker
    # Isolate cache so results don't leak between tests
    service._cache = MagicMock()
    service._cache.get.return_value = None
    return service, tracker


def _fake_search_response(n=3):
    """Minimal YouTube search API response."""
    items = [
        {
            "id": {"videoId": f"vid{i}"},
            "snippet": {
                "title": f"Video {i}",
                "description": "",
                "channelTitle": "Artist",
                "channelId": "chan1",
                "publishedAt": "2024-01-01T00:00:00Z",
                "thumbnails": {},
            },
        }
        for i in range(n)
    ]
    return {"items": items, "pageInfo": {"totalResults": n}}


@patch("src.services.youtube_search_service.requests.get")
def test_search_makes_at_most_two_api_calls(mock_get, tmp_path):
    service, _ = _make_service_with_tracker(tmp_path)
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: _fake_search_response(),
        raise_for_status=lambda: None,
    )
    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        service.search_artist_videos("Test Artist", limit=50)

    # Should be 2 search calls + up to 2 video-details calls (batched)
    search_calls = [c for c in mock_get.call_args_list if "/search" in str(c)]
    assert len(search_calls) <= 2


@patch("src.services.youtube_search_service.requests.get")
def test_search_skips_second_call_when_quota_exhausted(mock_get, tmp_path):
    service, tracker = _make_service_with_tracker(tmp_path)
    # Exhaust quota — only 100 units left (not enough for a second search)
    for _ in range(99):
        tracker.consume("search")

    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: _fake_search_response(),
        raise_for_status=lambda: None,
    )
    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        result = service.search_artist_videos("Test Artist", limit=50)

    search_calls = [c for c in mock_get.call_args_list if "/search" in str(c)]
    # First call (100 units) succeeds, second (100 units) would hit limit
    assert len(search_calls) <= 1
    # Result should still be returned, not an error
    assert "videos" in result


@patch("src.services.youtube_search_service.requests.get")
def test_search_returns_error_dict_when_fully_exhausted(mock_get, tmp_path):
    service, tracker = _make_service_with_tracker(tmp_path)
    # Fully exhaust quota
    for _ in range(100):
        tracker.consume("search")

    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        result = service.search_artist_videos("Test Artist", limit=50)

    mock_get.assert_not_called()
    assert result["videos"] == []
    assert "quota" in result.get("error", "").lower()
