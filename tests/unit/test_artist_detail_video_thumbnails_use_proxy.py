"""Live-reported: videos 167, 170, 173, 174 (and any other video whose
thumbnail_url points at an external CDN -- Spotify's i.scdn.co, YouTube's
img.youtube.com, etc.) showed as missing thumbnails on the artist detail
page's video grid, even though the app's own thumbnail cache and proxy
endpoint (/api/videos/{id}/thumbnail) served them correctly when tested
directly (200, valid cached JPEG on disk).

Root cause: unlike videos.html's video grid, which correctly uses
`/api/videos/${video.id}/thumbnail` (the app's own caching proxy),
artist_detail.html's main video grid and its "preview selected videos"
modal both hotlinked `video.thumbnail_url` directly -- bypassing the
app's cache entirely and depending on the external CDN being reachable,
un-hotlink-protected, and not blocked by the browser (e.g. tracking
protection flagging a third-party CDN domain) at the exact moment the
page renders. Worse, the `data-fallback-src="/static/placeholder-video.png"`
attribute on these <img> tags was never wired to any onerror handler --
dead markup -- so any such failure showed a permanently broken image
with no fallback and no retry.

Fix: both occurrences now use the same proxy-endpoint pattern as
videos.html, with a real onerror fallback to the placeholder image.

NOT changed: the "discovered videos" list (a separate, pre-import
search-results view -- these videos may not have a real row/ID in our
own database yet, so the proxy endpoint wouldn't work for them; hotlinking
the raw source URL is correct there).
"""

import re
from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent
    / "frontend"
    / "templates"
    / "artist_detail.html"
)


def _source() -> str:
    return TEMPLATE_PATH.read_text()


class TestArtistDetailVideoGridUsesThumbnailProxy:
    def test_main_video_grid_uses_the_proxy_endpoint(self):
        source = _source()
        # The main artist video grid card (data-video-id, handleVideoCardClick)
        grid_marker = 'data-video-id="${video.id}" data-status="${video.status}" onclick="handleVideoCardClick'
        grid_pos = source.index(grid_marker)
        window = source[grid_pos : grid_pos + 800]
        img_tag = window.split("<img")[1].split(">")[0]
        assert "/api/videos/${video.id}/thumbnail" in img_tag
        assert "video.thumbnail_url" not in img_tag

    def test_preview_selected_videos_uses_the_proxy_endpoint(self):
        source = _source()
        preview_marker = "const previewHtml = selectedVideoData.map(video => `"
        preview_pos = source.index(preview_marker)
        window = source[preview_pos : preview_pos + 400]
        assert "/api/videos/${video.id}/thumbnail" in window

    def test_discovered_videos_list_still_hotlinks_the_raw_source_url(self):
        # Pre-import search results have no local video row/ID -- the
        # proxy endpoint would 404 for them. This one must NOT change.
        source = _source()
        discovered_marker = "discovered-video-thumbnail"
        discovered_pos = source.index(discovered_marker)
        window = source[discovered_pos : discovered_pos + 200]
        assert "${video.thumbnail_url || '/static/placeholder-video.png'}" in window

    def test_fixed_thumbnails_have_a_real_onerror_fallback(self):
        source = _source()
        grid_marker = 'data-video-id="${video.id}" data-status="${video.status}" onclick="handleVideoCardClick'
        grid_pos = source.index(grid_marker)
        window = source[grid_pos : grid_pos + 800]
        assert "onerror=" in window

    def test_no_dead_data_fallback_src_left_on_the_fixed_tags(self):
        source = _source()
        grid_marker = 'data-video-id="${video.id}" data-status="${video.status}" onclick="handleVideoCardClick'
        grid_pos = source.index(grid_marker)
        window = source[grid_pos : grid_pos + 800]
        # data-fallback-src alone (with no onerror handler reading it)
        # was the dead markup this bug involved -- if kept, it must now
        # actually be used.
        if "data-fallback-src" in window:
            assert "onerror=" in window
