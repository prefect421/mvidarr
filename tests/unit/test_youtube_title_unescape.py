"""#612: YouTube Data API returns HTML-escaped snippet text; unescape at parse time."""

from unittest.mock import MagicMock, PropertyMock, patch

from src.services import youtube_search_service as yss


def _api_payload():
    return {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "MACKLEMORE &amp; RYAN LEWIS - Where&#39;s our love",
                    "description": "Tom &amp; Jerry &quot;live&quot;",
                    "channelTitle": "Ben &amp; Jerry&#39;s VEVO",
                    "channelId": "c1",
                    "publishedAt": "2020-01-01T00:00:00Z",
                    "thumbnails": {},
                },
            }
        ]
    }


def _service():
    svc = yss.YouTubeSearchService.__new__(yss.YouTubeSearchService)
    svc.base_url = "https://example.invalid"
    svc._quota_tracker = MagicMock()
    svc._quota_tracker.has_budget.return_value = True
    svc._get_video_details = lambda ids: {}
    return svc


def test_search_api_unescapes_title_description_and_channel():
    svc = _service()
    resp = MagicMock()
    resp.json.return_value = _api_payload()
    with patch.object(
        yss.YouTubeSearchService, "api_key", new_callable=PropertyMock, return_value="k"
    ), patch.object(yss.requests, "get", return_value=resp):
        out = svc._search_youtube_api("q", 5)
    v = out["videos"][0]
    assert v["title"] == "MACKLEMORE & RYAN LEWIS - Where's our love"
    assert v["description"] == 'Tom & Jerry "live"'
    assert v["channel_title"] == "Ben & Jerry's VEVO"
