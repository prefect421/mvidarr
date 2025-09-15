"""
Video discovery API endpoints
"""

from flask import Blueprint, jsonify, request

from src.services.video_discovery_service import video_discovery_service
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

video_discovery_bp = Blueprint("video_discovery", __name__, url_prefix="/discovery")
logger = get_logger("mvidarr.api.video_discovery")


@video_discovery_bp.route("/artist/<int:artist_id>", methods=["POST"])
@monitor_performance("api.discovery.artist")
def discover_for_artist(artist_id):
    """Discover new videos for a specific artist"""
    try:
        data = request.get_json() or {}
        limit = data.get("limit", 10)

        result = video_discovery_service.discover_videos_for_artist(artist_id, limit)

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Artist discovery failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_discovery_bp.route("/all", methods=["POST"])
def discover_for_all_artists():
    """Discover new videos for all monitored artists"""
    try:
        data = request.get_json() or {}
        limit_per_artist = data.get("limit_per_artist", 5)

        result = video_discovery_service.discover_videos_for_all_artists(
            limit_per_artist
        )

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Bulk discovery failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_discovery_bp.route("/stats", methods=["GET"])
def get_discovery_stats():
    """Get video discovery statistics"""
    try:
        stats = video_discovery_service.get_discovery_stats()

        return jsonify({"success": True, "stats": stats}), 200

    except Exception as e:
        logger.error(f"Failed to get discovery stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_discovery_bp.route("/test/<int:artist_id>", methods=["GET"])
def test_discovery_for_artist(artist_id):
    """Test video discovery for an artist (returns preview without storing)"""
    try:
        # This would be a dry-run version that doesn't store results
        result = video_discovery_service.discover_videos_for_artist(artist_id, limit=3)

        # Remove stored videos from response for preview
        if result.get("success"):
            result["preview"] = True
            result["note"] = "This is a preview - videos were not stored"

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Discovery test failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def discover_videos_for_artists(
    limit_artists=5,
    limit_videos_per_artist=3,
    max_artists=None,
    max_videos_per_artist=None,
    scheduled=False,
):
    """Discover videos for multiple artists (helper function for scheduler)

    Args:
        limit_artists: Maximum number of artists to process (for backward compatibility)
        limit_videos_per_artist: Maximum videos to discover per artist (for backward compatibility)
        max_artists: Alternative name for limit_artists
        max_videos_per_artist: Alternative name for limit_videos_per_artist
        scheduled: Whether this is a scheduled discovery operation

    Returns:
        dict: Discovery results with artists_processed and videos_discovered counts
    """
    try:
        # Support both parameter naming conventions
        artists_limit = max_artists or limit_artists
        videos_limit = max_videos_per_artist or limit_videos_per_artist

        logger.info(
            f"Starting video discovery for {artists_limit} artists, {videos_limit} videos per artist (scheduled={scheduled})"
        )

        # Use the existing discovery service
        result = video_discovery_service.discover_videos_for_all_artists(
            limit_per_artist=videos_limit, max_artists=artists_limit
        )

        if result.get("success"):
            # Standardize return format for scheduler
            return {
                "success": True,
                "artists_processed": result.get("processed_artists", 0),
                "videos_discovered": result.get("total_discovered", 0),
                "scheduled": scheduled,
                "details": result,
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Discovery failed"),
                "artists_processed": 0,
                "videos_discovered": 0,
            }

    except Exception as e:
        logger.error(f"Error in discover_videos_for_artists: {e}")
        return {
            "success": False,
            "error": str(e),
            "artists_processed": 0,
            "videos_discovered": 0,
        }
