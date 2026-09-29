"""youtube_service / async_youtube_service must respect and feed the shared
YouTube quota tracker (they used to call the API without it, so their spend
was invisible and they kept calling after Google said the quota was gone)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.async_youtube_service import AsyncYouTubeService
from src.services.youtube_service import YouTubeService
from src.utils.youtube_quota_tracker import YouTubeQuotaTracker

QUOTA_BODY = "Quota exceeded for metric 'Search Queries' per day"


@pytest.fixture
def tracker(tmp_path):
    t = YouTubeQuotaTracker(storage_path=str(tmp_path / "quota.json"))
    with patch("src.services.youtube_service.get_quota_tracker", return_value=t), patch(
        "src.services.async_youtube_service.get_quota_tracker", return_value=t
    ):
        yield t


@pytest.fixture
def sync_service():
    settings = MagicMock()
    settings.get.return_value = "fakekey"
    service = YouTubeService(settings)
    service.get_api_key = lambda: "fakekey"
    return service


def _response(status, body="", json_data=None):
    return SimpleNamespace(
        status_code=status, text=body, json=lambda: json_data or {"items": []}
    )


class TestSyncService:
    def test_search_counts_successful_call(self, tracker, sync_service):
        with patch("src.services.youtube_service.requests.get") as get:
            get.return_value = _response(200)
            assert sync_service.search_videos("moon")["success"] is True
        assert tracker.get_stats()["operations"]["search"]["quota_used"] == 100

    def test_daily_quota_response_marks_exhausted(self, tracker, sync_service):
        with patch("src.services.youtube_service.requests.get") as get:
            get.return_value = _response(429, QUOTA_BODY)
            result = sync_service.search_videos("moon")
        assert result["success"] is False and "quota" in result["error"].lower()
        assert tracker.is_exhausted() is True

    def test_no_api_call_once_exhausted(self, tracker, sync_service):
        tracker.mark_exhausted()
        with patch("src.services.youtube_service.requests.get") as get:
            assert sync_service.search_videos("moon")["success"] is False
            assert sync_service.get_video_details("abc")["success"] is False
        get.assert_not_called()

    def test_connection_test_costs_one_unit_not_a_search(self, tracker, sync_service):
        with patch("src.services.youtube_service.requests.get") as get:
            get.return_value = _response(200, json_data={"items": [{"id": "x"}]})
            assert sync_service.test_api_connection()["success"] is True
        ops = tracker.get_stats()["operations"]
        assert "search" not in ops and ops["video_details"]["quota_used"] == 1

    def test_connection_test_reports_exhausted_without_calling(
        self, tracker, sync_service
    ):
        tracker.mark_exhausted()
        with patch("src.services.youtube_service.requests.get") as get:
            result = sync_service.test_api_connection()
        get.assert_not_called()
        assert result["success"] is False and "quota" in result["message"].lower()


class TestAsyncService:
    @pytest.fixture
    def service(self):
        service = AsyncYouTubeService()
        service.get_api_key = AsyncMock(return_value="fakekey")
        return service

    @staticmethod
    def _client(response):
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        return (
            patch(
                "src.services.async_youtube_service.get_global_httpx_client",
                AsyncMock(return_value=client),
            ),
            client,
        )

    @pytest.mark.asyncio
    async def test_search_counts_successful_call(self, tracker, service):
        patcher, _ = self._client(_response(200))
        with patcher:
            assert (await service.search_videos("moon"))["success"] is True
        assert tracker.get_stats()["operations"]["search"]["quota_used"] == 100

    @pytest.mark.asyncio
    async def test_daily_quota_response_marks_exhausted(self, tracker, service):
        patcher, _ = self._client(_response(429, QUOTA_BODY))
        with patcher:
            result = await service.search_videos("moon")
        assert result["success"] is False and "quota" in result["error"].lower()
        assert tracker.is_exhausted() is True

    @pytest.mark.asyncio
    async def test_no_api_call_once_exhausted(self, tracker, service):
        tracker.mark_exhausted()
        patcher, client = self._client(_response(200))
        with patcher:
            assert (await service.search_videos("moon"))["success"] is False
            assert (await service.get_video_details(["abc"]))["success"] is False
        client.get.assert_not_called()
