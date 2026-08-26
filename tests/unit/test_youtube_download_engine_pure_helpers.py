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

Second pass (same #317, later slice): the 5 strategy-specific arg
builders (_get_strategy_args, _get_tv_client_args,
_get_android_client_args, _get_web_cookies_args,
_get_web_fallback_args) and _extract_error_message -- all pure, no I/O
beyond delegating to the already-tested _get_cookie_args() above.
_extract_error_message specifically feeds every failed-download error
message a user actually sees, directly relevant given #443/#452's
cookie/PO-token investigations earlier this session.
"""

from unittest.mock import patch

from src.services.youtube_download_engine import DownloadStrategy, YouTubeDownloadEngine


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


class TestGetStrategyArgs:
    def test_tv_client_strategy_dispatches_to_tv_client_args(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            dispatched = engine._get_strategy_args(DownloadStrategy.TV_CLIENT)
            direct = engine._get_tv_client_args()
        assert dispatched == direct

    def test_web_client_cookies_strategy_dispatches_to_web_cookies_args(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            dispatched = engine._get_strategy_args(DownloadStrategy.WEB_CLIENT_COOKIES)
            direct = engine._get_web_cookies_args()
        assert dispatched == direct

    def test_web_client_fallback_strategy_dispatches_to_web_fallback_args(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            dispatched = engine._get_strategy_args(DownloadStrategy.WEB_CLIENT_FALLBACK)
            direct = engine._get_web_fallback_args()
        assert dispatched == direct

    def test_android_client_has_no_dedicated_enum_value_and_is_unreachable_via_dispatch(
        self,
    ):
        # DownloadStrategy only defines TV_CLIENT/WEB_CLIENT_COOKIES/
        # WEB_CLIENT_FALLBACK -- _get_android_client_args() exists and
        # is fully implemented (see TestGetAndroidClientArgs below) but
        # _get_strategy_args()'s if/elif chain has no branch that can
        # ever reach it. Not necessarily a bug (Android may be legacy
        # or reserved for a future strategy), but worth pinning down:
        # dead code that looks reachable from the public
        # DownloadStrategy enum is easy to assume is in use when it
        # isn't.
        assert not hasattr(DownloadStrategy, "ANDROID_CLIENT")


class TestGetTvClientArgs:
    def test_uses_the_tv_client_with_web_fallback(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            args = engine._get_tv_client_args()
        idx = args.index("--extractor-args")
        assert args[idx + 1] == "youtube:player_client=tv,web"

    def test_includes_cookie_args_for_age_restricted_videos(self):
        # TV client still needs cookies -- age-restriction isn't
        # client-specific.
        engine = _engine()
        with patch("os.path.exists", return_value=True):
            args = engine._get_tv_client_args()
        assert "--cookies" in args


class TestGetAndroidClientArgs:
    def test_uses_the_android_client_with_a_matching_user_agent(self):
        engine = _engine()
        args = engine._get_android_client_args()
        idx = args.index("--extractor-args")
        assert args[idx + 1] == "youtube:player_client=android"
        assert "--add-header" in args

    def test_never_includes_cookie_args(self):
        # Unlike every other strategy, android intentionally never
        # calls _get_cookie_args() at all -- confirmed live this
        # session (#452): yt-dlp actively refuses the android client
        # when cookies are supplied ("Skipping client "android" since
        # it does not support cookies").
        engine = _engine()
        with patch("os.path.exists", return_value=True):
            args = engine._get_android_client_args()
        assert "--cookies" not in args


class TestGetWebCookiesArgs:
    def test_uses_the_web_client(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            args = engine._get_web_cookies_args()
        idx = args.index("--extractor-args")
        assert args[idx + 1] == "youtube:player_client=web"

    def test_includes_cookie_args_when_available(self):
        engine = _engine()
        with patch("os.path.exists", return_value=True):
            args = engine._get_web_cookies_args()
        assert "--cookies" in args


class TestGetWebFallbackArgs:
    def test_uses_the_broadest_client_list_as_a_last_resort(self):
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            args = engine._get_web_fallback_args()
        idx = args.index("--extractor-args")
        assert args[idx + 1] == "youtube:player_client=web,tv,android"

    def test_uses_longer_timeouts_and_more_retries_than_the_other_strategies(self):
        # Last-resort strategy -- more patient than TV/web-cookies.
        engine = _engine()
        with patch("os.path.exists", return_value=False):
            fallback_args = engine._get_web_fallback_args()
            tv_args = engine._get_tv_client_args()
        fallback_timeout = int(
            fallback_args[fallback_args.index("--socket-timeout") + 1]
        )
        tv_timeout = int(tv_args[tv_args.index("--socket-timeout") + 1])
        assert fallback_timeout > tv_timeout


class TestExtractErrorMessage:
    """Feeds every failed-download error message a user actually sees
    -- directly relevant to this session's #443/#452 cookie/PO-token
    investigations, where the exact wording of yt-dlp's failure output
    was the whole diagnostic trail."""

    def test_prefers_the_last_error_line_when_multiple_are_present(self):
        engine = _engine()
        output = "some setup output\nERROR: first problem\nmore output\nERROR: real final problem"
        assert engine._extract_error_message(output) == "real final problem"

    def test_falls_back_to_the_last_warning_when_no_error_line_exists(self):
        engine = _engine()
        output = "WARNING: cookies stale\nWARNING: signature solving failed"
        assert (
            engine._extract_error_message(output)
            == "No explicit error, warnings: signature solving failed"
        )

    def test_falls_back_to_recent_output_when_no_error_or_warning_exists(self):
        engine = _engine()
        output = "line one\nline two\nline three"
        result = engine._extract_error_message(output)
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result

    def test_empty_output_reports_no_output_captured(self):
        engine = _engine()
        assert (
            engine._extract_error_message("")
            == "Unknown error occurred - no output captured"
        )
