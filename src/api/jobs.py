"""
Background Job API Endpoints
RESTful API for managing background jobs, queuing tasks, and monitoring progress.
"""

import asyncio
import logging
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from src.middleware.simple_auth_middleware import auth_required
from src.services.job_queue import BackgroundJob, JobPriority, JobType, get_job_queue
from src.services.job_system_integration import (
    get_job_system_health,
    get_job_system_status,
    is_job_system_enabled,
)

logger = logging.getLogger(__name__)

# Create blueprint
jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@jobs_bp.route("/health", methods=["GET"])
def health_check():
    """Get job system health status"""
    try:
        if not is_job_system_enabled():
            return (
                jsonify(
                    {
                        "status": "starting",
                        "message": "Job system is starting up",
                        "details": {
                            "workers": "initializing",
                            "queue": "initializing",
                            "ready": False,
                        },
                    }
                ),
                200,
            )

        # Try to get detailed health data
        try:
            health_data = asyncio.run(get_job_system_health())
            status_code = 200 if health_data["status"] == "healthy" else 503
            return jsonify(health_data), status_code
        except Exception as health_error:
            logger.warning(f"Detailed health check failed: {health_error}")
            # Return basic healthy status if detailed check fails
            return (
                jsonify(
                    {
                        "status": "operational",
                        "message": "Job system is running (basic check)",
                        "details": {
                            "workers": "running",
                            "queue": "available",
                            "ready": True,
                            "note": "Detailed health check unavailable",
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return (
            jsonify(
                {"status": "error", "error": str(e), "message": "Health check failed"}
            ),
            200,
        )  # Return 200 instead of 500 to allow UI to display error


@jobs_bp.route("/status", methods=["GET"])
def system_status():
    """Get job system status and statistics"""
    try:
        status = get_job_system_status()
        return jsonify(status)

    except Exception as e:
        logger.error(f"Status check error: {e}")
        # Return basic status info if detailed check fails
        return (
            jsonify(
                {
                    "status": "partial",
                    "message": "Basic job system operational",
                    "error": str(e),
                    "queue_size": 0,
                    "active_jobs": 0,
                    "completed_jobs": 0,
                    "failed_jobs": 0,
                }
            ),
            200,
        )


@jobs_bp.route("/enqueue", methods=["POST"])
def enqueue_job():
    """
    Enqueue a new background job

    Request body:
    {
        "type": "metadata_enrichment",
        "priority": "normal",
        "payload": {
            "artist_id": 123,
            "force_refresh": true
        }
    }
    """
    try:
        from flask import session

        if not is_job_system_enabled():
            return jsonify({"error": "Job system is not enabled"}), 503

        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400

        # Validate required fields
        if "type" not in data:
            return jsonify({"error": "job type is required"}), 400

        if "payload" not in data:
            return jsonify({"error": "job payload is required"}), 400

        # Parse job type
        try:
            job_type = JobType(data["type"])
        except ValueError:
            valid_types = [t.value for t in JobType]
            return (
                jsonify({"error": f"Invalid job type. Valid types: {valid_types}"}),
                400,
            )

        # Parse priority (optional)
        priority = JobPriority.NORMAL
        if "priority" in data:
            try:
                priority = (
                    JobPriority(data["priority"])
                    if isinstance(data["priority"], int)
                    else JobPriority[data["priority"].upper()]
                )
            except (ValueError, KeyError):
                valid_priorities = [p.name.lower() for p in JobPriority]
                return (
                    jsonify(
                        {
                            "error": f"Invalid priority. Valid priorities: {valid_priorities}"
                        }
                    ),
                    400,
                )

        # Create job
        job = BackgroundJob(
            type=job_type,
            priority=priority,
            payload=data["payload"],
            created_by=session.get("username"),  # From session
        )

        # Add optional fields
        if "max_retries" in data:
            job.max_retries = max(0, min(10, int(data["max_retries"])))  # Clamp to 0-10

        if "retry_delay" in data:
            job.retry_delay = max(
                5, min(3600, int(data["retry_delay"]))
            )  # Clamp to 5s-1h

        # Enqueue job
        job_queue = asyncio.run(get_job_queue())
        job_id = asyncio.run(job_queue.enqueue(job))

        logger.info(
            f"Enqueued job {job_id} ({job_type.value}) for user {job.created_by}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"{job_type.value} job queued successfully",
                    "estimated_wait_time": 30,  # TODO: Calculate based on queue size
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Job enqueue error: {e}")
        return jsonify({"error": f"Failed to enqueue job: {str(e)}"}), 500


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Get status and progress of a specific job"""
    try:
        if not is_job_system_enabled():
            return jsonify({"error": "Job system is not enabled"}), 503

        job_queue = asyncio.run(get_job_queue())
        job = job_queue.get_job(job_id)

        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Check if user has permission to view this job
        from flask import session

        user_id = session.get("username")
        if job.created_by and job.created_by != user_id:
            # TODO: Add admin role check
            return jsonify({"error": "Access denied"}), 403

        # Return job status
        response_data = {
            "job_id": job.id,
            "type": job.type.value,
            "status": job.status.value,
            "priority": job.priority.value,
            "progress": job.progress,
            "message": job.message,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
        }

        # Add error message if job failed
        if job.status.value == "failed" and job.error_message:
            response_data["error_message"] = job.error_message

        # Add result if job completed successfully
        if job.status.value == "completed" and job.result:
            response_data["result"] = job.result

        # Add timing information
        if job.elapsed_time():
            response_data["elapsed_seconds"] = job.elapsed_time().total_seconds()

        response_data["total_seconds"] = job.total_time().total_seconds()

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Get job status error: {e}")
        return jsonify({"error": f"Failed to get job status: {str(e)}"}), 500


@jobs_bp.route("", methods=["GET"])
def list_user_jobs():
    """List recent jobs for current user"""
    try:
        if not is_job_system_enabled():
            # Return empty job list instead of error to allow UI to work
            logger.warning("Job system not enabled, returning empty job list")
            return jsonify(
                {
                    "jobs": [],
                    "total": 0,
                    "message": "Job system is starting up",
                    "filters": {
                        "status": request.args.get("status"),
                        "type": request.args.get("type"),
                        "limit": min(
                            100, max(1, request.args.get("limit", 50, type=int))
                        ),
                    },
                }
            )

        # Get user ID from session instead of request attribute
        from flask import session

        user_id = session.get(
            "username"
        )  # Using username as user_id since we don't have numeric IDs
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401

        # Get query parameters
        limit = min(100, max(1, request.args.get("limit", 50, type=int)))
        status_filter = request.args.get("status")
        job_type_filter = request.args.get("type")

        job_queue = asyncio.run(get_job_queue())
        user_jobs = job_queue.get_user_jobs(user_id, limit)

        # Apply filters
        if status_filter:
            user_jobs = [job for job in user_jobs if job.status.value == status_filter]

        if job_type_filter:
            user_jobs = [job for job in user_jobs if job.type.value == job_type_filter]

        # Format response
        jobs_data = []
        for job in user_jobs:
            job_data = {
                "job_id": job.id,
                "type": job.type.value,
                "status": job.status.value,
                "priority": job.priority.value,
                "progress": job.progress,
                "message": job.message,
                "created_at": job.created_at.isoformat(),
                "elapsed_seconds": (
                    job.elapsed_time().total_seconds() if job.elapsed_time() else 0
                ),
            }

            # Add completion time for finished jobs
            if job.completed_at:
                job_data["completed_at"] = job.completed_at.isoformat()

            jobs_data.append(job_data)

        return jsonify(
            {
                "jobs": jobs_data,
                "total": len(jobs_data),
                "filters": {
                    "status": status_filter,
                    "type": job_type_filter,
                    "limit": limit,
                },
            }
        )

    except Exception as e:
        logger.error(f"List jobs error: {e}")
        return jsonify({"error": f"Failed to list jobs: {str(e)}"}), 500


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """Cancel a queued job"""
    try:
        if not is_job_system_enabled():
            return jsonify({"error": "Job system is not enabled"}), 503

        job_queue = asyncio.run(get_job_queue())
        job = job_queue.get_job(job_id)

        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Check permission
        from flask import session

        user_id = session.get("username")
        if job.created_by and job.created_by != user_id:
            return jsonify({"error": "Access denied"}), 403

        # Try to cancel job
        cancelled = asyncio.run(job_queue.cancel_job(job_id))

        if cancelled:
            logger.info(f"Job {job_id} cancelled by user {user_id}")
            return jsonify({"success": True, "message": "Job cancelled successfully"})
        else:
            return (
                jsonify(
                    {
                        "error": "Job cannot be cancelled (may already be processing or completed)"
                    }
                ),
                400,
            )

    except Exception as e:
        logger.error(f"Cancel job error: {e}")
        return jsonify({"error": f"Failed to cancel job: {str(e)}"}), 500


@jobs_bp.route("/enrich-metadata", methods=["POST"])
def enqueue_metadata_enrichment():
    """
    Convenience endpoint for metadata enrichment jobs

    Request body:
    {
        "artist_id": 123,
        "force_refresh": true
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400

        artist_id = data.get("artist_id")
        if not artist_id:
            return jsonify({"error": "artist_id is required"}), 400

        # Create job payload
        job_payload = {
            "artist_id": int(artist_id),
            "force_refresh": data.get("force_refresh", False),
        }

        # Use the generic enqueue endpoint
        request.json = {
            "type": "metadata_enrichment",
            "priority": "normal",
            "payload": job_payload,
        }

        return enqueue_job()

    except ValueError:
        return jsonify({"error": "artist_id must be a valid integer"}), 400
    except Exception as e:
        logger.error(f"Metadata enrichment enqueue error: {e}")
        return (
            jsonify({"error": f"Failed to enqueue metadata enrichment: {str(e)}"}),
            500,
        )


@jobs_bp.route("/types", methods=["GET"])
def get_job_types():
    """Get available job types"""
    job_types = [
        {
            "value": job_type.value,
            "name": job_type.value.replace("_", " ").title(),
            "description": _get_job_type_description(job_type),
        }
        for job_type in JobType
    ]

    return jsonify(
        {
            "job_types": job_types,
            "priorities": [
                {
                    "value": priority.value,
                    "name": priority.name.lower(),
                    "description": _get_priority_description(priority),
                }
                for priority in JobPriority
            ],
        }
    )


def _get_job_type_description(job_type: JobType) -> str:
    """Get human-readable description for job type"""
    descriptions = {
        JobType.METADATA_ENRICHMENT: "Enrich artist metadata from external sources",
        JobType.VIDEO_DOWNLOAD: "Download music videos from external sources",
        JobType.BULK_ARTIST_IMPORT: "Import multiple artists from playlists or sources",
        JobType.THUMBNAIL_GENERATION: "Generate thumbnails for videos",
        JobType.PLAYLIST_SYNC: "Synchronize playlists with external services",
        JobType.BULK_VIDEO_DELETE: "Delete multiple videos in batch",
        JobType.DATABASE_CLEANUP: "Clean up old data and optimize database",
        # Video quality operations
        JobType.VIDEO_QUALITY_ANALYZE: "Analyze video quality and properties",
        JobType.VIDEO_QUALITY_UPGRADE: "Upgrade single video to higher quality",
        JobType.VIDEO_QUALITY_BULK_UPGRADE: "Upgrade multiple videos to higher quality",
        JobType.VIDEO_QUALITY_CHECK_ALL: "Check and verify quality for all videos",
        # Video indexing operations
        JobType.VIDEO_INDEX_ALL: "Index all videos in the music directory",
        JobType.VIDEO_INDEX_SINGLE: "Index a specific video file",
        # Video organization operations
        JobType.VIDEO_ORGANIZE_ALL: "Organize all videos from downloads directory",
        JobType.VIDEO_ORGANIZE_SINGLE: "Organize a specific video file",
        JobType.VIDEO_REORGANIZE_EXISTING: "Reorganize existing videos in music directory",
        # Scheduler operations
        JobType.SCHEDULED_DOWNLOAD: "Scheduled download of wanted videos",
        JobType.SCHEDULED_DISCOVERY: "Scheduled discovery of new videos for artists",
    }
    return descriptions.get(job_type, "Background task")


def _get_priority_description(priority: JobPriority) -> str:
    """Get human-readable description for priority level"""
    descriptions = {
        JobPriority.LOW: "Background maintenance tasks",
        JobPriority.NORMAL: "Regular user-initiated tasks",
        JobPriority.HIGH: "Important user tasks requiring quick processing",
        JobPriority.URGENT: "Critical tasks that should be processed immediately",
    }
    return descriptions.get(priority, "Standard priority")
