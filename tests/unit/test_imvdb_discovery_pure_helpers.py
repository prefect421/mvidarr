"""#317: IMVDbDiscoveryService (655 lines) had zero test coverage. Most
of the file is DB/network-heavy (session queries, live IMVDb API calls
via imvdb_service), but it has two small, genuinely pure helpers worth
covering directly: _extract_thumbnail_url() (picks the best available
image size from IMVDb's nested image dict) and
_calculate_similarity_score() (used when ranking IMVDb artist search
results).

IMVDbDiscoveryService.__init__() does only simple attribute assignment
(no real I/O), so it's safe to construct directly -- no __new__ bypass
needed here, unlike the other #317 slices.
"""

from src.services.imvdb_discovery_service import IMVDbDiscoveryService


def _service():
    return IMVDbDiscoveryService()


class TestExtractThumbnailUrl:
    def test_prefers_the_original_size_when_available(self):
        video_data = {"image": {"o": "orig.jpg", "l": "large.jpg", "s": "small.jpg"}}
        assert _service()._extract_thumbnail_url(video_data) == "orig.jpg"

    def test_falls_back_through_sizes_in_priority_order(self):
        # No "o" (original) -- next preferred is "l" (large).
        video_data = {"image": {"l": "large.jpg", "s": "small.jpg"}}
        assert _service()._extract_thumbnail_url(video_data) == "large.jpg"

    def test_skips_falsy_values_for_a_higher_priority_size(self):
        # "o" key present but empty -- must not short-circuit on mere
        # key presence, only on a genuinely truthy value.
        video_data = {"image": {"o": "", "l": "large.jpg"}}
        assert _service()._extract_thumbnail_url(video_data) == "large.jpg"

    def test_falls_back_to_top_level_image_url_when_no_image_dict(self):
        video_data = {"image_url": "https://example.com/fallback.jpg"}
        assert (
            _service()._extract_thumbnail_url(video_data)
            == "https://example.com/fallback.jpg"
        )

    def test_falls_back_to_top_level_image_url_when_image_is_not_a_dict(self):
        video_data = {"image": "not-a-dict", "image_url": "fallback.jpg"}
        assert _service()._extract_thumbnail_url(video_data) == "fallback.jpg"

    def test_returns_none_when_nothing_is_available(self):
        assert _service()._extract_thumbnail_url({}) is None


class TestCalculateSimilarityScore:
    def test_base_score_with_no_id_or_slug(self):
        score = _service()._calculate_similarity_score({"name": "Ghost"}, set())
        assert score == 1.0

    def test_id_present_adds_a_bonus(self):
        score = _service()._calculate_similarity_score(
            {"name": "Ghost", "id": 123}, set()
        )
        assert score == 1.5

    def test_slug_present_adds_a_bonus(self):
        score = _service()._calculate_similarity_score(
            {"name": "Ghost", "slug": "ghost"}, set()
        )
        assert round(score, 2) == 1.3

    def test_id_and_slug_both_present_stack(self):
        score = _service()._calculate_similarity_score(
            {"name": "Ghost", "id": 123, "slug": "ghost"}, set()
        )
        assert round(score, 2) == 1.8

    def test_reference_genres_argument_is_currently_unused(self):
        # Genuinely a stub, not a bug: the docstring says "simplified...
        # for now" and reference_genres never appears in the method
        # body. Passing different genre sets makes no difference to the
        # score -- pinned down so a future implementation that starts
        # using it is a deliberate change, not an accidental no-op fix.
        artist_data = {"name": "Ghost", "id": 123}
        score_a = _service()._calculate_similarity_score(artist_data, {"rock"})
        score_b = _service()._calculate_similarity_score(
            artist_data, {"completely", "different", "genres"}
        )
        assert score_a == score_b
