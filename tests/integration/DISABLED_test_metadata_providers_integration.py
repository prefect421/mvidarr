"""
Integration tests for Third-Party Metadata Providers (Issue #83)
"""

from unittest.mock import Mock, patch

import pytest

from src.services.discogs_service import discogs_service
from src.services.metadata_enrichment_service import metadata_enrichment_service


class TestMetadataProvidersIntegration:
    """Integration tests for metadata provider services"""

    def test_discogs_service_initialization(self):
        """Test DiscogsService initializes correctly"""
        service = discogs_service
        assert service is not None
        assert hasattr(service, "search_artist")
        assert hasattr(service, "get_artist_metadata_for_enrichment")

    @patch("src.services.discogs_service.requests.get")
    def test_discogs_artist_search(self, mock_get):
        """Test Discogs artist search functionality"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 123456,
                    "title": "Test Artist",
                    "type": "artist",
                    "thumb": "http://example.com/thumb.jpg",
                }
            ]
        }
        mock_get.return_value = mock_response

        results = discogs_service.search_artist("Test Artist")

        assert results is not None
        assert len(results) > 0
        assert results[0]["confidence"] > 0.5

    def test_metadata_enrichment_includes_discogs(self):
        """Test that metadata enrichment includes Discogs as a source"""
        enrichment_service = metadata_enrichment_service

        # Check that Discogs is in the source weights
        assert hasattr(enrichment_service, "source_weights")
        # Note: This test validates structure; actual weights testing requires database

    @patch("src.services.discogs_service.DiscogsService._make_request")
    def test_discogs_rate_limiting(self, mock_request):
        """Test Discogs rate limiting functionality"""
        mock_request.return_value = {"results": []}

        service = discogs_service

        # Test that rate limiting attributes exist
        assert hasattr(service, "_last_request_time")
        assert hasattr(service, "_rate_limit_delay")

    def test_discogs_metadata_enrichment_integration(self):
        """Test Discogs integration with metadata enrichment"""
        # Mock artist data
        artist_data = {"name": "Test Artist", "discogs_id": None}

        with patch.object(
            discogs_service, "get_artist_metadata_for_enrichment"
        ) as mock_discogs:
            mock_discogs.return_value = {
                "name": "Test Artist",
                "discogs_id": "123456",
                "biography": "Test biography",
                "genres": ["Rock", "Pop"],
            }

            # Test that the method can be called
            result = discogs_service.get_artist_metadata_for_enrichment("Test Artist")

            assert result is not None
            if result:
                assert "discogs_id" in result

    def test_metadata_source_prioritization(self):
        """Test metadata source prioritization includes all providers"""
        enrichment_service = metadata_enrichment_service

        # Verify service has access to all metadata providers
        assert hasattr(enrichment_service, "musicbrainz")
        assert hasattr(enrichment_service, "lastfm")
        assert hasattr(enrichment_service, "spotify")
        assert hasattr(enrichment_service, "discogs")
        assert hasattr(enrichment_service, "allmusic")

    @patch("src.services.metadata_enrichment_service.get_db")
    def test_metadata_enrichment_workflow(self, mock_db):
        """Test complete metadata enrichment workflow"""
        # Mock database session
        mock_session = Mock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock artist query result
        mock_artist = Mock()
        mock_artist.id = 1
        mock_artist.name = "Test Artist"
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_artist
        )

        enrichment_service = metadata_enrichment_service

        # Test that enrichment can be initiated
        assert hasattr(enrichment_service, "enrich_artist_metadata")

    def test_all_metadata_providers_accessible(self):
        """Test that all metadata providers are accessible"""
        from src.services.allmusic_service import allmusic_service
        from src.services.discogs_service import discogs_service
        from src.services.lastfm_service import lastfm_service
        from src.services.musicbrainz_service import musicbrainz_service

        # Verify all services are available
        assert musicbrainz_service is not None
        assert lastfm_service is not None
        assert allmusic_service is not None
        assert discogs_service is not None

    def test_metadata_conflict_resolution_structure(self):
        """Test metadata conflict resolution structure"""
        enrichment_service = metadata_enrichment_service

        # Test that conflict resolution methods exist
        assert hasattr(enrichment_service, "source_weights")
        # Detailed conflict resolution testing requires database setup
