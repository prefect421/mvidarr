"""#604: Maximum Quality Limit / Max File Size settings must reach yt-dlp."""

from unittest.mock import patch

from src.services import unified_download_service as uds
from src.services.unified_download_service import (
    build_quality_format,
    parse_height,
)


def test_parse_height():
    assert parse_height("1080p") == 1080
    assert parse_height("2160p") == 2160
    assert parse_height("best") is None
    assert parse_height(None) is None
    assert parse_height("garbage") is None


class TestBuildQualityFormat:
    def test_no_limits_keeps_the_existing_best_format(self):
        fmt = build_quality_format("best")
        assert fmt.startswith("bestvideo[height<=2160]+bestaudio")
        assert fmt.endswith("/bestvideo+bestaudio/best")

    def test_best_is_capped_by_max_height(self):
        fmt = build_quality_format("best", max_height=1080)
        assert "2160" not in fmt
        assert "[height<=1080]" in fmt
        # no unconstrained last-resort tail that would silently defeat the cap
        assert not fmt.endswith("/best")
        assert "/bestvideo+bestaudio" not in fmt

    def test_explicit_quality_is_clamped_to_the_cap(self):
        assert "2160" not in build_quality_format("2160p", max_height=720)
        assert "[height<=720]" in build_quality_format("2160p", max_height=720)

    def test_lower_explicit_quality_is_kept(self):
        fmt = build_quality_format("480p", max_height=1080)
        assert "[height<=480]" in fmt and "1080" not in fmt

    def test_custom_selector_passes_through_untouched(self):
        custom = "bestvideo[height<=1440][vcodec^=av01]+bestaudio"
        assert build_quality_format(custom, max_height=720) == custom

    def test_file_size_cap_adds_a_size_filter_with_a_height_only_fallback(self):
        fmt = build_quality_format("best", max_height=1080, max_filesize_gb=2)
        size = 2 * 1024**3
        assert f"filesize<?{size}" in fmt
        # last resort drops the size filter so the download still succeeds
        assert fmt.rsplit("/", 1)[-1].count("filesize") == 0


class TestGetQualityFormatReadsSettings:
    def _strategy(self):
        return uds.YouTubeDownloadStrategy.__new__(uds.YouTubeDownloadStrategy)

    def test_uses_max_video_quality_setting(self):
        values = {"max_video_quality": "1080p", "max_video_file_size_gb": "10"}
        with patch.object(
            uds.settings, "get", side_effect=lambda k, d=None: values.get(k, d)
        ):
            fmt = self._strategy()._get_quality_format("best")
        assert "[height<=1080]" in fmt and "2160" not in fmt

    def test_settings_failure_means_no_limit_not_a_failed_download(self):
        with patch.object(uds.settings, "get", side_effect=RuntimeError("db down")):
            fmt = self._strategy()._get_quality_format("best")
        assert fmt.startswith("bestvideo[height<=2160]+bestaudio")
