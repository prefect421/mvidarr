"""
Unified Media Server Manager for coordinating Plex, Jellyfin, and Emby integrations
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.base_media_server_service import (
    BaseMediaServerService,
    MediaServerType,
    MediaType,
    SyncDirection,
)
from src.services.emby_service import emby_service
from src.services.jellyfin_service import jellyfin_service
from src.services.plex_service import plex_service
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.media_server_manager")


class SyncStrategy(Enum):
    """Media server sync strategies"""

    SEQUENTIAL = "sequential"  # Sync servers one at a time
    PARALLEL = "parallel"  # Sync servers concurrently
    PRIORITY = "priority"  # Sync by configured priority order


class MediaServerManager:
    """Unified manager for all media server integrations"""

    def __init__(self):
        self.servers = {
            MediaServerType.PLEX: plex_service,
            MediaServerType.JELLYFIN: jellyfin_service,
            MediaServerType.EMBY: emby_service,
        }

        self._sync_in_progress = False
        self._last_full_sync = None
        self._sync_lock = threading.Lock()

        # Load configuration
        self.config = self._load_manager_config()

    def _load_manager_config(self) -> Dict:
        """Load media server manager configuration"""
        try:
            return {
                "auto_sync_enabled": SettingsService.get_bool(
                    "media_server_auto_sync", True
                ),
                "sync_interval_hours": SettingsService.get_int(
                    "media_server_sync_interval", 24
                ),
                "sync_strategy": SettingsService.get(
                    "media_server_sync_strategy", SyncStrategy.PARALLEL.value
                ),
                "enabled_servers": {
                    "plex": SettingsService.get_bool("plex_enabled", False),
                    "jellyfin": SettingsService.get_bool("jellyfin_enabled", False),
                    "emby": SettingsService.get_bool("emby_enabled", False),
                },
                "server_priority": [
                    SettingsService.get("media_server_priority_1", "plex"),
                    SettingsService.get("media_server_priority_2", "jellyfin"),
                    SettingsService.get("media_server_priority_3", "emby"),
                ],
            }
        except Exception as e:
            logger.error(f"Failed to load manager configuration: {e}")
            return {
                "auto_sync_enabled": True,
                "sync_interval_hours": 24,
                "sync_strategy": SyncStrategy.PARALLEL.value,
                "enabled_servers": {"plex": False, "jellyfin": False, "emby": False},
                "server_priority": ["plex", "jellyfin", "emby"],
            }

    def get_enabled_servers(self) -> List[BaseMediaServerService]:
        """Get list of enabled and configured media servers"""
        enabled_servers = []

        for server_type, service in self.servers.items():
            server_name = server_type.value
            if self.config["enabled_servers"].get(server_name, False):
                # Check if server is properly configured
                if self._is_server_configured(service):
                    enabled_servers.append(service)
                else:
                    logger.warning(
                        f"{server_name} is enabled but not properly configured"
                    )

        return enabled_servers

    def _is_server_configured(self, service: BaseMediaServerService) -> bool:
        """Check if a media server service is properly configured"""
        try:
            config = service.config

            # Check basic configuration
            if not config.server_url:
                return False

            # Check authentication configuration
            has_auth = (
                config.api_key
                or (config.username and config.password)
                or config.auth_token
            )

            return has_auth

        except Exception as e:
            logger.error(f"Failed to check server configuration: {e}")
            return False

    def test_all_connections(self) -> Dict:
        """Test connections to all enabled media servers"""
        enabled_servers = self.get_enabled_servers()
        results = {}

        def test_server(service):
            server_name = service.server_type.value
            try:
                connection_result = service.test_connection()
                connection_result["server_type"] = server_name
                connection_result["server_url"] = service.config.server_url
                return server_name, connection_result
            except Exception as e:
                logger.error(f"Failed to test {server_name} connection: {e}")
                return server_name, {
                    "connected": False,
                    "error": str(e),
                    "server_type": server_name,
                    "server_url": service.config.server_url,
                }

        # Test connections in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_server = {
                executor.submit(test_server, service): service
                for service in enabled_servers
            }

            for future in as_completed(future_to_server):
                try:
                    server_name, result = future.result(timeout=30)
                    results[server_name] = result
                except Exception as e:
                    service = future_to_server[future]
                    server_name = service.server_type.value
                    logger.error(f"Connection test failed for {server_name}: {e}")
                    results[server_name] = {
                        "connected": False,
                        "error": str(e),
                        "server_type": server_name,
                        "server_url": service.config.server_url,
                    }

        # Add results for disabled servers
        for server_type, service in self.servers.items():
            server_name = server_type.value
            if server_name not in results:
                results[server_name] = {
                    "connected": False,
                    "enabled": False,
                    "configured": self._is_server_configured(service),
                    "server_type": server_name,
                    "server_url": service.config.server_url,
                }

        return results

    def get_all_libraries(self) -> Dict:
        """Get libraries from all enabled media servers"""
        enabled_servers = self.get_enabled_servers()
        results = {}

        def get_server_libraries(service):
            server_name = service.server_type.value
            try:
                libraries = service.get_libraries()
                music_libraries = service.get_music_libraries()
                return server_name, {
                    "all_libraries": libraries,
                    "music_libraries": music_libraries,
                    "total_libraries": len(libraries),
                    "music_library_count": len(music_libraries),
                }
            except Exception as e:
                logger.error(f"Failed to get {server_name} libraries: {e}")
                return server_name, {
                    "error": str(e),
                    "all_libraries": [],
                    "music_libraries": [],
                    "total_libraries": 0,
                    "music_library_count": 0,
                }

        # Get libraries in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_server = {
                executor.submit(get_server_libraries, service): service
                for service in enabled_servers
            }

            for future in as_completed(future_to_server):
                try:
                    server_name, result = future.result(timeout=60)
                    results[server_name] = result
                except Exception as e:
                    service = future_to_server[future]
                    server_name = service.server_type.value
                    logger.error(f"Library retrieval failed for {server_name}: {e}")
                    results[server_name] = {
                        "error": str(e),
                        "all_libraries": [],
                        "music_libraries": [],
                        "total_libraries": 0,
                        "music_library_count": 0,
                    }

        return results

    def sync_all_servers(
        self,
        sync_direction: SyncDirection = SyncDirection.FROM_SERVER,
        server_types: List[str] = None,
    ) -> Dict:
        """Sync all enabled media servers with MVidarr"""
        with self._sync_lock:
            if self._sync_in_progress:
                return {
                    "success": False,
                    "error": "Sync already in progress",
                    "sync_in_progress": True,
                }

            self._sync_in_progress = True

        try:
            logger.info(
                f"Starting full media server sync with strategy: {self.config['sync_strategy']}"
            )

            enabled_servers = self.get_enabled_servers()

            # Filter by requested server types
            if server_types:
                enabled_servers = [
                    service
                    for service in enabled_servers
                    if service.server_type.value in server_types
                ]

            if not enabled_servers:
                return {
                    "success": False,
                    "error": "No enabled media servers found",
                    "servers_synced": [],
                }

            overall_results = {
                "success": True,
                "sync_strategy": self.config["sync_strategy"],
                "sync_direction": sync_direction.value,
                "start_time": datetime.utcnow().isoformat(),
                "end_time": None,
                "servers_synced": [],
                "total_artists": 0,
                "total_videos": 0,
                "total_new_artists": 0,
                "total_new_videos": 0,
                "total_errors": 0,
                "errors": [],
            }

            # Execute sync based on strategy
            if self.config["sync_strategy"] == SyncStrategy.PARALLEL.value:
                server_results = self._sync_servers_parallel(
                    enabled_servers, sync_direction
                )
            elif self.config["sync_strategy"] == SyncStrategy.PRIORITY.value:
                server_results = self._sync_servers_by_priority(
                    enabled_servers, sync_direction
                )
            else:  # Sequential
                server_results = self._sync_servers_sequential(
                    enabled_servers, sync_direction
                )

            # Aggregate results
            for server_name, result in server_results.items():
                overall_results["servers_synced"].append(
                    {
                        "server_type": server_name,
                        "success": "errors" not in result or len(result["errors"]) == 0,
                        "result": result,
                    }
                )

                overall_results["total_artists"] += result.get("artists_processed", 0)
                overall_results["total_videos"] += result.get("videos_processed", 0)
                overall_results["total_new_artists"] += result.get("new_artists", 0)
                overall_results["total_new_videos"] += result.get("new_videos", 0)
                overall_results["total_errors"] += len(result.get("errors", []))
                overall_results["errors"].extend(result.get("errors", []))

            overall_results["end_time"] = datetime.utcnow().isoformat()
            overall_results["success"] = overall_results["total_errors"] == 0

            self._last_full_sync = datetime.utcnow()

            logger.info(
                f"Full sync completed: {overall_results['total_new_artists']} new artists, "
                f"{overall_results['total_new_videos']} new videos"
            )

            return overall_results

        except Exception as e:
            logger.error(f"Full sync failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "end_time": datetime.utcnow().isoformat(),
            }
        finally:
            self._sync_in_progress = False

    def _sync_servers_parallel(
        self, servers: List[BaseMediaServerService], sync_direction: SyncDirection
    ) -> Dict:
        """Sync servers in parallel"""
        results = {}

        def sync_server(service):
            server_name = service.server_type.value
            try:
                return server_name, service.sync_with_mvidarr(sync_direction)
            except Exception as e:
                logger.error(f"Failed to sync {server_name}: {e}")
                return server_name, {"errors": [str(e)]}

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_server = {
                executor.submit(sync_server, service): service for service in servers
            }

            for future in as_completed(future_to_server):
                try:
                    server_name, result = future.result(
                        timeout=1800
                    )  # 30 minute timeout
                    results[server_name] = result
                except Exception as e:
                    service = future_to_server[future]
                    server_name = service.server_type.value
                    logger.error(f"Sync failed for {server_name}: {e}")
                    results[server_name] = {"errors": [str(e)]}

        return results

    def _sync_servers_sequential(
        self, servers: List[BaseMediaServerService], sync_direction: SyncDirection
    ) -> Dict:
        """Sync servers one at a time"""
        results = {}

        for service in servers:
            server_name = service.server_type.value
            try:
                logger.info(f"Starting sync for {server_name}")
                results[server_name] = service.sync_with_mvidarr(sync_direction)
            except Exception as e:
                logger.error(f"Failed to sync {server_name}: {e}")
                results[server_name] = {"errors": [str(e)]}

        return results

    def _sync_servers_by_priority(
        self, servers: List[BaseMediaServerService], sync_direction: SyncDirection
    ) -> Dict:
        """Sync servers in configured priority order"""
        results = {}

        # Sort servers by configured priority
        priority_order = self.config["server_priority"]
        sorted_servers = sorted(
            servers,
            key=lambda s: (
                priority_order.index(s.server_type.value)
                if s.server_type.value in priority_order
                else 999
            ),
        )

        for service in sorted_servers:
            server_name = service.server_type.value
            try:
                logger.info(f"Starting priority sync for {server_name}")
                results[server_name] = service.sync_with_mvidarr(sync_direction)
            except Exception as e:
                logger.error(f"Failed to sync {server_name}: {e}")
                results[server_name] = {"errors": [str(e)]}

        return results

    def scan_all_libraries(self, server_types: List[str] = None) -> Dict:
        """Trigger library scans on all enabled media servers"""
        enabled_servers = self.get_enabled_servers()

        # Filter by requested server types
        if server_types:
            enabled_servers = [
                service
                for service in enabled_servers
                if service.server_type.value in server_types
            ]

        results = {}

        def scan_server_libraries(service):
            server_name = service.server_type.value
            try:
                # Get music libraries and trigger scans
                music_libraries = service.get_music_libraries()
                scan_results = []

                for library in music_libraries:
                    library_id = library.get("id")
                    scan_result = service.scan_library(library_id)
                    scan_results.append(
                        {
                            "library_id": library_id,
                            "library_name": library.get("name"),
                            "result": scan_result,
                        }
                    )

                return server_name, {
                    "success": True,
                    "libraries_scanned": len(scan_results),
                    "scan_results": scan_results,
                }

            except Exception as e:
                logger.error(f"Failed to scan {server_name} libraries: {e}")
                return server_name, {"success": False, "error": str(e)}

        # Scan libraries in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_server = {
                executor.submit(scan_server_libraries, service): service
                for service in enabled_servers
            }

            for future in as_completed(future_to_server):
                try:
                    server_name, result = future.result(timeout=300)  # 5 minute timeout
                    results[server_name] = result
                except Exception as e:
                    service = future_to_server[future]
                    server_name = service.server_type.value
                    logger.error(f"Library scan failed for {server_name}: {e}")
                    results[server_name] = {"success": False, "error": str(e)}

        return results

    def get_sync_status(self) -> Dict:
        """Get overall sync status for all media servers"""
        enabled_servers = self.get_enabled_servers()

        status = {
            "sync_in_progress": self._sync_in_progress,
            "last_full_sync": (
                self._last_full_sync.isoformat() if self._last_full_sync else None
            ),
            "config": self.config,
            "servers": {},
        }

        for service in enabled_servers:
            server_name = service.server_type.value
            try:
                server_status = service.get_sync_status()
                server_status.update(service.get_sync_statistics())
                status["servers"][server_name] = server_status
            except Exception as e:
                logger.error(f"Failed to get sync status for {server_name}: {e}")
                status["servers"][server_name] = {"error": str(e)}

        return status

    def should_auto_sync(self) -> bool:
        """Check if automatic sync should be triggered"""
        if not self.config["auto_sync_enabled"]:
            return False

        if self._sync_in_progress:
            return False

        if not self._last_full_sync:
            return True

        sync_interval = timedelta(hours=self.config["sync_interval_hours"])
        return datetime.utcnow() - self._last_full_sync >= sync_interval

    def get_server_statistics(self) -> Dict:
        """Get comprehensive statistics for all media servers"""
        enabled_servers = self.get_enabled_servers()
        stats = {
            "total_servers_configured": len(self.servers),
            "total_servers_enabled": len(enabled_servers),
            "servers": {},
        }

        for server_type, service in self.servers.items():
            server_name = server_type.value
            server_stats = {
                "enabled": server_name
                in [s.server_type.value for s in enabled_servers],
                "configured": self._is_server_configured(service),
                "connected": False,
            }

            if server_stats["enabled"] and server_stats["configured"]:
                try:
                    # Get connection status
                    connection_test = service.test_connection()
                    server_stats["connected"] = connection_test["connected"]

                    if server_stats["connected"]:
                        # Get detailed statistics
                        libraries = service.get_music_libraries()
                        server_stats.update(
                            {
                                "music_libraries": len(libraries),
                                "server_info": service.get_server_info(),
                                "sync_stats": service.get_sync_statistics(),
                            }
                        )

                except Exception as e:
                    logger.error(f"Failed to get statistics for {server_name}: {e}")
                    server_stats["error"] = str(e)

            stats["servers"][server_name] = server_stats

        return stats


# Global instance
media_server_manager = MediaServerManager()
