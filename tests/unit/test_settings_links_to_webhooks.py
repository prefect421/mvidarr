"""Regression/feature test for #315: Settings page must link to the
webhooks/notifications page -- before this, nothing anywhere linked to
it (confirmed by grep across frontend/templates/*.html), so it was
undiscoverable even after Task 6 made it technically reachable by URL.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestSettingsLinksToWebhooks:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_settings_page_links_to_the_webhooks_page(self):
        assert "/webhooks" in self.html

    def test_the_link_is_a_sidebar_nav_button_styled_like_its_siblings(self):
        start = self.html.index('class="sidebar-nav">')
        end = self.html.index("</ul>", start)
        nav_html = self.html[start:end]
        assert "/webhooks" in nav_html
        assert "settings-tab-btn" in nav_html
