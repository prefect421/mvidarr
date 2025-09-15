"""
Video Quality Management API endpoints for Issue #110
"""

from flask import Blueprint, jsonify, request

from src.services.video_quality_service import video_quality_service
from src.utils.logger import get_logger

video_quality_bp = Blueprint("video_quality", __name__, url_prefix="/video-quality")
logger = get_logger("mvidarr.api.video_quality")


@video_quality_bp.route("/preferences", methods=["GET"])
def get_quality_preferences():
    """Get quality preferences for a user or system defaults"""
    try:
        user_id = request.args.get("user_id", type=int)
        preferences = video_quality_service.get_user_quality_preferences(user_id)

        return jsonify({"success": True, "preferences": preferences})

    except Exception as e:
        logger.error(f"Error getting quality preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/preferences", methods=["POST"])
def set_quality_preferences():
    """Set quality preferences for a user or globally"""
    try:
        data = request.get_json()
        if not data or "preferences" not in data:
            return jsonify({"error": "preferences object is required"}), 400

        preferences = data["preferences"]
        user_id = data.get("user_id")

        success = video_quality_service.set_user_quality_preferences(
            preferences, user_id
        )

        if success:
            return jsonify(
                {"success": True, "message": "Quality preferences updated successfully"}
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Failed to validate or save preferences",
                    }
                ),
                400,
            )

    except Exception as e:
        logger.error(f"Error setting quality preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/format-string", methods=["GET"])
def get_ytdlp_format_string():
    """Get yt-dlp format string based on quality preferences"""
    try:
        user_id = request.args.get("user_id", type=int)
        artist_id = request.args.get("artist_id", type=int)

        format_string = video_quality_service.generate_ytdlp_format_string(
            user_id, artist_id
        )

        return jsonify({"success": True, "format_string": format_string})

    except Exception as e:
        logger.error(f"Error getting yt-dlp format string: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/analyze/<int:video_id>", methods=["POST"])
def analyze_video_quality(video_id):
    """Analyze the quality of a specific video (background job)"""
    try:
        import asyncio

        # Get current user from session for job tracking
        from flask import session

        from src.middleware.simple_auth_middleware import auth_required
        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        current_user = session.get("username")

        # Create background job for video quality analysis
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_ANALYZE,
            priority=JobPriority.NORMAL,
            payload={"video_id": video_id},
            created_by=current_user,
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(
            f"Enqueued video quality analysis job {job_id} for video {video_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Video quality analysis job queued for video {video_id}",
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Error queueing video quality analysis for video {video_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/upgradeable", methods=["GET"])
def find_upgradeable_videos():
    """Find videos that could benefit from quality upgrades"""
    try:
        user_id = request.args.get("user_id", type=int)
        limit = int(request.args.get("limit", 0))  # 0 means no limit

        upgradeable_videos = video_quality_service.find_upgradeable_videos(
            user_id, limit
        )

        return jsonify(
            {
                "success": True,
                "upgradeable_videos": upgradeable_videos,
                "count": len(upgradeable_videos),
            }
        )

    except Exception as e:
        logger.error(f"Error finding upgradeable videos: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/upgrade/<int:video_id>", methods=["POST"])
def upgrade_video_quality(video_id):
    """Upgrade a video to higher quality (background job)"""
    try:
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        # Handle both JSON and empty requests
        try:
            data = request.get_json() or {}
        except Exception as json_error:
            logger.warning(
                f"JSON parsing error for video upgrade {video_id}: {json_error}"
            )
            # Fallback to empty data if JSON parsing fails
            data = {}

        user_id = data.get("user_id")

        # Get current user from session for job tracking
        from flask import session

        current_user = session.get("username")

        # Create background job for video quality upgrade
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_UPGRADE,
            priority=JobPriority.HIGH,  # Quality upgrades are high priority
            payload={"video_id": video_id, "user_id": user_id},
            created_by=current_user or user_id,
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(f"Enqueued video quality upgrade job {job_id} for video {video_id}")

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Video quality upgrade job queued for video {video_id}",
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Error queueing video quality upgrade for video {video_id}: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/bulk-upgrade", methods=["POST"])
def bulk_upgrade_videos():
    """Upgrade multiple videos to higher quality (background job)"""
    try:
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        user_id = data.get("user_id")

        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({"error": "video_ids must be a non-empty array"}), 400

        # Create background job for bulk video quality upgrade
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_BULK_UPGRADE,
            priority=JobPriority.HIGH,  # Bulk upgrades are high priority
            payload={"video_ids": video_ids, "user_id": user_id},
            created_by=getattr(request, "user_id", user_id),
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(
            f"Enqueued bulk video quality upgrade job {job_id} for {len(video_ids)} videos"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Bulk video quality upgrade job queued for {len(video_ids)} videos",
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Error queueing bulk video quality upgrade: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/statistics", methods=["GET"])
def get_quality_statistics():
    """Get system-wide video quality statistics"""
    # Add debugging
    try:
        from flask import current_app

        current_app.logger.info("Statistics endpoint called")
        stats = video_quality_service.get_quality_statistics()
        current_app.logger.info("Statistics retrieved successfully")

        # Ensure all values are JSON serializable
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {
                    str(k) if k is not None else "unknown": clean_for_json(v)
                    for k, v in obj.items()
                }
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            elif obj is None:
                return "none"
            else:
                return obj

        cleaned_stats = clean_for_json(stats)
        current_app.logger.info("Statistics cleaned for JSON serialization")
        return jsonify({"success": True, "statistics": cleaned_stats})
    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        from flask import current_app

        current_app.logger.error(f"Error getting quality statistics: {e}")
        current_app.logger.error(f"Full traceback: {error_trace}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/test-statistics", methods=["GET"])
def test_quality_statistics():
    """Get system-wide video quality statistics"""
    try:
        stats = video_quality_service.get_quality_statistics()

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Error getting quality statistics: {e}")
        logger.error(f"Full traceback: {error_trace}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/artist-preferences/<int:artist_id>", methods=["GET"])
def get_artist_quality_preferences(artist_id):
    """Get quality preferences for a specific artist"""
    try:
        preferences = video_quality_service._get_artist_quality_preferences(artist_id)

        return jsonify(
            {"success": True, "artist_id": artist_id, "preferences": preferences}
        )

    except Exception as e:
        logger.error(f"Error getting artist quality preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/artist-preferences/<int:artist_id>", methods=["POST"])
def set_artist_quality_preferences(artist_id):
    """Set quality preferences for a specific artist"""
    try:
        data = request.get_json()
        if not data or "preferences" not in data:
            return jsonify({"error": "preferences object is required"}), 400

        preferences = data["preferences"]
        success = video_quality_service.set_artist_quality_preferences(
            artist_id, preferences
        )

        if success:
            return jsonify(
                {
                    "success": True,
                    "message": f"Quality preferences set for artist {artist_id}",
                }
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Failed to validate or save artist preferences",
                    }
                ),
                400,
            )

    except Exception as e:
        logger.error(f"Error setting artist quality preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/quality-levels", methods=["GET"])
def get_available_quality_levels():
    """Get available quality levels and their descriptions"""
    try:
        from src.services.video_quality_service import QualityLevel

        quality_levels = []
        for level in QualityLevel:
            quality_levels.append(
                {
                    "value": level.value,
                    "height": level.to_height(),
                    "description": (
                        f"{level.value} ({level.to_height()}p)"
                        if level.value != "best"
                        else "Best Available"
                    ),
                }
            )

        return jsonify({"success": True, "quality_levels": quality_levels})

    except Exception as e:
        logger.error(f"Error getting quality levels: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/check-all-qualities", methods=["POST"])
def check_all_video_qualities():
    """Manually trigger quality checks for multiple videos (background job)"""
    try:
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        data = request.get_json() or {}
        limit = data.get("limit")  # None means check all videos
        only_unchecked = data.get("only_unchecked", True)

        limit_msg = f"up to {limit}" if limit else "all"
        logger.info(
            f"Queueing quality check for {limit_msg} videos (only_unchecked={only_unchecked})"
        )

        # Create background job for quality check
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_CHECK_ALL,
            priority=JobPriority.NORMAL,
            payload={"limit": limit, "only_unchecked": only_unchecked},
            created_by=getattr(request, "user_id", None),
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        logger.info(f"Enqueued quality check job {job_id} for {limit_msg} videos")

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Quality check job queued for {limit_msg} videos",
                }
            ),
            202,
        )

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Error queueing quality check job: {e}")
        logger.error(f"Full traceback: {error_trace}")
        return jsonify({"success": False, "error": str(e)}), 500


@video_quality_bp.route("/cleanup-stats", methods=["GET"])
def get_cleanup_statistics():
    """Get statistics about quality upgrade cleanup operations"""
    try:
        from src.database.connection import get_db
        from src.database.models import Video

        stats = {
            "total_cleanups": 0,
            "total_space_saved_bytes": 0,
            "total_space_saved_mb": 0,
            "total_space_saved_gb": 0,
            "recent_cleanups": [],
            "average_space_saved_mb": 0,
        }

        with get_db() as session:
            # Query videos that have cleanup metadata
            videos_with_cleanup = (
                session.query(Video)
                .filter(Video.video_metadata.contains('"quality_upgrade_cleanup"'))
                .all()
            )

            total_bytes_saved = 0
            recent_cleanups = []

            for video in videos_with_cleanup:
                if (
                    video.video_metadata
                    and "quality_upgrade_cleanup" in video.video_metadata
                ):
                    cleanup_info = video.video_metadata["quality_upgrade_cleanup"]

                    deleted_size = cleanup_info.get("deleted_file_size", 0)
                    total_bytes_saved += deleted_size

                    # Add to recent cleanups (latest first)
                    recent_cleanups.append(
                        {
                            "video_id": video.id,
                            "video_title": video.title,
                            "artist_name": (
                                video.artist.name if video.artist else "Unknown"
                            ),
                            "deleted_file_path": cleanup_info.get(
                                "deleted_file_path", ""
                            ),
                            "space_saved_mb": round(deleted_size / (1024 * 1024), 2),
                            "deleted_at": cleanup_info.get("deleted_at", ""),
                            "replaced_by_size_mb": round(
                                cleanup_info.get("replaced_by_size", 0) / (1024 * 1024),
                                2,
                            ),
                        }
                    )

            # Sort recent cleanups by deletion date (newest first)
            recent_cleanups.sort(key=lambda x: x.get("deleted_at", ""), reverse=True)

            # Calculate statistics
            stats["total_cleanups"] = len(videos_with_cleanup)
            stats["total_space_saved_bytes"] = total_bytes_saved
            stats["total_space_saved_mb"] = round(total_bytes_saved / (1024 * 1024), 2)
            stats["total_space_saved_gb"] = round(
                total_bytes_saved / (1024 * 1024 * 1024), 2
            )
            stats["recent_cleanups"] = recent_cleanups[:20]  # Latest 20 cleanups

            if len(videos_with_cleanup) > 0:
                stats["average_space_saved_mb"] = round(
                    stats["total_space_saved_mb"] / len(videos_with_cleanup), 2
                )

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Error getting cleanup statistics: {e}")
        logger.error(f"Full traceback: {error_trace}")
        return jsonify({"success": False, "error": str(e)}), 500
