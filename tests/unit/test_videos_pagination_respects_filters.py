"""Regression test for #357: Videos page pagination (Next/Prev/goToPage/
page-size) silently dropped any active filter or sort, because those
controls all called loadVideos(...) -- a completely separate fetch to
/api/videos with hardcoded sort:'title', order:'asc' and no filter
params at all -- instead of the filter-aware applyVideoFilters(), which
fetches /api/videos/search with the real filter state but never sent
limit/offset in the first place.

Result: apply any filter (e.g. #316's "Recently Found" button) and click
Next, and you silently land on an unfiltered, alphabetically-sorted
page 2.

Fix: applyVideoFilters() now accepts (page, resetPage), sends limit/
offset derived from currentPage/pageSize, and sets the previously-dead
`searchActive` flag (declared but never read before this fix -- only
ever set to false in clearAllVideoFilters()). The four pagination
control functions now check searchActive and route through
applyVideoFilters() instead of loadVideos() whenever a filtered view is
active.

Matches the static-content-assertion approach already established this
session for template changes.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestVideosPaginationRespectsFilters:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "videos.html").read_text()

    def _function_body(self, signature_prefix):
        start = self.html.index(signature_prefix)
        end = self.html.index("\n}", start)
        return self.html[start:end]

    def test_apply_video_filters_marks_search_active(self):
        body = self._function_body("function applyVideoFilters(")
        assert "searchActive = true" in body

    def test_apply_video_filters_sends_limit_and_offset(self):
        body = self._function_body("function applyVideoFilters(")
        assert "params.append('limit'" in body or 'params.append("limit"' in body
        assert "params.append('offset'" in body or 'params.append("offset"' in body

    def test_apply_video_filters_accepts_a_page_argument(self):
        # Pagination controls need to request a specific page without
        # resetting back to page 1.
        assert (
            "function applyVideoFilters(page = 1, resetPage = true)" in self.html
        )

    def test_next_page_routes_through_apply_video_filters_when_search_active(self):
        body = self._function_body("function nextPage(")
        assert "searchActive" in body
        assert "applyVideoFilters(" in body
        assert "loadVideos(" in body  # still the fallback for the unfiltered case

    def test_previous_page_routes_through_apply_video_filters_when_search_active(self):
        body = self._function_body("function previousPage(")
        assert "searchActive" in body
        assert "applyVideoFilters(" in body
        assert "loadVideos(" in body

    def test_go_to_page_routes_through_apply_video_filters_when_search_active(self):
        body = self._function_body("function goToPage(")
        assert "searchActive" in body
        assert "applyVideoFilters(" in body
        assert "loadVideos(" in body

    def test_change_page_size_routes_through_apply_video_filters_when_search_active(
        self,
    ):
        body = self._function_body("function changePageSize(")
        assert "searchActive" in body
        assert "applyVideoFilters(" in body
        assert "loadVideos(" in body

    def test_clear_all_filters_still_sets_search_active_false(self):
        # Pre-existing behavior (the only prior write to searchActive) --
        # must survive this fix so a cleared filter set correctly falls
        # back to plain loadVideos()-driven pagination again.
        body = self._function_body("function clearAllVideoFilters(")
        assert "searchActive = false" in body
