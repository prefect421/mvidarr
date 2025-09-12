"""
yt-dlp CLI API endpoints for video downloading (renamed from metube for compatibility)
"""

import os

from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from src.services.ytdlp_service import ytdlp_service
from src.utils.logger import get_logger

metube_bp = Blueprint("metube", __name__, url_prefix="/metube")
logger = get_logger("mvidarr.api.metube")

COOKIE_FOLDER = "data/cookies"
ALLOWED_EXTENSIONS = {"txt", "cookies"}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@metube_bp.route("/test", methods=["GET"])
def test_connection():
    """Test yt-dlp availability"""
    try:
        result = ytdlp_service.health_check()

        status_code = 200 if result["status"] == "healthy" else 503
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"yt-dlp health check failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 503


@metube_bp.route("/queue", methods=["GET"])
def get_download_queue():
    """Get current download queue"""
    try:
        result = ytdlp_service.get_queue()
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to get download queue: {e}")
        return jsonify({"error": str(e)}), 500


@metube_bp.route("/history", methods=["GET"])
def get_download_history():
    """Get download history"""
    try:
        limit = request.args.get("limit", 50, type=int)
        result = ytdlp_service.get_history(limit=limit)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to get download history: {e}")
        return jsonify({"error": str(e)}), 500


@metube_bp.route("/download/music-video", methods=["POST"])
def add_music_video_download():
    """Add a music video download with MVidarr formatting"""
    try:
        data = request.get_json()
        required_fields = ["artist", "title", "url"]

        for field in required_fields:
            if not data or field not in data:
                return jsonify({"success": False, "error": f"{field} is required"}), 400

        artist = data["artist"]
        title = data["title"]
        url = data["url"]
        quality = data.get("quality", "best")
        video_id = data.get("video_id")
        download_subtitles = data.get("download_subtitles", False)

        # Read subtitle language settings if not provided in request
        from src.services.settings_service import settings

        subtitle_languages = data.get("subtitle_languages") or settings.get(
            "subtitle_languages", "en,en-US"
        )

        result = ytdlp_service.add_music_video_download(
            artist=artist,
            title=title,
            url=url,
            quality=quality,
            video_id=video_id,
            download_subtitles=download_subtitles,
            subtitle_languages=subtitle_languages,
        )

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to add music video download: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/download/<int:download_id>/stop", methods=["POST"])
def stop_download(download_id):
    """Stop a specific download"""
    try:
        result = ytdlp_service.stop_download(download_id)

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to stop download: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/download/<int:download_id>/retry", methods=["POST"])
def retry_download(download_id):
    """Retry a failed download"""
    try:
        result = ytdlp_service.retry_download(download_id)

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to retry download: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/history/clear", methods=["DELETE"])
def clear_history():
    """Clear download history"""
    try:
        result = ytdlp_service.clear_history()

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to clear history: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/clear-stuck", methods=["POST"])
def clear_stuck_downloads():
    """Clear downloads stuck at 0% progress"""
    try:
        data = request.get_json() or {}
        minutes = data.get("minutes", 10)

        result = ytdlp_service.clear_stuck_downloads(minutes=minutes)

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to clear stuck downloads: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/health", methods=["GET"])
def health_check():
    """Get yt-dlp service health status"""
    try:
        result = ytdlp_service.health_check()

        status_code = 200 if result["status"] == "healthy" else 503
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503


@metube_bp.route("/cookies/upload", methods=["POST"])
def upload_cookies():
    """Upload YouTube cookies file for age-restricted video downloads"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        if not allowed_file(file.filename):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "File type not allowed. Please upload a .txt or .cookies file",
                    }
                ),
                400,
            )

        # Ensure upload directory exists
        os.makedirs(COOKIE_FOLDER, exist_ok=True)

        # Save as youtube_cookies.txt for yt-dlp
        cookie_filename = "youtube_cookies.txt"
        cookie_path = os.path.join(COOKIE_FOLDER, cookie_filename)

        # Save the file
        file.save(cookie_path)

        # Validate cookie file format
        try:
            with open(cookie_path, "r") as f:
                content = f.read().strip()
                if not content:
                    os.remove(cookie_path)
                    return (
                        jsonify({"success": False, "error": "Cookie file is empty"}),
                        400,
                    )

                # Basic validation - check if it looks like cookies
                if not (
                    "youtube.com" in content.lower()
                    or "session_token" in content.lower()
                    or "\t" in content
                ):
                    os.remove(cookie_path)
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "File does not appear to contain valid cookies",
                            }
                        ),
                        400,
                    )

        except Exception as e:
            if os.path.exists(cookie_path):
                os.remove(cookie_path)
            return (
                jsonify(
                    {"success": False, "error": f"Failed to validate cookie file: {e}"}
                ),
                400,
            )

        # Update ytdlp service to use the uploaded cookies
        ytdlp_service.set_cookie_file(cookie_path)

        logger.info(f"Cookies uploaded successfully: {file.filename}")

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Cookies uploaded successfully",
                    "filename": cookie_filename,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to upload cookies: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/cookies/status", methods=["GET"])
def cookies_status():
    """Check if cookies are uploaded and available"""
    try:
        cookie_path = os.path.join(COOKIE_FOLDER, "youtube_cookies.txt")

        if os.path.exists(cookie_path):
            # Get file info
            stat = os.stat(cookie_path)
            file_size = stat.st_size
            modified_time = stat.st_mtime

            return (
                jsonify(
                    {
                        "success": True,
                        "cookies_available": True,
                        "file_size": file_size,
                        "modified_time": modified_time,
                        "path": cookie_path,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": True,
                        "cookies_available": False,
                        "message": "No cookies file uploaded",
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to check cookie status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/cookies/delete", methods=["DELETE"])
def delete_cookies():
    """Delete uploaded cookies file"""
    try:
        cookie_path = os.path.join(COOKIE_FOLDER, "youtube_cookies.txt")

        if os.path.exists(cookie_path):
            os.remove(cookie_path)
            ytdlp_service.clear_cookie_file()

            logger.info("Cookies deleted successfully")
            return (
                jsonify({"success": True, "message": "Cookies deleted successfully"}),
                200,
            )
        else:
            return (
                jsonify({"success": True, "message": "No cookies file to delete"}),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to delete cookies: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@metube_bp.route("/download/<int:download_id>/retry", methods=["POST"])
def retry_download(download_id):
    """Retry a failed download"""
    try:
        result = ytdlp_service.retry_download(download_id)
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Failed to retry download {download_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
