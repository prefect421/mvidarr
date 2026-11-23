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
    # \" stays encoded: the frontend interpolates these into attributes/innerHTML
    assert v["description"] == "Tom & Jerry &quot;live&quot;"
    assert v["channel_title"] == "Ben & Jerry's VEVO"


def test_markup_characters_stay_encoded_so_titles_cannot_become_html():
    from src.services.title_unescape_service import unescape_text

    hostile = "&lt;img src=x onerror=alert(1)&gt; &quot;x&quot; &amp; &#39;y&#39;"
    out = unescape_text(hostile)
    assert "<" not in out and ">" not in out and '"' not in out
    assert out == "&lt;img src=x onerror=alert(1)&gt; &quot;x&quot; & 'y'"
    # numeric forms of the markup characters stay encoded too
    assert (
        unescape_text("&#60;b&#62; &#34;q&#34; &#x3c;")
        == "&#60;b&#62; &#34;q&#34; &#x3c;"
    )
    # one pass only: a double-encoded entity never turns into live markup
    assert "<" not in unescape_text("&amp;lt;script&amp;gt;")


def test_malformed_entities_without_semicolon_are_left_alone():
    # Seen in real libraries ('&quotTrue North&quot'): not API escaping, and
    # html.unescape()'s lenient legacy decoding would only churn them.
    from src.services.title_unescape_service import unescape_text

    for t in ["&quotTrue North&quot", "Fish&chips", "AT&T", "a &amp b"]:
        assert unescape_text(t) == t
