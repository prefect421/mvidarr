"""
Integration tests for Media Server Integration (Issue #80)
"""

from unittest.mock import Mock, patch

import pytest

from src.services.base_media_server_service import (
    MediaServerConfig,
    MediaServerType,
    SyncDirection,
)
from src.services.emby_service import EmbyService
from src.services.jellyfin_service import JellyfinService
from src.services.media_server_manager import media_server_manager
from src.services.media_server_sync_service import MediaServerSyncService


class TestMediaServerIntegration:
    """Integration tests for media server services"""

    def test_media_server_manager_initialization(self):
        """Test MediaServerManager initializes correctly"""
        manager = media_server_manager
        assert manager is not None
        assert hasattr(manager, "sync_all_servers")
        assert hasattr(manager, "test_all_connections")

    def test_jellyfin_service_configuration(self):
        """Test JellyfinService configuration handling"""
        from src.services.base_media_server_service import MediaServerType

        config = MediaServerConfig(
            server_type=MediaServerType.JELLYFIN,
            server_url="http://localhost:8096",
            api_key="test_key",
            username="test_user",
        )

        service = JellyfinService(config)
        assert service.config.server_url == "http://localhost:8096"
        assert service.config.api_key == "test_key"

    def test_emby_service_configuration(self):
        """Test EmbyService configuration handling"""
        from src.services.base_media_server_service import MediaServerType

        config = MediaServerConfig(
            server_type=MediaServerType.EMBY,
            server_url="http://localhost:8092",
            api_key="test_key",
            username="test_user",
        )

        service = EmbyService(config)
        assert service.config.server_url == "http://localhost:8092"
        assert service.config.api_key == "test_key"

    @patch("src.services.jellyfin_service.requests.get")
    def test_jellyfin_authentication_flow(self, mock_get):
        """Test Jellyfin authentication process"""
        # Mock successful system info response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "test-server-id"}
        mock_get.return_value = mock_response

        config = MediaServerConfig(
            server_type=MediaServerType.JELLYFIN,
            server_url="http://localhost:8096",
            api_key="test_api_key",
        )

        service = JellyfinService(config)
        result = service.authenticate()

        assert result is True
        assert service._connected is True

    @patch("src.services.emby_service.requests.get")
    def test_emby_authentication_flow(self, mock_get):
        """Test Emby authentication process"""
        # Mock successful system info response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "test-server-id"}
        mock_get.return_value = mock_response

        config = MediaServerConfig(
            server_type=MediaServerType.EMBY,
            server_url="http://localhost:8092",
            api_key="test_api_key",
        )

        service = EmbyService(config)
        result = service.authenticate()

        assert result is True
        assert service._connected is True

    def test_sync_direction_enum(self):
        """Test SyncDirection enum values"""
        assert SyncDirection.FROM_SERVER.value == "from_server"
        assert SyncDirection.TO_SERVER.value == "to_server"
        assert SyncDirection.BIDIRECTIONAL.value == "bidirectional"

    def test_media_server_manager_connection_testing(self):
        """Test MediaServerManager connection testing"""
        manager = media_server_manager

        # Test that the method exists and returns expected structure
        with patch.object(manager, "_get_server_configs", return_value=[]):
            result = manager.test_all_connections()

            assert "success" in result
            assert "results" in result
            assert isinstance(result["results"], list)

    def test_media_server_sync_service_initialization(self):
        """Test MediaServerSyncService initializes correctly"""
        sync_service = MediaServerSyncService()
        assert sync_service is not None
        assert hasattr(sync_service, "sync_metadata_bidirectional")
        assert hasattr(sync_service, "_resolve_metadata_conflicts")
