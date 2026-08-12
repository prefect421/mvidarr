"""Regression test: settings.html must expose oauth_allowed_emails as a
real, savable field — otherwise the allowlist backend added alongside it
has no way to be configured except direct DB/API access, the same class
of gap #336 existed for (see test_oauth_settings_ui.py).
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestOAuthAllowlistUI:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_allowlist_field_exists(self):
        assert 'name="oauth_allowed_emails"' in self.html

    def test_allowlist_field_is_a_real_input_not_a_textarea(self):
        """settings.html's generic save collector is
        querySelectorAll('input, select') — a <textarea> here would
        silently never be saved."""
        start = self.html.index('name="oauth_allowed_emails"')
        tag_start = self.html.rindex("<", 0, start)
        tag = self.html[tag_start : start + 40]
        assert tag.startswith("<input")
