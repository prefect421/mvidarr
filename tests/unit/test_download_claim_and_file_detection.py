"""#605: a Download row must run exactly once, and local_path must never point
at a yt-dlp intermediate (.fNNN.ext) file."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.services.download_service_adapter import DownloadServiceAdapter
from src.services.unified_download_service import YouTubeDownloadStrategy


def _adapter():
    a = DownloadServiceAdapter.__new__(DownloadServiceAdapter)
    a.music_videos_path = "/tmp/mv-test"
    a.unified_service = MagicMock()
    a.unified_service.download_video.return_value = 111
    a.active_downloads = {}
    a.download_queue = []
    a._get_working_cookies_path = lambda: None
    a._get_anti_detection_level = lambda: None
    return a


def _session_with_rowcount(rowcount):
    session = MagicMock()
    session.query.return_value.filter.return_value.update.return_value = rowcount

    @contextmanager
    def fake_get_db():
        yield session

    return fake_get_db, session


class TestAtomicClaim:
    def test_dispatch_claims_the_download_row_first(self):
        get_db, session = _session_with_rowcount(1)
        a = _adapter()
        with patch("src.database.connection.get_db", get_db), patch("os.makedirs"):
            res = a.add_music_video_download("A", "T", "u", video_id=5, download_id=6)
        assert res["success"] is True
        session.query.return_value.filter.return_value.update.assert_called_once()
        session.commit.assert_called()
        a.unified_service.download_video.assert_called_once()

    def test_lost_claim_does_not_start_a_second_download(self):
        get_db, _ = _session_with_rowcount(0)
        a = _adapter()
        with patch("src.database.connection.get_db", get_db), patch("os.makedirs"):
            res = a.add_music_video_download("A", "T", "u", video_id=5, download_id=6)
        assert res["success"] is False
        assert res.get("already_claimed") is True
        a.unified_service.download_video.assert_not_called()

    def test_no_download_id_skips_claim(self):
        a = _adapter()
        with patch("os.makedirs"):
            res = a.add_music_video_download("A", "T", "u")
        assert res["success"] is True


class TestFindDownloadedFile:
    @pytest.fixture
    def strategy(self):
        return YouTubeDownloadStrategy.__new__(YouTubeDownloadStrategy)

    def test_intermediate_destination_is_ignored(self, strategy, tmp_path):
        tmpl = str(tmp_path / "Song.%(ext)s")
        lines = [
            f"[download] Destination: {tmp_path}/Song.f625.mp4",
            f"[download] Destination: {tmp_path}/Song.f251.webm",
        ]
        assert strategy._find_downloaded_file(tmpl, lines) is None

    def test_merged_output_wins_over_fragments(self, strategy, tmp_path):
        tmpl = str(tmp_path / "Song.%(ext)s")
        lines = [
            f"[download] Destination: {tmp_path}/Song.f251.webm",
            f'[Merger] Merging formats into "{tmp_path}/Song.webm"',
        ]
        assert strategy._find_downloaded_file(tmpl, lines) == f"{tmp_path}/Song.webm"

    def test_directory_fallback_skips_fragments_and_prefers_exact_stem(
        self, strategy, tmp_path
    ):
        import os
        import time

        final = tmp_path / "Song.webm"
        frag = tmp_path / "Song.f251.webm"
        final.write_bytes(b"x" * 10)
        time.sleep(0.01)
        frag.write_bytes(b"y")  # newest, but a fragment
        os.utime(frag, None)
        tmpl = str(tmp_path / "Song.%(ext)s")
        assert strategy._find_downloaded_file(tmpl, []) == str(final)
