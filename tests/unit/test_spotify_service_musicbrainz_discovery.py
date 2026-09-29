"""
Focused tests for SpotifyService.discover_music_videos_from_listening_history()'s
IMVDb -> MusicBrainz migration (Task 1a of the IMVDb removal plan, GitHub
issue #524).

The old implementation bulk-fetched an artist's entire IMVDb video catalog
and fuzzy-matched it against each top track (calculate_metadata_similarity/
enhanced_metadata_matching). The new implementation calls
musicbrainz_service.find_official_video(artist, track) directly per track,
since MusicBrainz's curated relationships already identify the exact video
for a track -- no fuzzy matching needed.
"""

from unittest.mock import MagicMock, patch

from src.database.models import Video
from src.services.spotify_service import SpotifyService


def _make_db(existing_video=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing_video
    return db


class TestDiscoverMusicVideosFromListeningHistoryMusicBrainz:
    def test_musicbrainz_match_becomes_high_confidence_discovery(self):
        service = SpotifyService()
        track = {
            "name": "Rats",
            "artists": [{"name": "Ghost"}],
        }
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }
        db = _make_db(existing_video=None)

        with patch.object(
            service, "get_user_top_tracks", return_value={"items": [track]}
        ), patch(
            "src.services.spotify_service.get_db",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=db),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.services.spotify_service.musicbrainz_service.find_official_video",
            return_value=match,
        ) as mock_find:
            result = service.discover_music_videos_from_listening_history()

        mock_find.assert_called_once_with("Ghost", "Rats")
        assert result["high_confidence_matches"] == 1
        assert result["potential_matches"] == 0
        assert len(result["discovered_videos"]) == 1
        discovered = result["discovered_videos"][0]
        assert discovered["confidence"] == "high"
        assert (
            discovered["video_data"]["url"] == "https://www.youtube.com/watch?v=abc123"
        )
        assert discovered["artist"] == "Ghost"

    def test_no_musicbrainz_match_yields_no_discovery(self):
        service = SpotifyService()
        track = {
            "name": "No Video Here",
            "artists": [{"name": "Unknown Artist"}],
        }
        db = _make_db(existing_video=None)

        with patch.object(
            service, "get_user_top_tracks", return_value={"items": [track]}
        ), patch(
            "src.services.spotify_service.get_db",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=db),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.services.spotify_service.musicbrainz_service.find_official_video",
            return_value=None,
        ):
            result = service.discover_music_videos_from_listening_history()

        assert result["discovered_videos"] == []
        assert result["high_confidence_matches"] == 0

    def test_existing_video_by_url_is_skipped(self):
        service = SpotifyService()
        track = {
            "name": "Rats",
            "artists": [{"name": "Ghost"}],
        }
        match = {
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "recording_id": "aaaa-bbbb",
            "recording_title": "Rats",
            "relationship_type": "music video",
            "score": 100,
        }
        db = _make_db(existing_video=Video(id=1, title="Rats"))

        with patch.object(
            service, "get_user_top_tracks", return_value={"items": [track]}
        ), patch(
            "src.services.spotify_service.get_db",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=db),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.services.spotify_service.musicbrainz_service.find_official_video",
            return_value=match,
        ):
            result = service.discover_music_videos_from_listening_history()

        assert result["discovered_videos"] == []
        assert result["high_confidence_matches"] == 0
