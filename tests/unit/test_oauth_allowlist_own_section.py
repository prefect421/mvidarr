"""Regression test for #366: the OAuth new-account signup allowlist field
used to live inside #oauthProvidersSection, mixed in with the per-provider
(Authentik/Google/GitHub) config fields -- two distinct concerns (which
providers are enabled vs. who's allowed to sign up through them) sharing
one settings-section frame.

This confirms the allowlist now has its own settings-section, positioned
after (not inside) #oauthProvidersSection.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestOAuthAllowlistOwnSection:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_allowlist_field_is_outside_the_oauth_providers_section(self):
        providers_start = self.html.index('id="oauthProvidersSection"')
        providers_section_start = self.html.rindex("<div", 0, providers_start)
        # Find this section's closing </div> by matching the next sibling
        # settings-section opening tag, same convention as the rest of
        # this file's flat (non-nested) settings-section blocks.
        next_section = self.html.index(
            'class="settings-section"', providers_section_start + 10
        )
        providers_section_html = self.html[providers_section_start:next_section]

        assert 'name="oauth_allowed_emails"' not in providers_section_html, (
            "the allowlist field must not be inside #oauthProvidersSection "
            "-- it belongs in its own section"
        )

    def test_allowlist_has_its_own_settings_section_immediately_after(self):
        providers_start = self.html.index('id="oauthProvidersSection"')
        next_section = self.html.index(
            'class="settings-section"', providers_start
        )
        allowlist_section_end = self.html.index(
            'class="settings-section"', next_section + 10
        )
        allowlist_section_html = self.html[next_section:allowlist_section_end]

        assert 'name="oauth_allowed_emails"' in allowlist_section_html

    def test_allowlist_field_still_a_real_input(self):
        # Matches test_oauth_allowlist_ui.py's existing check -- settings.html's
        # generic save collector is querySelectorAll('input, select'), so a
        # <textarea> would silently never be saved.
        start = self.html.index('name="oauth_allowed_emails"')
        tag_start = self.html.rindex("<", 0, start)
        tag = self.html[tag_start : start + 40]
        assert tag.startswith("<input")
