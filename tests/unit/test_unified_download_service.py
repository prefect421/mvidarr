"""Tests for YouTubeDownloadStrategy/UnifiedDownloadService download logic."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.unified_download_service import (
    AntiDetectionLevel,
    DownloadContext,
    DownloadResult,
    UnifiedDownloadService,
    YouTubeDownloadStrategy,
)


def _make_strategy():
    return YouTubeDownloadStrategy(
        ytdlp_manager=MagicMock(), anti_detection=MagicMock()
    )


def _make_context(**overrides):
    defaults = dict(
        video_id=1,
        url="https://www.youtube.com/watch?v=abc12345678",
        title="Artist - Song",
        artist="Artist",
        quality="best",
        output_path="/tmp",
        anti_detection=AntiDetectionLevel.AGGRESSIVE,
    )
    defaults.update(overrides)
    return DownloadContext(**defaults)


class TestLowResRetryFilePreservation:
    """Covers the low-res retry path in YouTubeDownloadStrategy.download()."""

    def test_keeps_original_file_when_retry_fails(self, tmp_path):
        strategy = _make_strategy()
        original_file = tmp_path / "video.mp4"
        original_file.write_bytes(b"original-360p")

        original_result = DownloadResult(success=True, file_path=str(original_file))
        retry_result = DownloadResult(success=False, error_message="retry failed")

        with patch.object(
            strategy,
            "_attempt_download",
            side_effect=[original_result, retry_result],
        ), patch.object(strategy, "_probe_video_height", return_value=360):
            result = strategy.download(_make_context())

        assert result.success is True
        assert result.file_path == str(original_file)
        assert (
            original_file.exists()
        ), "original download must not be deleted when the retry fails"

    def test_keeps_original_file_when_retry_is_not_better(self, tmp_path):
        strategy = _make_strategy()
        original_file = tmp_path / "video.mp4"
        original_file.write_bytes(b"original-360p")
        retry_file = tmp_path / "video_retry.mp4"
        retry_file.write_bytes(b"retry-240p")

        original_result = DownloadResult(success=True, file_path=str(original_file))
        retry_result = DownloadResult(success=True, file_path=str(retry_file))
        heights = {str(original_file): 360, str(retry_file): 240}

        with patch.object(
            strategy,
            "_attempt_download",
            side_effect=[original_result, retry_result],
        ), patch.object(
            strategy, "_probe_video_height", side_effect=lambda p: heights[p]
        ):
            result = strategy.download(_make_context())

        assert result.success is True
        assert result.file_path == str(original_file)
        assert (
            original_file.exists()
        ), "higher-resolution original must survive a worse retry"
        assert (
            not retry_file.exists()
        ), "discarded worse retry file should be cleaned up"

    def test_returns_retry_when_it_is_better(self, tmp_path):
        strategy = _make_strategy()
        original_file = tmp_path / "video.mp4"
        original_file.write_bytes(b"original-360p")
        retry_file = tmp_path / "video_retry.mp4"
        retry_file.write_bytes(b"retry-1080p")

        original_result = DownloadResult(success=True, file_path=str(original_file))
        retry_result = DownloadResult(success=True, file_path=str(retry_file))
        heights = {str(original_file): 360, str(retry_file): 1080}

        with patch.object(
            strategy,
            "_attempt_download",
            side_effect=[original_result, retry_result],
        ), patch.object(
            strategy, "_probe_video_height", side_effect=lambda p: heights[p]
        ):
            result = strategy.download(_make_context())

        assert result.success is True
        assert result.file_path == str(retry_file)
        assert (
            not original_file.exists()
        ), "superseded low-res original should be discarded once the retry wins"


class TestGetQualityFormat:
    def test_best_prefers_separate_streams_up_to_4k(self):
        strategy = _make_strategy()
        fmt = strategy._get_quality_format("best")
        assert fmt.startswith("bestvideo[height<=2160]+bestaudio")

    def test_numeric_quality_caps_height(self):
        strategy = _make_strategy()
        fmt = strategy._get_quality_format("1080p")
        assert "height<=1080" in fmt

    def test_custom_format_string_passthrough(self):
        strategy = _make_strategy()
        custom = "bestvideo[height<=720]+bestaudio"
        assert strategy._get_quality_format(custom) == custom


class TestFindDownloadedFile:
    def test_prefers_merged_output_line(self, tmp_path):
        strategy = _make_strategy()
        template = str(tmp_path / "Song.%(ext)s")
        merged_path = tmp_path / "Song.mp4"
        lines = [f'Merging formats into "{merged_path}"']

        assert strategy._find_downloaded_file(template, lines) == str(merged_path)

    def test_skips_info_json_destination(self, tmp_path):
        strategy = _make_strategy()
        template = str(tmp_path / "Song.%(ext)s")
        lines = [
            f"Destination: {tmp_path / 'Song.info.json'}",
            f"Destination: {tmp_path / 'Song.mp4'}",
        ]

        assert strategy._find_downloaded_file(template, lines) == str(
            tmp_path / "Song.mp4"
        )

    def test_falls_back_to_directory_scan(self, tmp_path):
        strategy = _make_strategy()
        (tmp_path / "Song.info.json").write_text("{}")
        (tmp_path / "Song.mp4").write_bytes(b"data")
        template = str(tmp_path / "Song.%(ext)s")

        assert strategy._find_downloaded_file(template, []) == str(
            tmp_path / "Song.mp4"
        )


class TestIsDeadYoutubeError:
    def _check(self, message):
        service = UnifiedDownloadService.__new__(UnifiedDownloadService)
        return service._is_dead_youtube_error(message)

    @pytest.mark.parametrize(
        "message",
        [
            "ERROR: Private video. Sign in if you've been granted access",
            "ERROR: Video unavailable",
            "This video has been terminated for a violation of YouTube's policy",
            "ERROR: [youtube] abc12345678: This video is not available",
        ],
    )
    def test_detects_dead_url_markers(self, message):
        assert self._check(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "",
            "ERROR: Unable to download webpage: HTTP Error 429",
            "Process error: timed out",
        ],
    )
    def test_does_not_flag_transient_errors(self, message):
        assert self._check(message) is False
