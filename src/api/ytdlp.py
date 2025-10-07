"""
yt-dlp API endpoints for download management and status
"""

from flask import Blueprint, jsonify, request

from src.services.ytdlp_service import ytdlp_service
from src.utils.logger import get_logger

ytdlp_bp = Blueprint("ytdlp", __name__, url_prefix="/ytdlp")
logger = get_logger("mvidarr.api.ytdlp")


@ytdlp_bp.route("/cookie-status", methods=["GET"])
def get_cookie_status():
    """Get current cookie file status for SABR workarounds"""
    try:
        status = ytdlp_service.get_cookie_status()
        logger.debug(f"Cookie status result: {status}")

        # Ensure we always return a valid JSON response
        if not isinstance(status, dict):
            status = {"cookies_available": False, "error": "Invalid status response"}

        return jsonify(status)

    except Exception as e:
        logger.error(f"Error getting cookie status: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"cookies_available": False, "error": str(e)}), 500


@ytdlp_bp.route("/health", methods=["GET"])
def health_check():
    """Check yt-dlp service health and version"""
    try:
        health_status = ytdlp_service.health_check()
        return jsonify(health_status)

    except Exception as e:
        logger.error(f"Error checking yt-dlp health: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@ytdlp_bp.route("/queue", methods=["GET"])
def get_download_queue():
    """Get current download queue status"""
    try:
        queue_status = ytdlp_service.get_queue()
        return jsonify(queue_status)

    except Exception as e:
        logger.error(f"Error getting download queue: {e}")
        return jsonify({"error": str(e)}), 500


@ytdlp_bp.route("/history", methods=["GET"])
def get_download_history():
    """Get download history"""
    try:
        limit = request.args.get("limit", 50, type=int)
        history = ytdlp_service.get_history(limit=limit)
        return jsonify(history)

    except Exception as e:
        logger.error(f"Error getting download history: {e}")
        return jsonify({"error": str(e)}), 500
