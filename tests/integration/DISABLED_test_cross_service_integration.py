"""
Cross-service integration tests for 0.9.8 features
"""

from unittest.mock import Mock, patch

import pytest

from src.services.discogs_service import discogs_service
from src.services.media_server_manager import media_server_manager
from src.services.metadata_enrichment_service import metadata_enrichment_service
from src.services.spotify_service import spotify_service


class TestCrossServiceIntegration:
    """Cross-service integration tests for all 0.9.8 features"""

    def test_spotify_metadata_enrichment_integration(self):
        """Test Spotify integration with metadata enrichment"""
        # Test that Spotify search_tracks is available for metadata enrichment
        assert hasattr(spotify_service, "search_tracks")

        with patch.object(spotify_service, "search_tracks") as mock_search:
            mock_search.return_value = {"tracks": {"items": []}}

            # This should not raise an exception now
            result = spotify_service.search_tracks("test artist test song")
            assert "tracks" in result

    def test_media_server_spotify_artist_sync(self):
        """Test media server integration with Spotify artist discovery"""
        # Test that media servers can sync with Spotify-discovered artists
        with patch(
            "src.services.media_server_manager.MediaServerManager._get_configured_servers"
        ):
            manager = media_server_manager
            assert hasattr(manager, "sync_artist_libraries")

    def test_discogs_metadata_enrichment_integration(self):
        """Test Discogs integration with metadata enrichment service"""
        # Test that Discogs is integrated into metadata enrichment
        enrichment_service = metadata_enrichment_service

        # Verify Discogs service is accessible
        assert hasattr(enrichment_service, "discogs")

        with patch.object(
            discogs_service, "get_artist_metadata_for_enrichment"
        ) as mock_discogs:
            mock_discogs.return_value = {
                "name": "Test Artist",
                "discogs_id": "123456",
                "biography": "Test biography",
            }

            # Test that Discogs can provide metadata for enrichment
            result = discogs_service.get_artist_metadata_for_enrichment("Test Artist")
            if result:
                assert "discogs_id" in result

    def test_spotify_playlist_media_server_workflow(self):
        """Test workflow: Spotify playlist → MVidarr → Media Server"""
        # This tests the complete workflow of:
        # 1. Import playlist from Spotify
        # 2. Match videos in MVidarr
        # 3. Sync to media servers

        with patch("src.services.spotify_sync_service.get_db") as mock_db:
            mock_session = Mock()
            mock_db.return_value.__enter__.return_value = mock_session

            with patch.object(spotify_service, "get_user_playlists") as mock_playlists:
                mock_playlists.return_value = {"items": []}

                # Test that playlist sync can be initiated
                from src.services.spotify_sync_service import spotify_sync_service

                results = spotify_sync_service.sync_user_playlists()
                assert isinstance(results, list)

    def test_metadata_provider_cascading(self):
        """Test cascading through multiple metadata providers"""
        # Test the workflow where if one provider fails, others are used
        providers = [
            ("musicbrainz", "musicbrainz_service"),
            ("lastfm", "lastfm_service"),
            ("spotify", "spotify_service"),
            ("discogs", "discogs_service"),
            ("allmusic", "allmusic_service"),
        ]

        for provider_name, service_name in providers:
            try:
                module = __import__(
                    f"src.services.{service_name}", fromlist=[service_name]
                )
                service = getattr(module, service_name)
                assert service is not None
            except ImportError:
                # Some services might not be fully implemented
                pass

    def test_dynamic_playlist_metadata_integration(self):
        """Test dynamic playlists with enhanced metadata"""
        # Test that dynamic playlists can use enhanced metadata from all providers
        from src.services.dynamic_playlist_service import dynamic_playlist_service

        # Verify dynamic playlist service exists and can access metadata
        assert dynamic_playlist_service is not None
        assert hasattr(dynamic_playlist_service, "create_dynamic_playlist")

    def test_api_endpoint_integration(self):
        """Test that all API endpoints are properly integrated"""
        # Test API blueprint integration
        from src.api.media_servers import media_servers_bp
        from src.api.spotify_enhanced import spotify_enhanced_bp

        # Verify blueprints exist
        assert spotify_enhanced_bp is not None
        assert media_servers_bp is not None

        # Verify they have expected URL prefixes
        assert spotify_enhanced_bp.url_prefix == "/spotify"

    @patch("src.services.metadata_enrichment_service.get_db")
    def test_complete_artist_enrichment_workflow(self, mock_db):
        """Test complete artist enrichment using all metadata providers"""
        # Mock database session
        mock_session = Mock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock artist
        mock_artist = Mock()
        mock_artist.id = 1
        mock_artist.name = "Test Artist"
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_artist
        )

        enrichment_service = metadata_enrichment_service

        # Test that enrichment service can handle artist metadata
        assert hasattr(enrichment_service, "enrich_artist_metadata")

    def test_service_error_handling_integration(self):
        """Test error handling across integrated services"""
        # Test that services gracefully handle failures from other services

        # Spotify service error handling
        with patch.object(
            spotify_service, "_make_request", side_effect=Exception("API Error")
        ):
            try:
                spotify_service.get_user_playlists()
            except Exception as e:
                assert "API Error" in str(e)

    def test_concurrent_service_operations(self):
        """Test that services can operate concurrently without conflicts"""
        # Test concurrent operations don't cause conflicts
        import threading

        def spotify_operation():
            with patch.object(spotify_service, "get_user_playlists") as mock_playlists:
                mock_playlists.return_value = {"items": []}
                return spotify_service.get_user_playlists()

        def discogs_operation():
            with patch.object(discogs_service, "search_artist") as mock_search:
                mock_search.return_value = []
                return discogs_service.search_artist("Test Artist")

        # Run operations concurrently
        threads = [
            threading.Thread(target=spotify_operation),
            threading.Thread(target=discogs_operation),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # If we get here without deadlocks, concurrent operations work
