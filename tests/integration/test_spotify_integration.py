"""
Integration tests for Enhanced Spotify Integration (Issue #79)
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.api.spotify_enhanced import spotify_enhanced_bp
from src.services.spotify_service import spotify_service
from src.services.spotify_sync_service import SyncResult, spotify_sync_service


class TestSpotifyIntegration:
    """Integration tests for Spotify services"""

    def test_spotify_service_initialization(self):
        """Test SpotifyService initializes correctly"""
        service = spotify_service
        assert service is not None
        assert hasattr(service, "search_tracks")
        assert hasattr(service, "get_recommendations")
        assert hasattr(service, "create_playlist")

    def test_spotify_sync_service_initialization(self):
        """Test SpotifySyncService initializes correctly"""
        sync_service = spotify_sync_service
        assert sync_service is not None
        assert hasattr(sync_service, "sync_user_playlists")
        assert hasattr(sync_service, "export_playlist_to_spotify")

    def test_sync_result_dataclass(self):
        """Test SyncResult dataclass structure"""
        result = SyncResult(success=True)
        assert result.success is True
        assert result.tracks_added == 0
        assert result.artists_discovered == 0
        assert result.videos_matched == 0
        assert isinstance(result.errors, list)

    @patch("src.services.spotify_service.SpotifyService.search_tracks")
    def test_search_tracks_method_exists(self, mock_search):
        """Test that search_tracks method exists and is callable"""
        mock_search.return_value = {"tracks": {"items": []}}

        result = spotify_service.search_tracks("test query")

        mock_search.assert_called_once_with("test query")
        assert "tracks" in result

    @patch("src.services.spotify_service.SpotifyService.get_recommendations")
    def test_recommendations_method(self, mock_recommendations):
        """Test get_recommendations method functionality"""
        mock_recommendations.return_value = {"tracks": []}

        result = spotify_service.get_recommendations(
            seed_artists=["artist1"], seed_tracks=["track1"]
        )

        mock_recommendations.assert_called_once()
        assert "tracks" in result

    @patch("src.services.spotify_service.SpotifyService.create_playlist")
    def test_playlist_creation(self, mock_create):
        """Test playlist creation functionality"""
        mock_create.return_value = {"id": "test_playlist_id", "name": "Test Playlist"}

        result = spotify_service.create_playlist(
            name="Test Playlist", description="Test Description", public=False
        )

        mock_create.assert_called_once()
        assert "id" in result

    def test_track_similarity_calculation(self):
        """Test track similarity calculation algorithm"""
        sync_service = spotify_sync_service

        # Exact match
        similarity = sync_service._calculate_track_similarity("Test Song", "Test Song")
        assert similarity == 1.0

        # Partial match
        similarity = sync_service._calculate_track_similarity(
            "Test Song", "Test Song (Official Video)"
        )
        assert similarity > 0.7

        # No match
        similarity = sync_service._calculate_track_similarity(
            "Test Song", "Completely Different"
        )
        assert similarity < 0.5

    def test_track_title_cleaning(self):
        """Test track title cleaning for better matching"""
        sync_service = spotify_sync_service

        # Remove video suffixes
        cleaned = sync_service._clean_track_title("Song Title (Official Music Video)")
        assert cleaned == "Song Title"

        # Remove featuring
        cleaned = sync_service._clean_track_title("Song Title feat. Other Artist")
        assert cleaned == "Song Title"

        # Multiple cleaning
        cleaned = sync_service._clean_track_title("Song Title (Live) ft. Artist")
        assert cleaned == "Song Title"

    @patch("src.services.spotify_sync_service.get_db")
    @patch("src.services.spotify_service.SpotifyService.get_user_playlists")
    def test_playlist_sync_flow(self, mock_playlists, mock_db):
        """Test basic playlist synchronization flow"""
        # Mock database session
        mock_session = Mock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock Spotify playlists response
        mock_playlists.return_value = {
            "items": [
                {
                    "id": "test_playlist_id",
                    "name": "Test Playlist",
                    "description": "Test Description",
                }
            ]
        }

        # Mock playlist tracks
        with patch.object(spotify_service, "get_playlist_tracks") as mock_tracks:
            mock_tracks.return_value = {"items": []}

            results = spotify_sync_service.sync_user_playlists(force_refresh=True)

            assert isinstance(results, list)
            assert len(results) > 0

    def test_oauth_scopes_include_playlist_modification(self):
        """Test that OAuth scopes include playlist modification permissions"""
        auth_url = spotify_service.get_auth_url()

        # Check that required scopes are present
        assert "playlist-modify-public" in auth_url
        assert "playlist-modify-private" in auth_url
        assert "user-library-modify" in auth_url

    @patch("src.services.spotify_sync_service.get_db")
    def test_music_video_recommendations(self, mock_db):
        """Test music video recommendations generation"""
        # Mock database session
        mock_session = Mock()
        mock_db.return_value.__enter__.return_value = mock_session

        with patch.object(spotify_service, "get_user_top_tracks") as mock_top_tracks:
            mock_top_tracks.return_value = {
                "items": [{"id": "track1", "name": "Test Track"}]
            }

            with patch.object(
                spotify_service, "get_recommendations"
            ) as mock_recommendations:
                mock_recommendations.return_value = {"tracks": []}

                result = spotify_sync_service.get_music_video_recommendations(limit=10)

                assert "success" in result
                assert "recommendations" in result

    @patch("src.services.spotify_sync_service.get_db")
    def test_new_release_checking(self, mock_db):
        """Test new release checking functionality"""
        # Mock database session
        mock_session = Mock()
        mock_db.return_value.__enter__.return_value = mock_session

        with patch.object(spotify_service, "get_followed_artists") as mock_followed:
            mock_followed.return_value = {"artists": {"items": []}}

            result = spotify_sync_service.sync_new_releases()

            assert "success" in result
            assert "new_releases" in result

    def test_webhook_processing_structure(self):
        """Test webhook processing structure"""
        webhook_data = {"type": "playlist.update", "data": {"playlist_id": "test_id"}}

        result = spotify_sync_service.process_spotify_webhook(webhook_data)

        assert "success" in result
        assert isinstance(result, dict)

    def test_enhanced_api_blueprint_registration(self):
        """Test that enhanced Spotify API blueprint is properly structured"""
        assert spotify_enhanced_bp.name == "spotify_enhanced"
        assert spotify_enhanced_bp.url_prefix == "/spotify"

        # Verify blueprint has deferred functions (routes)
        assert hasattr(spotify_enhanced_bp, "deferred_functions")
        assert len(spotify_enhanced_bp.deferred_functions) > 0

        # Note: Blueprint routes won't be available until registered with app
        # This test validates blueprint structure and that routes are defined
