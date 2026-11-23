"""#613: thumbnail URL selection for imported YouTube videos (no DB needed)."""

import pytest

from src.api.fastapi.videos_import import resolve_import_thumbnail_url


class TestResolveImportThumbnailUrl:
    def test_falls_back_to_standard_hqdefault(self):
        assert (
            resolve_import_thumbnail_url(None, "abc123")
            == "https://img.youtube.com/vi/abc123/hqdefault.jpg"
        )

    def test_accepts_youtube_image_hosts(self):
        url = "https://i.ytimg.com/vi/abc123/mqdefault.jpg"
        assert resolve_import_thumbnail_url(url, "abc123") == url

    @pytest.mark.parametrize(
        "bad",
        [
            "http://169.254.169.254/latest/meta-data",
            "https://evil.example/x.jpg",
            "file:///etc/passwd",
            "https://i.ytimg.com.evil.example/x.jpg",
            "",
        ],
    )
    def test_rejects_untrusted_urls_to_avoid_ssrf(self, bad):
        # the server later downloads thumbnail_url, so never trust arbitrary hosts
        assert (
            resolve_import_thumbnail_url(bad, "abc123")
            == "https://img.youtube.com/vi/abc123/hqdefault.jpg"
        )
