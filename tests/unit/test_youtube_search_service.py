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


class TestSearchVideosAsTyped:
    """#545: universal search must query YouTube with exactly what the user
    typed -- no appended terms, no category filter, no re-ranking."""

    @staticmethod
    def _run(mock_get, tmp_path, query, items):
        service, _ = _make_service_with_tracker(tmp_path)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"items": items, "pageInfo": {"totalResults": len(items)}},
            raise_for_status=lambda: None,
        )
        with patch.object(
            YouTubeSearchService,
            "api_key",
            new_callable=PropertyMock,
            return_value="fakekey",
        ):
            result = service.search_videos_as_typed(query, limit=5)
        return result

    @staticmethod
    def _item(vid, title):
        return {
            "id": {"videoId": vid},
            "snippet": {
                "title": title,
                "description": "",
                "channelTitle": "Chan",
                "channelId": "c1",
                "publishedAt": "2024-01-01T00:00:00Z",
                "thumbnails": {},
            },
        }

    @patch("src.services.youtube_search_service.requests.get")
    def test_single_search_call_with_exact_query_and_no_category(
        self, mock_get, tmp_path
    ):
        self._run(mock_get, tmp_path, "AC/DC Back In Black", [self._item("v1", "x")])

        search_calls = [c for c in mock_get.call_args_list if "/search" in str(c)]
        assert len(search_calls) == 1
        params = search_calls[0].kwargs["params"]
        assert params["q"] == "AC/DC Back In Black"
        assert "videoCategoryId" not in params

    @patch("src.services.youtube_search_service.requests.get")
    def test_keeps_youtube_relevance_order(self, mock_get, tmp_path):
        # Titles that an artist-name heuristic would re-rank ("official video"
        # bonus) must stay in the order YouTube returned them.
        items = [
            self._item("first", "Plain upload"),
            self._item("second", "Some Band - Official Music Video"),
        ]
        result = self._run(mock_get, tmp_path, "some band", items)

        assert [v["youtube_id"] for v in result["videos"]] == ["first", "second"]

    @patch("src.services.youtube_search_service.requests.get")
    def test_returns_error_when_quota_exhausted(self, mock_get, tmp_path):
        service, tracker = _make_service_with_tracker(tmp_path)
        for _ in range(100):
            tracker.consume("search")
        with patch.object(
            YouTubeSearchService,
            "api_key",
            new_callable=PropertyMock,
            return_value="fakekey",
        ):
            result = service.search_videos_as_typed("anything", limit=5)

        mock_get.assert_not_called()
        assert result["videos"] == []
        assert "quota" in result["error"].lower()


@patch("src.services.youtube_search_service.requests.get")
def test_search_skips_items_without_video_id(mock_get, tmp_path):
    """A result item lacking id.videoId must be skipped, not fail the search."""
    service, _ = _make_service_with_tracker(tmp_path)
    payload = _fake_search_response(2)
    payload["items"].insert(1, {"id": {"kind": "youtube#channel"}, "snippet": {}})
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: payload, raise_for_status=lambda: None
    )
    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        result = service.search_videos_as_typed("anything", limit=5)

    assert "error" not in result
    assert [v["youtube_id"] for v in result["videos"]] == ["vid0", "vid1"]


def _quota_429():
    import requests

    response = requests.Response()
    response.status_code = 429
    response._content = b"Quota exceeded for metric 'Search Queries' per day"
    return response


@patch("src.services.youtube_search_service.requests.get")
def test_daily_quota_429_stops_all_further_calls(mock_get, tmp_path):
    """After Google says the daily quota is gone, don't keep calling it."""
    service, tracker = _make_service_with_tracker(tmp_path)
    mock_get.return_value = _quota_429()
    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        first = service.search_videos_as_typed("alien ant farm")
        second = service.search_videos_as_typed("alien ant farm again")

    assert tracker.is_exhausted() is True
    assert mock_get.call_count == 1, "second search must not reach the API"
    assert "error" in first
    assert "quota" in second["error"].lower()


@patch("src.services.youtube_search_service.requests.get")
def test_title_search_skips_items_without_video_id_and_honors_exhaustion(
    mock_get, tmp_path
):
    service, tracker = _make_service_with_tracker(tmp_path)
    payload = _fake_search_response(1)
    payload["items"].append({"id": {"kind": "youtube#channel"}, "snippet": {}})
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: payload, raise_for_status=lambda: None
    )
    with patch.object(
        YouTubeSearchService,
        "api_key",
        new_callable=PropertyMock,
        return_value="fakekey",
    ):
        ok = service.search_video_by_title("Creep", "Radiohead")
        assert [v["youtube_id"] for v in ok["videos"]] == ["vid0"]

        tracker.mark_exhausted()
        mock_get.reset_mock()
        blocked = service.search_video_by_title("Other Song", "Radiohead")

    assert mock_get.call_count == 0
    assert "quota" in blocked["error"].lower()
