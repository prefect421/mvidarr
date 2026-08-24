"""Fix for #387: resolve_video_url() call condition has an
operator-precedence bug (pre-existing).

videos_downloads.py computed a video's already-stored URL via:

    video.url
    or video.youtube_url
    or f"https://youtube.com/watch?v={video.youtube_id}"
    if hasattr(video, "youtube_id") and video.youtube_id
    else None

Python's conditional expression (`X if C else Y`) binds looser than
`or`, so this parses as:

    (video.url or video.youtube_url or f"...watch?v={youtube_id}") if (hasattr(...) and youtube_id) else None

-- the whole `or`-chain is the ternary's "true" value, and the youtube_id
check gates ALL of it, not just the f-string fallback. A video with
`url` set but no `youtube_id` therefore evaluates the outer condition to
False and the whole expression to None, discarding a perfectly usable
`video.url` -- silently falling through to an unnecessary
resolve_video_url() call (harmless today only because that function
independently re-checks video.url first, but wasteful, and fragile
against future changes to that function). Confirmed identical, copy-
pasted in 5 places across this file (not just the one #387 named):
bulk_download_videos(), queue_video_download() (x2, one as
original_url= for the Download record), bulk_download_wanted_videos()
(x2, same original_url= pattern).

Fix: extracted the shared logic into _stored_video_url(video,
missing_value), which parenthesizes correctly -- the youtube_id ternary
now only governs the final fallback branch -- and used it in all 5
places, eliminating the duplication along with the bug.
"""

from types import SimpleNamespace

from src.api.fastapi.videos_downloads import _stored_video_url


def _video(url=None, youtube_url=None, youtube_id=None):
    return SimpleNamespace(url=url, youtube_url=youtube_url, youtube_id=youtube_id)


class TestStoredVideoUrl:
    def test_url_wins_even_without_a_youtube_id(self):
        # The exact bug: a video with url set but no youtube_id used to
        # yield None here instead of the url.
        video = _video(url="https://example.com/video.mp4", youtube_id=None)
        assert _stored_video_url(video) == "https://example.com/video.mp4"

    def test_url_wins_over_youtube_url_and_youtube_id(self):
        video = _video(
            url="https://example.com/video.mp4",
            youtube_url="https://youtube.com/watch?v=abc123",
            youtube_id="abc123",
        )
        assert _stored_video_url(video) == "https://example.com/video.mp4"

    def test_falls_back_to_youtube_url_when_url_is_missing(self):
        video = _video(youtube_url="https://youtube.com/watch?v=abc123")
        assert _stored_video_url(video) == "https://youtube.com/watch?v=abc123"

    def test_falls_back_to_a_constructed_youtube_watch_url_last(self):
        video = _video(youtube_id="abc123")
        assert _stored_video_url(video) == "https://youtube.com/watch?v=abc123"

    def test_returns_default_missing_value_when_nothing_is_available(self):
        video = _video()
        assert _stored_video_url(video) is None

    def test_returns_the_given_missing_value_when_nothing_is_available(self):
        video = _video()
        assert _stored_video_url(video, missing_value="Unknown URL") == "Unknown URL"

    def test_empty_string_youtube_id_does_not_construct_a_watch_url(self):
        video = _video(youtube_id="")
        assert _stored_video_url(video) is None
