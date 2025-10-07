"""
Unified Media Server API endpoints for Plex, Jellyfin, and Emby integration
"""

from flask import Blueprint, jsonify, request

from src.services.base_media_server_service import SyncDirection
from src.services.media_server_manager import media_server_manager
from src.services.media_server_sync_service import media_server_sync_service
from src.utils.logger import get_logger

media_servers_bp = Blueprint("media_servers", __name__, url_prefix="/media-servers")
logger = get_logger("mvidarr.api.media_servers")


@media_servers_bp.route("/status", methods=["GET"])
def get_status():
    """Get status of all media server integrations"""
    try:
        connection_results = media_server_manager.test_all_connections()
        sync_status = media_server_manager.get_sync_status()

        return (
            jsonify(
                {
                    "success": True,
                    "connections": connection_results,
                    "sync_status": sync_status,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get media server status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/connections/test", methods=["POST"])
def test_connections():
    """Test connections to all configured media servers"""
    try:
        results = media_server_manager.test_all_connections()

        # Count successful connections
        successful_connections = sum(
            1 for result in results.values() if result.get("connected", False)
        )

        return (
            jsonify(
                {
                    "success": True,
                    "results": results,
                    "total_servers": len(results),
                    "successful_connections": successful_connections,
                    "message": f"{successful_connections} of {len(results)} servers connected successfully",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to test media server connections: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/libraries", methods=["GET"])
def get_libraries():
    """Get libraries from all enabled media servers"""
    try:
        libraries = media_server_manager.get_all_libraries()

        # Count total libraries
        total_libraries = sum(
            result.get("total_libraries", 0)
            for result in libraries.values()
            if "total_libraries" in result
        )

        total_music_libraries = sum(
            result.get("music_library_count", 0)
            for result in libraries.values()
            if "music_library_count" in result
        )

        return (
            jsonify(
                {
                    "success": True,
                    "libraries": libraries,
                    "summary": {
                        "total_libraries": total_libraries,
                        "music_libraries": total_music_libraries,
                        "servers_with_libraries": len(
                            [
                                r
                                for r in libraries.values()
                                if r.get("total_libraries", 0) > 0
                            ]
                        ),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get media server libraries: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/sync", methods=["POST"])
def sync_servers():
    """Sync all enabled media servers with MVidarr"""
    try:
        data = request.get_json() or {}

        # Parse sync direction
        sync_direction_str = data.get("sync_direction", "from_server")
        try:
            sync_direction = SyncDirection(sync_direction_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Invalid sync direction: {sync_direction_str}. Must be one of: {[e.value for e in SyncDirection]}",
                    }
                ),
                400,
            )

        # Optional server type filtering
        server_types = data.get("server_types")
        if server_types and not isinstance(server_types, list):
            return (
                jsonify({"success": False, "error": "server_types must be a list"}),
                400,
            )

        logger.info(
            f"Starting media server sync with direction: {sync_direction.value}"
        )

        # Start sync
        results = media_server_manager.sync_all_servers(sync_direction, server_types)

        if results["success"]:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Sync completed: {results['total_new_artists']} new artists, {results['total_new_videos']} new videos",
                        "results": results,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Sync completed with errors",
                        "results": results,
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Failed to sync media servers: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """Get detailed sync status for all media servers"""
    try:
        status = media_server_manager.get_sync_status()

        return jsonify({"success": True, "status": status}), 200

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/libraries/scan", methods=["POST"])
def scan_libraries():
    """Trigger library scans on all enabled media servers"""
    try:
        data = request.get_json() or {}
        server_types = data.get("server_types")

        logger.info("Starting library scans for all enabled media servers")

        results = media_server_manager.scan_all_libraries(server_types)

        # Count successful scans
        successful_scans = sum(
            1 for result in results.values() if result.get("success", False)
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Library scans initiated on {successful_scans} servers",
                    "results": results,
                    "total_servers": len(results),
                    "successful_scans": successful_scans,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to scan media server libraries: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/statistics", methods=["GET"])
def get_statistics():
    """Get comprehensive statistics for all media servers"""
    try:
        stats = media_server_manager.get_server_statistics()

        return jsonify({"success": True, "statistics": stats}), 200

    except Exception as e:
        logger.error(f"Failed to get media server statistics: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Individual server endpoints


@media_servers_bp.route("/plex/status", methods=["GET"])
def get_plex_status():
    """Get Plex server status"""
    try:
        from src.services.plex_service import plex_service

        connection_test = plex_service.test_connection()
        sync_stats = plex_service.get_sync_statistics()

        return (
            jsonify(
                {
                    "success": True,
                    "connection": connection_test,
                    "sync_statistics": sync_stats,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Plex status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/jellyfin/status", methods=["GET"])
def get_jellyfin_status():
    """Get Jellyfin server status"""
    try:
        from src.services.jellyfin_service import jellyfin_service

        connection_test = jellyfin_service.test_connection()
        sync_stats = jellyfin_service.get_sync_statistics()

        return (
            jsonify(
                {
                    "success": True,
                    "connection": connection_test,
                    "sync_statistics": sync_stats,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Jellyfin status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/emby/status", methods=["GET"])
def get_emby_status():
    """Get Emby server status"""
    try:
        from src.services.emby_service import emby_service

        connection_test = emby_service.test_connection()
        sync_stats = emby_service.get_sync_statistics()

        return (
            jsonify(
                {
                    "success": True,
                    "connection": connection_test,
                    "sync_statistics": sync_stats,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Emby status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/plex/libraries", methods=["GET"])
def get_plex_libraries():
    """Get Plex libraries"""
    try:
        from src.services.plex_service import plex_service

        all_libraries = plex_service.get_libraries()
        music_libraries = plex_service.get_music_libraries()

        return (
            jsonify(
                {
                    "success": True,
                    "all_libraries": all_libraries,
                    "music_libraries": music_libraries,
                    "total_libraries": len(all_libraries),
                    "music_library_count": len(music_libraries),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Plex libraries: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/jellyfin/libraries", methods=["GET"])
def get_jellyfin_libraries():
    """Get Jellyfin libraries"""
    try:
        from src.services.jellyfin_service import jellyfin_service

        all_libraries = jellyfin_service.get_libraries()
        music_libraries = jellyfin_service.get_music_libraries()

        return (
            jsonify(
                {
                    "success": True,
                    "all_libraries": all_libraries,
                    "music_libraries": music_libraries,
                    "total_libraries": len(all_libraries),
                    "music_library_count": len(music_libraries),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Jellyfin libraries: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/emby/libraries", methods=["GET"])
def get_emby_libraries():
    """Get Emby libraries"""
    try:
        from src.services.emby_service import emby_service

        all_libraries = emby_service.get_libraries()
        music_libraries = emby_service.get_music_libraries()

        return (
            jsonify(
                {
                    "success": True,
                    "all_libraries": all_libraries,
                    "music_libraries": music_libraries,
                    "total_libraries": len(all_libraries),
                    "music_library_count": len(music_libraries),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Emby libraries: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/plex/sync", methods=["POST"])
def sync_plex():
    """Sync Plex server with MVidarr"""
    try:
        data = request.get_json() or {}

        sync_direction_str = data.get("sync_direction", "from_server")
        try:
            sync_direction = SyncDirection(sync_direction_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Invalid sync direction: {sync_direction_str}",
                    }
                ),
                400,
            )

        from src.services.plex_service import plex_service

        results = plex_service.sync_with_mvidarr(sync_direction)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Plex sync completed: {results.get('new_artists', 0)} new artists",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to sync Plex: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/jellyfin/sync", methods=["POST"])
def sync_jellyfin():
    """Sync Jellyfin server with MVidarr"""
    try:
        data = request.get_json() or {}

        sync_direction_str = data.get("sync_direction", "from_server")
        try:
            sync_direction = SyncDirection(sync_direction_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Invalid sync direction: {sync_direction_str}",
                    }
                ),
                400,
            )

        from src.services.jellyfin_service import jellyfin_service

        results = jellyfin_service.sync_with_mvidarr(sync_direction)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Jellyfin sync completed: {results.get('new_artists', 0)} new artists",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to sync Jellyfin: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/emby/sync", methods=["POST"])
def sync_emby():
    """Sync Emby server with MVidarr"""
    try:
        data = request.get_json() or {}

        sync_direction_str = data.get("sync_direction", "from_server")
        try:
            sync_direction = SyncDirection(sync_direction_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Invalid sync direction: {sync_direction_str}",
                    }
                ),
                400,
            )

        from src.services.emby_service import emby_service

        results = emby_service.sync_with_mvidarr(sync_direction)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Emby sync completed: {results.get('new_artists', 0)} new artists",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to sync Emby: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/sync/bidirectional", methods=["POST"])
def sync_metadata_bidirectional():
    """Perform bidirectional metadata synchronization"""
    try:
        data = request.get_json() or {}
        server_types = data.get("server_types")
        force_sync = data.get("force_sync", False)

        logger.info("Starting bidirectional metadata synchronization")

        results = media_server_sync_service.sync_metadata_bidirectional(
            server_types=server_types, force_sync=force_sync
        )

        if results["success"]:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Bidirectional sync completed: {results['total_items_synced']} items synced, {results['total_conflicts_resolved']} conflicts resolved",
                        "results": results,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Bidirectional sync failed",
                        "results": results,
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Failed to perform bidirectional sync: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/conflicts/manual", methods=["GET"])
def get_manual_conflicts():
    """Get conflicts requiring manual resolution"""
    try:
        conflicts = media_server_sync_service.get_manual_conflict_queue()

        return (
            jsonify(
                {
                    "success": True,
                    "conflicts": conflicts,
                    "total_conflicts": len(conflicts),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get manual conflicts: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/conflicts/<conflict_id>/resolve", methods=["POST"])
def resolve_manual_conflict(conflict_id):
    """Resolve a manual conflict"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Resolution data required"}), 400

        result = media_server_sync_service.resolve_manual_conflict(conflict_id, data)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"Failed to resolve conflict: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/play-history", methods=["GET"])
def get_play_history():
    """Get play history from all enabled media servers"""
    try:
        server_type = request.args.get("server_type")
        limit = int(request.args.get("limit", 50))

        enabled_servers = media_server_manager.get_enabled_servers()

        # Filter by server type if specified
        if server_type:
            enabled_servers = [
                service
                for service in enabled_servers
                if service.server_type.value == server_type
            ]

        results = {}

        for service in enabled_servers:
            server_name = service.server_type.value
            try:
                play_history = service.get_play_history(limit=limit)
                recently_played = service.get_recently_played(limit=min(limit, 20))

                results[server_name] = {
                    "play_history": play_history,
                    "recently_played": recently_played,
                    "total_history_items": len(play_history),
                    "total_recent_items": len(recently_played),
                }

            except Exception as e:
                logger.error(f"Failed to get play history from {server_name}: {e}")
                results[server_name] = {"error": str(e)}

        return (
            jsonify(
                {
                    "success": True,
                    "results": results,
                    "servers_queried": len(enabled_servers),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get play history: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@media_servers_bp.route("/watch-status/<item_id>", methods=["POST"])
def update_watch_status(item_id):
    """Update watch status for an item on media servers"""
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify({"success": False, "error": "Watch status data required"}),
                400,
            )

        watched = data.get("watched", False)
        play_count = data.get("play_count")
        server_types = data.get("server_types")

        enabled_servers = media_server_manager.get_enabled_servers()

        # Filter by server types if specified
        if server_types:
            enabled_servers = [
                service
                for service in enabled_servers
                if service.server_type.value in server_types
            ]

        results = {}

        for service in enabled_servers:
            server_name = service.server_type.value
            try:
                success = service.update_play_status(item_id, watched, play_count)
                results[server_name] = {
                    "success": success,
                    "item_id": item_id,
                    "watched": watched,
                    "play_count": play_count,
                }

            except Exception as e:
                logger.error(f"Failed to update watch status on {server_name}: {e}")
                results[server_name] = {"success": False, "error": str(e)}

        # Count successful updates
        successful_updates = sum(
            1 for result in results.values() if result.get("success", False)
        )

        return (
            jsonify(
                {
                    "success": successful_updates > 0,
                    "results": results,
                    "successful_updates": successful_updates,
                    "total_servers": len(enabled_servers),
                    "message": f"Watch status updated on {successful_updates} of {len(enabled_servers)} servers",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to update watch status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
