"""First slice of #317 (broaden test coverage beyond auth): real unit
tests for youtube_download_engine.py, which had zero dedicated test
coverage despite being the actual yt-dlp subprocess/strategy logic --
cookie handling, quality format selection, filename sanitization -- that
every video download in this app ultimately goes through.

Scoped to this file's three pure, self-contained helper methods
(no I/O beyond a single os.path.exists() call, easily mocked; no
network, no real subprocess invocation): _get_cookie_args(),
_get_quality_format(), _sanitize_filename(). Chosen as the highest-value
first slice for two reasons: they're the most tractable part of a large,
mostly-untested subsystem to add genuine behavioral coverage for in one
sitting, and _get_cookie_args() specifically is the exact code path
behind two live-reported download failures (#443: "Sign in to confirm
your age" -- the missing-cookie-file case this test suite pins down
directly).

YouTubeDownloadEngine() instantiates a real subprocess-backed engine on
construction (_find_best_ytdlp(), _ensure_latest_ytdlp()) and does so
again at import time via a module-level singleton
(youtube_download_engine = YouTubeDownloadEngine()) -- the module
imports fine in this test venv (no exception, just log noise about a
missing `pipx`), but instantiating a *second* real engine per test would
be slow and side-effecting for no benefit, since none of the three
methods under test touch any instance state. Bypassing __init__ via
__new__ avoids that entirely.

The broader scoping this issue needs (scheduler_service_v2.py,
imvdb_discovery_service.py, enhanced_artist_discovery_service.py, and
the rest of this file's own untested surface -- strategy dispatch,
_find_downloaded_file(), the real subprocess-invoking download path) is
tracked in a follow-up comment on #317 rather than attempted here.
"""

from unittest.mock import patch

from src.services.youtube_download_engine import YouTubeDownloadEngine


def _engine():
    """Bypass __init__ (real subprocess calls) -- none of the methods
    under test use any instance state."""
    return YouTubeDownloadEngine.__new__(YouTubeDownloadEngine)


class TestGetCookieArgs:
    """#443 (live-reported): a video download failed with YouTube's
    "Sign in to confirm your age" error. Root-caused to this exact
    method returning no --cookies argument at all because
    data/cookies/youtube_cookies.txt didn't exist on that deployment."""

    def test_returns_cookies_flag_when_cookie_file_exists(self):
        engine = _engine()
        with patch("os.path.exists", return_value=True):
            args = engine._get_cookie_args()
        assert args == ["--cookies", "data/cookies/youtube_cookies.txt"]

    def test_returns_empty_list_when_cookie_file_is_missing(self):
        # The exact condition behind #443: no cookie file means no
        # --cookies argument is passed to yt-dlp at all, so any
        # age-restricted video fails outright.
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            args = engine._get_cookie_args()
        assert args == []

    def test_ignores_the_strategy_argument(self):
        # The method accepts a strategy parameter but never reads it --
        # every strategy gets the same cookie file (or none). Pinning
        # this down so a future change that starts branching on
        # strategy is a deliberate choice, not an accident.
        from src.services.youtube_download_engine import DownloadStrategy

        engine = _engine()
        with patch("os.path.exists", return_value=True):
            tv_args = engine._get_cookie_args(DownloadStrategy.TV_CLIENT)
            web_args = engine._get_cookie_args(DownloadStrategy.WEB_CLIENT_COOKIES)
            no_strategy_args = engine._get_cookie_args()
        assert tv_args == web_args == no_strategy_args


class TestGetQualityFormat:
    """Referenced at length in this project's own CLAUDE.md ("Video
    Quality Improvements (360p -> 1080p)" investigation) -- format
    selection is a documented history of real quality-related bugs."""

    def test_best_quality_caps_at_1080p(self):
        engine = _engine()
        assert (
            engine._get_quality_format("best")
            == "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        )

    def test_explicit_height_quality_builds_matching_format(self):
        engine = _engine()
        assert (
            engine._get_quality_format("720p")
            == "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        )

    def test_another_explicit_height_quality(self):
        engine = _engine()
        assert (
            engine._get_quality_format("480p")
            == "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        )

    def test_unrecognized_quality_string_falls_back_to_unrestricted(self):
        engine = _engine()
        assert engine._get_quality_format("ultra") == "bestvideo+bestaudio/best"


class TestSanitizeFilename:
    def test_strips_filesystem_unsafe_characters(self):
        engine = _engine()
        result = engine._sanitize_filename('Artist: "Song" <Live> / Version?*|')
        for char in '<>:"/\\|?*':
            assert char not in result

    def test_leaves_ordinary_characters_untouched(self):
        engine = _engine()
        assert engine._sanitize_filename("Artist - Song Title") == "Artist - Song Title"

    def test_truncates_to_200_characters(self):
        engine = _engine()
        result = engine._sanitize_filename("x" * 500)
        assert len(result) == 200
