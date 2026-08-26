"""Fix for #390: the global 401 interceptor's /auth/ substring match
incidentally excluded /api/lastfm/auth/url.

base.html's global 401 interceptor skipped its login-redirect handling
for any URL *containing* the substring "/auth/" -- meant to avoid
redirect loops on the app's own login/auth-flow endpoints (/auth/login,
etc). Phase 1's route-auth sweep added require_admin to GET
/api/lastfm/auth/url; its path happens to contain "/auth/" too (as a
path segment in the middle, not at the start), so a 401 from it fell
through the interceptor silently instead of prompting a login.

Fix: match on the URL's pathname with startsWith('/auth/') /
startsWith('/simple-auth/') instead of a bare substring check anywhere
in the (possibly relative, possibly absolute) URL string. Resolving via
`new URL(url, window.location.origin)` first handles both cases --
Request.url is always absolute per the Fetch API spec, but a plain
string passed straight to fetch() stays relative.

Static-content-assertion test, matching the pattern already established
for this app's other template regression tests -- no JS test runner in
this repo, and the logic is short and mechanical enough that reading it
verifies correctness directly.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestGlobal401InterceptorAuthPathMatch:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "base.html").read_text()
        start = self.html.index("Global 401 interceptor")
        end = self.html.index("})();", start)
        self.interceptor = self.html[start:end]

    def test_no_longer_uses_a_bare_substring_match_on_auth(self):
        # The exact bug: url.includes('/auth/') matches ANY path
        # containing that substring, not just paths that start with it.
        # Checked as the real conditional expression -- not a bare
        # substring search for "url.includes('/auth/')" -- since the fix's
        # own explanatory comment legitimately quotes the old pattern to
        # document what it replaced.
        assert "if (!url.includes('/auth/')" not in self.interceptor
        assert "url.includes('/simple-auth/')" not in self.interceptor

    def test_uses_pathname_prefix_matching_instead(self):
        assert "pathname.startsWith('/auth/')" in self.interceptor
        assert "pathname.startsWith('/simple-auth/')" in self.interceptor

    def test_resolves_to_an_absolute_url_before_extracting_pathname(self):
        # Handles both cases: `url` is relative when a plain string was
        # passed to fetch() directly (the common case in this app), but
        # Request.url is always absolute per the Fetch API spec when a
        # Request object was passed instead.
        assert "new URL(url, window.location.origin)" in self.interceptor

    def test_still_redirects_to_login_on_a_genuine_session_expiry(self):
        assert "window.location.href = '/auth/login'" in self.interceptor
