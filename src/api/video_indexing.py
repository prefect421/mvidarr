"""
Video indexing API endpoints
"""

from flask import Blueprint, jsonify, request

from src.services.imvdb_service import imvdb_service
from src.services.thumbnail_service import thumbnail_service
from src.services.video_indexing_service import video_indexing_service
from src.utils.logger import get_logger

video_indexing_bp = Blueprint("video_indexing", __name__, url_prefix="/video-indexing")
logger = get_logger("mvidarr.api.video_indexing")


@video_indexing_bp.route("/index-all", methods=["POST"])
def index_all_videos():
    """Index all videos in the music videos directory (background job)"""
    try:
        # Get optional parameters
        data = request.get_json() or {}
        fetch_metadata = data.get("fetch_metadata", True)
        max_files = data.get("max_files")

        logger.info(
            f"Starting video indexing process (fetch_metadata={fetch_metadata}, max_files={max_files})"
        )

        # Create background job for video indexing
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        job = BackgroundJob(
            type=JobType.VIDEO_INDEX_ALL,
            priority=JobPriority.NORMAL,
            payload={"fetch_metadata": fetch_metadata, "max_files": max_files},
            created_by=getattr(request, "user_id", None),
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(f"Enqueued video indexing job {job_id}")

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Video indexing job queued (fetch_metadata={fetch_metadata}, max_files={max_files or 'all'})",
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Failed to queue video indexing job: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_indexing_bp.route("/index-single", methods=["POST"])
def index_single_video():
    """Index a specific video file (background job)"""
    try:
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        data = request.get_json()
        if not data or "file_path" not in data:
            return jsonify({"success": False, "error": "file_path is required"}), 400

        file_path = data["file_path"]
        fetch_metadata = data.get("fetch_metadata", True)

        # Create background job for single video indexing
        job = BackgroundJob(
            type=JobType.VIDEO_INDEX_SINGLE,
            priority=JobPriority.HIGH,  # Single video indexing is higher priority
            payload={"file_path": file_path, "fetch_metadata": fetch_metadata},
            created_by=getattr(request, "user_id", None),
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(f"Enqueued single video indexing job {job_id} for {file_path}")

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Single video indexing job queued for {file_path}",
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Failed to queue single video indexing job: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_indexing_bp.route("/stats", methods=["GET"])
def get_indexing_stats():
    """Get video indexing statistics"""
    try:
        stats = video_indexing_service.get_indexing_stats()

        # Add thumbnail stats
        thumbnail_stats = thumbnail_service.get_storage_stats()
        stats["thumbnail_stats"] = thumbnail_stats

        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Failed to get indexing stats: {e}")
        return jsonify({"error": str(e)}), 500


@video_indexing_bp.route("/scan-files", methods=["GET"])
def scan_video_files():
    """Scan directory for video files without indexing"""
    try:
        # Get optional directory parameter
        directory = request.args.get("directory")

        from pathlib import Path

        scan_dir = Path(directory) if directory else None

        video_files = video_indexing_service.scan_video_files(scan_dir)

        # Convert Path objects to strings
        file_list = [str(f) for f in video_files]

        return (
            jsonify(
                {
                    "files": file_list,
                    "count": len(file_list),
                    "directory": str(scan_dir) if scan_dir else "default",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to scan video files: {e}")
        return jsonify({"error": str(e)}), 500


@video_indexing_bp.route("/metadata/search", methods=["POST"])
def search_metadata():
    """Search IMVDb for metadata"""
    try:
        data = request.get_json()
        if not data or "artist" not in data:
            return jsonify({"success": False, "error": "artist is required"}), 400

        artist = data["artist"]
        title = data.get("title")

        if title:
            # Search for specific video
            metadata = imvdb_service.find_best_video_match(artist, title)
            if metadata:
                return (
                    jsonify(
                        {
                            "success": True,
                            "metadata": imvdb_service.extract_metadata(metadata),
                        }
                    ),
                    200,
                )
            else:
                return (
                    jsonify({"success": False, "message": "No matching video found"}),
                    404,
                )
        else:
            # Search for videos by artist
            videos = imvdb_service.search_videos(artist)
            metadata_list = [imvdb_service.extract_metadata(video) for video in videos]

            return (
                jsonify(
                    {
                        "success": True,
                        "videos": metadata_list,
                        "count": len(metadata_list),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to search metadata: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_indexing_bp.route("/thumbnails/download", methods=["POST"])
def download_thumbnail():
    """Download thumbnail for a video"""
    try:
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"success": False, "error": "url is required"}), 400

        url = data["url"]
        artist = data.get("artist", "unknown")
        title = data.get("title", "unknown")

        thumbnail_path = thumbnail_service.download_video_thumbnail(artist, title, url)

        if thumbnail_path:
            return (
                jsonify(
                    {
                        "success": True,
                        "thumbnail_path": thumbnail_path,
                        "message": "Thumbnail downloaded successfully",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"success": False, "error": "Failed to download thumbnail"}),
                400,
            )

    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_indexing_bp.route("/thumbnails/stats", methods=["GET"])
def get_thumbnail_stats():
    """Get thumbnail storage statistics"""
    try:
        stats = thumbnail_service.get_storage_stats()
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Failed to get thumbnail stats: {e}")
        return jsonify({"error": str(e)}), 500


@video_indexing_bp.route("/imvdb/test", methods=["GET"])
def test_imvdb_connection():
    """Test IMVDb API connection"""
    try:
        result = imvdb_service.test_connection()

        status_code = 200 if result["status"] == "success" else 503
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"IMVDb connection test failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 503


@video_indexing_bp.route("/preview", methods=["POST"])
def preview_indexing():
    """Preview what would be indexed without actually indexing"""
    try:
        data = request.get_json()
        if not data or "file_path" not in data:
            return jsonify({"success": False, "error": "file_path is required"}), 400

        file_path = data["file_path"]

        from pathlib import Path

        file_metadata = video_indexing_service.extract_file_metadata(Path(file_path))

        preview = {
            "file_path": file_path,
            "file_metadata": file_metadata,
            "can_index": bool(file_metadata.get("extracted_artist")),
            "imvdb_preview": None,
        }

        # Try to get IMVDb preview if we have artist and title
        if file_metadata.get("extracted_artist") and file_metadata.get(
            "extracted_title"
        ):
            try:
                imvdb_metadata = video_indexing_service.fetch_imvdb_metadata(
                    file_metadata["extracted_artist"], file_metadata["extracted_title"]
                )
                preview["imvdb_preview"] = imvdb_metadata
            except Exception as e:
                logger.warning(f"Failed to get IMVDb preview: {e}")

        return jsonify(preview), 200

    except Exception as e:
        logger.error(f"Failed to preview indexing: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
