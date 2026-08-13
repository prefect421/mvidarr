"""Regression/feature test for #316: 'Recently Found' one-click view on
the Videos page (re-scoped from an 'upcoming release calendar' — no
integrated data source exposes reliable future release dates; see
docs/superpowers/specs/2026-08-13-recently-found-videos-design.md).

Static-content-assertion approach, matching the pattern already
established for this page's other template regression tests (e.g.
test_oauth_settings_ui.py): confirms the button exists and wires to
showRecentlyFound(), that showRecentlyFound() sets the three expected
filter values and calls applyVideoFilters(), and that the page's load
sequence reads sort_by/sort_order/status from the URL before the first
render so the pushed URL is a real, reproducible deep link.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestRecentlyFoundButton:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "videos.html").read_text()

    def test_button_exists_and_calls_show_recently_found(self):
        assert 'onclick="showRecentlyFound()"' in self.html

    def test_button_is_in_the_filter_actions_bar(self):
        start = self.html.index('class="filter-actions"')
        end = self.html.index("</div>", start)
        actions_bar = self.html[start:end]
        assert 'onclick="showRecentlyFound()"' in actions_bar

    def test_show_recently_found_function_exists(self):
        assert "function showRecentlyFound()" in self.html

    def test_show_recently_found_sets_expected_filter_values(self):
        start = self.html.index("function showRecentlyFound()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "getElementById('videoStatusFilter').value = ''" in body
        assert "getElementById('videoSortBy').value = 'date_added'" in body
        assert "getElementById('videoSortOrder').value = 'desc'" in body

    def test_show_recently_found_pushes_a_shareable_url(self):
        start = self.html.index("function showRecentlyFound()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "history.pushState(" in body
        assert "/videos?sort_by=date_added&sort_order=desc&status=" in body

    def test_show_recently_found_calls_apply_video_filters(self):
        start = self.html.index("function showRecentlyFound()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "applyVideoFilters()" in body
