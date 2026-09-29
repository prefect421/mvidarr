"""
Focused tests for MusicRecommendationService's IMVDb -> MusicBrainz migration
(Task 1a of the IMVDb removal plan, GitHub issue #524).

_get_similar_artist_recommendations()'s Spotify branch is the one call site
in this file with a known artist+track pair, so it's the only one migrated
to musicbrainz_service.find_official_video(); the other IMVDb touchpoints
(trending, genre-based, user-based, new-releases) were all bulk artist- or
genre-level discovery with no MusicBrainz equivalent and now return [].
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.music_recommendations import (
    MusicRecommendationService,
    RecommendationType,
)


@pytest.mark.asyncio
class TestSimilarArtistRecommendationsMusicBrainz:
    async def test_spotify_track_resolved_via_musicbrainz(self):
        service = MusicRecommendationService()
        spotify_recs = {
            "tracks": [
                {
                    "id": "track1",
                    "name": "Rats",
                    "artists": [{"name": "Ghost"}],
                    "popularity": 80,
                }
            ]
        }
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }

        spotify_mock = MagicMock()
        spotify_mock.get_recommendations.return_value = spotify_recs

        with patch(
            "src.services.music_recommendations.get_spotify_service",
            new=AsyncMock(return_value=spotify_mock),
        ), patch(
            "src.services.music_recommendations.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find:
            recs = await service._get_similar_artist_recommendations("Ghost", 10)

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert len(recs) == 1
        assert recs[0].video_url == "https://www.youtube.com/watch?v=abc123"
        assert recs[0].artist_name == "Ghost"
        assert recs[0].recommendation_type == RecommendationType.SIMILAR_ARTISTS

    async def test_spotify_track_with_no_musicbrainz_match_is_skipped(self):
        service = MusicRecommendationService()
        spotify_recs = {
            "tracks": [
                {
                    "id": "track1",
                    "name": "Unknown Song",
                    "artists": [{"name": "Unknown Artist"}],
                    "popularity": 10,
                }
            ]
        }

        spotify_mock = MagicMock()
        spotify_mock.get_recommendations.return_value = spotify_recs

        with patch(
            "src.services.music_recommendations.get_spotify_service",
            new=AsyncMock(return_value=spotify_mock),
        ), patch(
            "src.services.music_recommendations.musicbrainz_service.find_official_video",
            return_value=None,
        ):
            recs = await service._get_similar_artist_recommendations(
                "Unknown Artist", 10
            )

        assert recs == []


@pytest.mark.asyncio
class TestGuttedImvdbOnlyRecommendationTypes:
    """These had no MusicBrainz equivalent (bulk/genre-level discovery
    without a specific track) and now always return an empty list."""

    async def test_trending_returns_empty(self):
        service = MusicRecommendationService()
        assert await service._get_trending_video_recommendations(10) == []

    async def test_genre_based_returns_empty(self):
        service = MusicRecommendationService()
        assert await service._get_genre_based_recommendations("rock", 10) == []

    async def test_user_based_returns_empty(self):
        service = MusicRecommendationService()
        assert await service._get_user_based_recommendations("user1", 10) == []

    async def test_new_release_returns_empty(self):
        service = MusicRecommendationService()
        assert await service._get_new_release_recommendations(10) == []
