"""
FastAPI Metadata Enrichment - Jobs Module
Job management endpoints (job status, cancel, celery health, celery inspect)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.metadata_enrichment.jobs")

# Create router for job management endpoints
router = APIRouter()


@router.get("/job/{job_id}/status")
async def get_job_status(
    job_id: str, current_user: dict = Depends(require_authentication)
):
    """Get status of a Celery metadata enrichment job"""
    # Handle expired/invalid job IDs
    if not job_id or job_id == "undefined":
        return {
            "job_id": job_id,
            "status": "invalid",
            "progress": None,
            "result": {"success": False, "error": "Invalid job ID"},
            "ready": True,
            "successful": False,
            "failed": True,
        }

    try:
        from src.jobs.celery_app import celery_app

        # Get task result
        result = celery_app.AsyncResult(job_id)

        try:
            # Try to get state first, this will fail if result is expired/corrupted
            state = result.state
            logger.info(f"Checking job status for {job_id}, state: {state}")
            status = result.status  # PENDING, PROGRESS, SUCCESS, FAILURE
        except ValueError as state_error:
            # Result expired or doesn't exist in backend
            logger.info(
                f"Job {job_id} result expired or not found in backend: {state_error}"
            )
            return {
                "job_id": job_id,
                "status": "expired",
                "progress": None,
                "result": {
                    "success": False,
                    "error": "Job result expired or not found",
                },
                "ready": True,
                "successful": False,
                "failed": True,
            }
        except Exception as status_error:
            logger.error(f"Error getting result status: {status_error}")
            status = "UNKNOWN"

        task_result = None
        progress_info = None

        try:
            is_ready = result.ready()
        except Exception:
            is_ready = False

        if is_ready:
            try:
                is_successful = result.successful()
            except Exception:
                is_successful = False

            if is_successful:
                try:
                    task_result = result.get()
                except Exception as get_error:
                    task_result = {
                        "success": False,
                        "error": f"Error getting result: {get_error}",
                    }
            else:
                # Task failed - get error info safely
                try:
                    error_info = result.result
                    error_msg = str(error_info) if error_info else "Unknown error"
                except Exception:
                    error_msg = "Task failed with unknown error"

                task_result = {
                    "success": False,
                    "error": error_msg,
                }
        else:
            # Task is still running - check for progress updates
            if status == "PROGRESS":
                try:
                    progress_info = result.info or {}
                except Exception:
                    progress_info = {}

        return {
            "job_id": job_id,
            "status": status.lower(),  # Convert to lowercase for consistency
            "progress": progress_info,
            "result": task_result,
            "ready": is_ready,
            "successful": is_successful if is_ready else None,
            "failed": not is_successful if is_ready else None,
        }

    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {type(e).__name__}: {e}")
        return {
            "job_id": job_id,
            "status": "error",
            "progress": None,
            "result": {"success": False, "error": "Internal server error"},
            "ready": True,
            "successful": False,
            "failed": True,
        }


@router.post("/job/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: dict = Depends(require_authentication)):
    """Cancel a running Celery metadata enrichment job"""
    try:
        from src.jobs.celery_app import job_manager

        # Cancel the task
        success = job_manager.cancel_job(job_id)

        if success:
            return {
                "job_id": job_id,
                "message": "Job cancelled successfully",
                "cancelled": True,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to cancel job - it may have already completed",
            )

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.get("/celery/health")
async def get_celery_health(current_user: dict = Depends(require_authentication)):
    """Get Celery workers health status"""
    try:
        from src.jobs.celery_app import check_celery_health, job_manager

        health = check_celery_health()
        active_jobs = job_manager.get_active_jobs()
        queue_stats = {}

        # Get queue lengths for different queues
        for queue_name in [
            "metadata",
            "video_downloads",
            "image_processing",
            "default",
        ]:
            queue_length = job_manager.get_queue_length(queue_name)
            if queue_length >= 0:  # -1 indicates error
                queue_stats[queue_name] = queue_length

        return {
            **health,
            "active_jobs": active_jobs,
            "queue_stats": queue_stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting Celery health: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get Celery health: {str(e)}"
        )


@router.delete("/celery/clear-completed")
async def clear_completed_jobs(current_user: dict = Depends(require_authentication)):
    """Clear completed job history from Redis result backend"""
    try:
        import redis
        from src.jobs.celery_app import CELERY_RESULT_BACKEND

        # Create Redis connection with timeout
        redis_client = redis.from_url(
            CELERY_RESULT_BACKEND,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=2,
        )

        # Get all task result keys
        pattern = "celery-task-meta-*"
        deleted_count = 0

        # Use SCAN to find and delete keys
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                deleted_count += redis_client.delete(*keys)
            if cursor == 0:
                break

        redis_client.close()

        logger.info(f"Cleared {deleted_count} completed job results from Redis")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Cleared {deleted_count} completed jobs from history",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error clearing completed jobs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clear completed jobs: {str(e)}"
        )


@router.get("/celery/inspect")
async def get_celery_inspect(current_user: dict = Depends(require_authentication)):
    """Get all Celery job information for the jobs dashboard"""
    try:
        import json

        import redis
        from src.jobs.celery_app import CELERY_RESULT_BACKEND, celery_app

        inspect = celery_app.control.inspect()

        # Get active, scheduled, and reserved tasks
        active = inspect.active() or {}
        scheduled = inspect.scheduled() or {}
        reserved = inspect.reserved() or {}

        # Collect all jobs from all workers
        jobs = []

        # Process active tasks
        for worker, tasks in active.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "processing",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        # Process scheduled tasks
        for worker, tasks in scheduled.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "queued",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        # Process reserved tasks
        for worker, tasks in reserved.items():
            for task in tasks:
                jobs.append(
                    {
                        "job_id": task.get("id"),
                        "type": task.get("name", "").replace(".", "_"),
                        "status": "queued",
                        "worker": worker,
                        "created_at": task.get("time_start"),
                        "args": task.get("args"),
                        "kwargs": task.get("kwargs"),
                    }
                )

        # Query Redis for completed job results
        try:
            # Parse Redis URL to extract connection details
            # Format: redis://:password@host:port/db
            redis_url = CELERY_RESULT_BACKEND
            logger.info(f"Connecting to Redis for completed jobs: {redis_url}")

            # Create Redis connection with timeout
            redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=3,
                socket_connect_timeout=2,
            )

            # Get task result keys (limited scan for performance)
            # Celery stores results as celery-task-meta-{task_id}
            pattern = "celery-task-meta-*"
            task_keys = []
            max_jobs = 50  # Limit to 50 most recent completed jobs for performance

            # Use SCAN with limited iterations to avoid blocking
            cursor = 0
            scan_iterations = 0
            max_scan_iterations = 5  # Limit scan iterations to prevent timeout

            while scan_iterations < max_scan_iterations:
                cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
                task_keys.extend(keys)
                scan_iterations += 1

                # Break if we have enough keys or scan is complete
                if cursor == 0 or len(task_keys) >= max_jobs:
                    break

            logger.info(
                f"Found {len(task_keys)} completed job results in Redis after {scan_iterations} scan iterations"
            )

            # Fetch metadata for each completed task (limit to max_jobs)
            for key in task_keys[:max_jobs]:
                try:
                    task_data = redis_client.get(key)
                    if task_data:
                        task_meta = json.loads(task_data)
                        task_id = key.replace("celery-task-meta-", "")

                        # Extract task information
                        status = task_meta.get("status", "UNKNOWN")
                        result = task_meta.get("result", {})
                        task_name = task_meta.get("task", "unknown")

                        # Try to infer task type from result message if task name is unknown
                        if task_name == "unknown" and isinstance(result, dict):
                            message = result.get("message", "")
                            if "download" in message.lower():
                                task_name = "download_processor.process_downloads"
                            elif (
                                "metadata" in message.lower()
                                or "enrich" in message.lower()
                            ):
                                task_name = "metadata_enrichment"
                            elif "index" in message.lower():
                                task_name = "video_index"
                            elif "thumbnail" in message.lower():
                                task_name = "thumbnail_generation"

                        # Map Celery status to dashboard status
                        dashboard_status = "completed"
                        if status == "SUCCESS":
                            dashboard_status = "completed"
                        elif status == "FAILURE":
                            dashboard_status = "failed"
                        elif status == "REVOKED":
                            dashboard_status = "cancelled"

                        # Extract timing information and convert to Unix timestamp
                        date_done = task_meta.get("date_done")
                        completed_timestamp = None
                        if date_done:
                            try:
                                # Convert ISO 8601 string to Unix timestamp (seconds)
                                # Remove microseconds and 'Z' for parsing
                                date_str = date_done.split(".")[
                                    0
                                ]  # Remove microseconds
                                dt = datetime.fromisoformat(date_str)
                                # Assume UTC if no timezone info
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                completed_timestamp = int(dt.timestamp())
                            except Exception as ts_error:
                                logger.debug(
                                    f"Failed to parse timestamp {date_done}: {ts_error}"
                                )
                                # Return None instead of breaking the response
                                completed_timestamp = None

                        jobs.append(
                            {
                                "job_id": task_id,
                                "type": task_name.replace(".", "_"),
                                "status": dashboard_status,
                                "worker": "completed",
                                "created_at": None,  # Not available in result backend
                                "completed_at": completed_timestamp,
                                "result": result,
                                "traceback": task_meta.get("traceback"),
                            }
                        )

                except json.JSONDecodeError as json_error:
                    logger.warning(
                        f"Failed to parse task metadata for {key}: {json_error}"
                    )
                    continue
                except Exception as task_error:
                    logger.warning(f"Error processing task {key}: {task_error}")
                    continue

            redis_client.close()

        except redis.RedisError as redis_error:
            logger.error(f"Redis connection error: {redis_error}")
            # Continue without completed jobs rather than failing completely
        except Exception as completed_error:
            logger.error(f"Error fetching completed jobs from Redis: {completed_error}")
            # Continue without completed jobs rather than failing completely

        return {
            "jobs": jobs,
            "total": len(jobs),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error inspecting Celery jobs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to inspect Celery jobs: {str(e)}"
        )
