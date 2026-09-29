"""
Focused test for the IMVDb -> MusicBrainz migration of
src/api/fastapi/music_recommendations.py (Phase 2 of the IMVDb removal
plan, GitHub issue #525) -- distinct from the src/services/ file of the
same name, already migrated in #524.

generate_custom_spotify_recommendations() looked up a music video for each
Spotify-recommended track via imvdb_service.search_videos(artist, track).
MusicBrainzService.find_official_video() only returns a video URL (no
thumbnail), matching the precedent already set for this exact
artist+track lookup pattern in src/services/music_recommendations.py
during #524.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.fastapi.music_recommendations import (
    SpotifyRecommendationRequest,
    generate_custom_spotify_recommendations,
)


class TestCustomSpotifyRecommendationsMusicBrainzLookup:
    @pytest.mark.asyncio
    async def test_musicbrainz_match_sets_video_url_no_thumbnail(self):
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
        video_match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
        }

        with patch(
            "src.api.fastapi.music_recommendations.spotify_service.get_recommendations",
            return_value=spotify_recs,
        ), patch(
            "src.api.fastapi.music_recommendations.musicbrainz_service.find_official_video",
            return_value=video_match,
        ) as mock_find, patch(
            "src.api.fastapi.music_recommendations.get_music_recommendation_service",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ), patch(
            "src.api.fastapi.music_recommendations.track_media_processing_time",
            new_callable=AsyncMock,
        ):
            result = await generate_custom_spotify_recommendations(
                SpotifyRecommendationRequest(seed_artists=["Ghost"])
            )

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert result.success is True
        assert result.sources_used == ["spotify", "musicbrainz"]
        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec["video_url"] == "https://www.youtube.com/watch?v=abc123"
        assert rec["video_id"] == "aaaa-bbbb"
        assert rec["thumbnail_url"] is None
