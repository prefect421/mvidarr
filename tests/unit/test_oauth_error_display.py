"""Regression test for #353: the login page must actually display the
oauth_error query param that auth.py's oauth_callback now redirects
failures to — the backend fix alone is silent without this.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestOAuthErrorDisplay:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "auth" / "login.html").read_text()

    def test_reads_the_oauth_error_query_param(self):
        assert "oauth_error" in self.html

    def test_displays_it_via_the_existing_error_element_not_innerhtml(self):
        # showError() uses .textContent — confirm the oauth_error
        # value is routed through it, not injected as raw HTML.
        assert "showError(oauthError)" in self.html
