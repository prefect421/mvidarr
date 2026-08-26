"""#317: EnhancedArtistDiscoveryService (1163 lines) had zero test
coverage. It has a rich set of genuinely pure, self-contained helpers
that directly decide artist-matching/dedup correctness -- whether two
artist entries get silently merged, flagged for review, or left as
distinct rows. A bug here doesn't crash anything; it just quietly
pollutes the user's library with duplicates, or (the opposite failure)
merges two genuinely different artists. Covers _normalize_artist_name,
_calculate_name_similarity, _calculate_genre_similarity,
_calculate_quality_score, _calculate_artist_similarity,
_extract_country_from_text, _deduplicate_recommendations,
_rank_and_score_discoveries, and _merge_artist_metadata.

Found two real things while writing these -- one fixed, one documented:

- FIXED (unambiguous bug): _merge_artist_metadata() did
  `max(d.quality_score for d in discoveries)`, but MetadataQuality was
  a plain Enum -- its members don't support `<`/`>` at all, so this
  raised TypeError on every real invocation with more than one
  discovery (i.e. every actual multi-source merge, the whole point of
  this "multi-source discovery" service). Changed MetadataQuality to
  IntEnum.

- DOCUMENTED, not changed (a design decision, not a clear-cut bug):
  _calculate_name_similarity's "character-based similarity" is a
  *positional* zip() comparison, not edit-distance -- a single inserted
  or deleted leading character collapses the score to ~0.0 even for
  near-identical names. And _calculate_artist_similarity weights name
  at only 60% of the total score, with genre/year/country each
  contributing only when *both* artists have that field populated --
  so two artists with an identical name but no other metadata can never
  cross the 0.8 "review" threshold. See the tests below for both.
"""

from types import SimpleNamespace

from src.services.enhanced_artist_discovery_service import (
    ArtistMetadata,
    DiscoverySource,
    EnhancedArtistDiscoveryService,
)


def _service():
    # Bypass __init__() (constructs real SpotifyService/LastFmService
    # instances) -- none of the methods under test touch self at all.
    return EnhancedArtistDiscoveryService.__new__(EnhancedArtistDiscoveryService)


def _metadata(**overrides):
    defaults = dict(
        name="Test Artist",
        source=DiscoverySource.MANUAL,
        confidence=0.8,
    )
    defaults.update(overrides)
    return ArtistMetadata(**defaults)


def _artist(**overrides):
    defaults = dict(
        id=1,
        name="Test Artist",
        genres=None,
        formed_year=None,
        country=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestNormalizeArtistName:
    def test_lowercases_and_strips_whitespace(self):
        assert _service()._normalize_artist_name("  Ghost  ") == "ghost"

    def test_strips_a_leading_the_prefix(self):
        assert _service()._normalize_artist_name("The Beatles") == "beatles"

    def test_strips_a_leading_a_prefix(self):
        assert _service()._normalize_artist_name("A Perfect Circle") == "perfect circle"

    def test_does_not_strip_a_word_that_merely_starts_with_the_prefix_letters(self):
        # "Alabama" starts with "a" but not the "a " (with trailing
        # space) prefix -- must not be mangled into "labama".
        assert _service()._normalize_artist_name("Alabama") == "alabama"

    def test_removes_special_characters_but_keeps_spaces(self):
        assert _service()._normalize_artist_name("Ke$ha!") == "keha"
        assert _service()._normalize_artist_name("Sum 41") == "sum 41"

    def test_empty_string_returns_empty_string(self):
        assert _service()._normalize_artist_name("") == ""

    def test_none_returns_empty_string(self):
        assert _service()._normalize_artist_name(None) == ""


class TestCalculateNameSimilarity:
    def test_identical_names_score_1(self):
        assert _service()._calculate_name_similarity("Ghost", "Ghost") == 1.0

    def test_identical_after_normalization_scores_1(self):
        # "The Beatles" vs "beatles" -- same artist, different casing/prefix.
        assert _service()._calculate_name_similarity("The Beatles", "beatles") == 1.0

    def test_empty_name_scores_0(self):
        assert _service()._calculate_name_similarity("", "Ghost") == 0.0
        assert _service()._calculate_name_similarity("Ghost", "") == 0.0

    def test_completely_different_names_score_low(self):
        score = _service()._calculate_name_similarity("Ghost", "Metallica")
        assert score < 0.3

    def test_a_single_leading_character_insertion_collapses_the_score_despite_near_identical_names(
        self,
    ):
        # Documents a real weakness: the "character-based similarity" is
        # a *positional* zip() comparison (matching char N of name1
        # against char N of name2), not edit-distance. A single leading
        # insertion shifts every later character out of alignment, so
        # two names differing by one character in the wrong place score
        # as if they were unrelated.
        score = _service()._calculate_name_similarity("Blur", "XBlur")
        assert score == 0.0

    def test_trailing_extra_characters_score_high_since_positions_still_align(self):
        # The inverse case: a suffix difference doesn't break positional
        # alignment, so this scores much higher than the leading-insertion
        # case above -- same edit distance (1 character), very different
        # score, purely because of *where* the difference falls.
        score = _service()._calculate_name_similarity("Ghost", "Ghosts")
        assert score > 0.8


class TestCalculateGenreSimilarity:
    def test_identical_genre_sets_score_1(self):
        score = _service()._calculate_genre_similarity("rock,metal", "rock,metal")
        assert score == 1.0

    def test_disjoint_genre_sets_score_0(self):
        score = _service()._calculate_genre_similarity("rock", "jazz")
        assert score == 0.0

    def test_partial_overlap_is_jaccard_similarity(self):
        # {rock, metal, doom} vs {rock, metal, pop} -> intersection 2, union 4
        score = _service()._calculate_genre_similarity(
            "rock,metal,doom", "rock,metal,pop"
        )
        assert score == 0.5

    def test_case_and_whitespace_insensitive(self):
        score = _service()._calculate_genre_similarity(" Rock , METAL", "rock,metal ")
        assert score == 1.0

    def test_empty_genre_string_scores_0(self):
        assert _service()._calculate_genre_similarity("", "rock") == 0.0
        assert _service()._calculate_genre_similarity("rock", "") == 0.0


class TestCalculateQualityScore:
    def test_bare_minimum_metadata_scores_low(self):
        metadata = _metadata(genres=[], biography="", image_url="", country="")
        score = _service()._calculate_quality_score(metadata)
        # Only the required "name" field contributes: 2.0 / 10.0
        assert score == 0.2

    def test_fully_populated_metadata_scores_near_the_maximum(self):
        metadata = _metadata(
            genres=["rock", "metal"],
            biography="x" * 60,
            image_url="https://example.com/art.jpg",
            external_ids={"spotify_id": "abc"},
            popularity_score=0.9,
            formed_year=2010,
            country="Sweden",
        )
        score = _service()._calculate_quality_score(metadata)
        # 2.0 name + 2.0 genres + 1.5 bio + 1.0 image + 1.5 ext_ids
        # + 1.0 popularity + 0.5 year + 0.5 country = 10.0 / 10.0
        assert score == 1.0

    def test_short_biography_does_not_count(self):
        short_bio_score = _service()._calculate_quality_score(
            _metadata(biography="short")
        )
        no_bio_score = _service()._calculate_quality_score(_metadata(biography=""))
        assert short_bio_score == no_bio_score

    def test_popularity_at_or_below_threshold_does_not_count(self):
        at_threshold = _service()._calculate_quality_score(
            _metadata(popularity_score=0.5)
        )
        above_threshold = _service()._calculate_quality_score(
            _metadata(popularity_score=0.51)
        )
        assert above_threshold > at_threshold


class TestExtractCountryFromText:
    def test_finds_a_known_country_mentioned_in_text(self):
        text = "The band was formed in Sweden in 2006."
        assert _service()._extract_country_from_text(text) == "Sweden"

    def test_is_case_insensitive(self):
        text = "formed in GERMANY"
        assert _service()._extract_country_from_text(text) == "Germany"

    def test_returns_none_when_no_known_country_is_mentioned(self):
        assert _service()._extract_country_from_text("A great band.") is None

    def test_empty_text_returns_none(self):
        assert _service()._extract_country_from_text("") is None

    def test_when_multiple_countries_are_mentioned_the_first_list_entry_wins_not_the_first_text_occurrence(
        self,
    ):
        # "United States" precedes "United Kingdom" in the internal
        # country list, so it wins here even though "United Kingdom"
        # appears first in the actual text -- documents current
        # (list-order, not text-order) behavior.
        text = "Formed in United Kingdom, later relocated to United States."
        assert _service()._extract_country_from_text(text) == "United States"


class TestDeduplicateRecommendations:
    def test_removes_recommendations_with_the_same_normalized_name(self):
        recs = [
            _metadata(name="Ghost"),
            _metadata(name="ghost"),
            _metadata(name="The Ghost"),
        ]
        result = _service()._deduplicate_recommendations(recs)
        assert len(result) == 1

    def test_keeps_the_first_occurrence_of_a_duplicate(self):
        first = _metadata(name="Ghost", confidence=0.9)
        second = _metadata(name="Ghost", confidence=0.1)
        result = _service()._deduplicate_recommendations([first, second])
        assert result == [first]

    def test_distinct_names_are_all_kept(self):
        recs = [_metadata(name="Ghost"), _metadata(name="Metallica")]
        result = _service()._deduplicate_recommendations(recs)
        assert len(result) == 2

    def test_empty_list_returns_empty_list(self):
        assert _service()._deduplicate_recommendations([]) == []


class TestRankAndScoreDiscoveries:
    def test_sorts_by_adjusted_confidence_descending(self):
        low = _metadata(name="Low", confidence=0.5, genres=[])  # weak quality score
        high = _metadata(
            name="High",
            confidence=0.5,
            genres=["rock"],
            biography="x" * 60,
            image_url="https://x.test/a.jpg",
            external_ids={"id": "1"},
            popularity_score=0.9,
            formed_year=2000,
            country="Sweden",
        )
        result = _service()._rank_and_score_discoveries([low, high])
        assert result[0] is high
        assert result[1] is low

    def test_confidence_is_capped_at_1(self):
        metadata = _metadata(
            confidence=1.0,
            genres=["rock"],
            biography="x" * 60,
            image_url="https://x.test/a.jpg",
            external_ids={"id": "1"},
            popularity_score=0.9,
            formed_year=2000,
            country="Sweden",
        )
        result = _service()._rank_and_score_discoveries([metadata])
        assert result[0].confidence <= 1.0


class TestMergeArtistMetadata:
    def test_empty_list_returns_none(self):
        assert _service()._merge_artist_metadata([]) is None

    def test_single_discovery_is_returned_unchanged(self):
        only = _metadata(name="Ghost")
        assert _service()._merge_artist_metadata([only]) is only

    def test_uses_the_highest_confidence_discovery_as_the_name_source(self):
        low = _metadata(name="ghst (typo)", confidence=0.3)
        high = _metadata(name="Ghost", confidence=0.9)
        merged = _service()._merge_artist_metadata([low, high])
        assert merged.name == "Ghost"

    def test_merges_genres_from_all_sources(self):
        a = _metadata(genres=["rock"], confidence=0.5)
        b = _metadata(genres=["metal", "doom"], confidence=0.5)
        merged = _service()._merge_artist_metadata([a, b])
        assert set(merged.genres) == {"rock", "metal", "doom"}

    def test_merges_external_ids_from_all_sources(self):
        a = _metadata(external_ids={"spotify_id": "abc"}, confidence=0.5)
        b = _metadata(external_ids={"lastfm_id": "xyz"}, confidence=0.5)
        merged = _service()._merge_artist_metadata([a, b])
        assert merged.external_ids == {"spotify_id": "abc", "lastfm_id": "xyz"}

    def test_uses_the_longest_available_biography(self):
        a = _metadata(biography="short", confidence=0.5)
        b = _metadata(biography="a much longer biography text here", confidence=0.5)
        merged = _service()._merge_artist_metadata([a, b])
        assert merged.biography == "a much longer biography text here"

    def test_uses_the_first_available_image_when_the_base_has_none(self):
        a = _metadata(confidence=0.9, image_url="")
        b = _metadata(confidence=0.1, image_url="https://x.test/img.jpg")
        merged = _service()._merge_artist_metadata([a, b])
        assert merged.image_url == "https://x.test/img.jpg"

    def test_merged_confidence_is_capped_at_1(self):
        a = _metadata(confidence=1.0)
        b = _metadata(confidence=1.0)
        merged = _service()._merge_artist_metadata([a, b])
        assert merged.confidence <= 1.0


class TestCalculateArtistSimilarity:
    def test_identical_name_alone_is_flagged_as_a_similar_name_but_not_enough_to_merge(
        self,
    ):
        # Real limitation found while writing this test, documented
        # rather than silently "fixed" (a scoring-weight change is a
        # design decision, not an unambiguous bug like the MetadataQuality
        # crash above): name similarity is capped at 0.6 of the total
        # score (`name_sim * 0.6`), and genre/year/country each only
        # contribute when *both* artists have that field populated. Two
        # artists with an exactly identical name but no other metadata
        # at all -- a realistic case for artists added with sparse data
        # -- can never exceed 0.6 total, below even the 0.8 "review"
        # threshold. Duplicate detection is structurally blind to
        # exact-name duplicates when no other metadata is present.
        a = _artist(id=1, name="Ghost")
        b = _artist(id=2, name="Ghost")
        result = _service()._calculate_artist_similarity(a, b)
        assert "similar_name" in result.matching_factors
        assert result.suggested_action == "ignore"
        assert result.similarity_score == 0.6

    def test_identical_name_plus_matching_genre_crosses_the_review_threshold(self):
        # With a second corroborating signal, the same identical-name
        # pair above correctly reaches "review" (0.6 name + up to 0.2
        # genre = up to 0.8) -- the algorithm works when enough
        # metadata is actually present.
        a = _artist(id=1, name="Ghost", genres="rock,metal")
        b = _artist(id=2, name="Ghost", genres="rock,metal")
        result = _service()._calculate_artist_similarity(a, b)
        assert result.suggested_action in ("review", "merge")

    def test_completely_different_artists_suggest_ignore(self):
        a = _artist(id=1, name="Ghost")
        b = _artist(id=2, name="Metallica")
        result = _service()._calculate_artist_similarity(a, b)
        assert result.suggested_action == "ignore"

    def test_matching_genre_adds_a_matching_factor(self):
        a = _artist(id=1, name="Ghost", genres="rock,metal")
        b = _artist(id=2, name="Ghost Clone", genres="rock,metal")
        result = _service()._calculate_artist_similarity(a, b)
        assert "similar_genres" in result.matching_factors

    def test_same_country_adds_a_matching_factor(self):
        a = _artist(id=1, name="Artist One", country="Sweden")
        b = _artist(id=2, name="Artist Two", country="sweden")
        result = _service()._calculate_artist_similarity(a, b)
        assert "same_country" in result.matching_factors

    def test_result_references_the_original_artist_ids(self):
        a = _artist(id=42, name="Ghost")
        b = _artist(id=99, name="Ghost")
        result = _service()._calculate_artist_similarity(a, b)
        assert result.artist_id == 42
        assert result.candidate_id == 99
