"""
Background Job Queue System
Core infrastructure for processing long-running tasks in the background with real-time progress updates.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobType(Enum):
    """Types of background jobs that can be processed"""

    METADATA_ENRICHMENT = "metadata_enrichment"
    VIDEO_DOWNLOAD = "video_download"
    BULK_ARTIST_IMPORT = "bulk_artist_import"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    PLAYLIST_SYNC = "playlist_sync"
    BULK_VIDEO_DELETE = "bulk_video_delete"
    DATABASE_CLEANUP = "database_cleanup"
    # Video quality operations
    VIDEO_QUALITY_ANALYZE = "video_quality_analyze"
    VIDEO_QUALITY_UPGRADE = "video_quality_upgrade"
    VIDEO_QUALITY_BULK_UPGRADE = "video_quality_bulk_upgrade"
    VIDEO_QUALITY_CHECK_ALL = "video_quality_check_all"
    # Video indexing operations
    VIDEO_INDEX_ALL = "video_index_all"
    VIDEO_INDEX_SINGLE = "video_index_single"
    # Video organization operations
    VIDEO_ORGANIZE_ALL = "video_organize_all"
    VIDEO_ORGANIZE_SINGLE = "video_organize_single"
    VIDEO_REORGANIZE_EXISTING = "video_reorganize_existing"
    # Scheduler operations
    SCHEDULED_DOWNLOAD = "scheduled_download"
    SCHEDULED_DISCOVERY = "scheduled_discovery"


class JobStatus(Enum):
    """Job processing status"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels for queue ordering"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class BackgroundJob:
    """
    Represents a background job with all necessary metadata for processing and tracking
    """

    # Core job identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: JobType = JobType.METADATA_ENRICHMENT
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.NORMAL

    # Job data and state
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    progress: int = 0  # 0-100
    message: str = ""
    error_message: Optional[str] = None

    # Timing information
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Retry configuration
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: int = 60  # seconds

    # User and tracking
    created_by: Optional[str] = None
    tags: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert enums to strings
        data["type"] = self.type.value
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        # Convert datetime objects to ISO strings
        for field_name in ["created_at", "started_at", "completed_at"]:
            if data[field_name]:
                data[field_name] = data[field_name].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackgroundJob":
        """Create job from dictionary"""
        # Convert string enums back to enum objects
        if "type" in data:
            data["type"] = JobType(data["type"])
        if "status" in data:
            data["status"] = JobStatus(data["status"])
        if "priority" in data:
            data["priority"] = JobPriority(data["priority"])

        # Convert ISO strings back to datetime objects
        for field_name in ["created_at", "started_at", "completed_at"]:
            if data.get(field_name):
                data[field_name] = datetime.fromisoformat(data[field_name])

        return cls(**data)

    def elapsed_time(self) -> Optional[timedelta]:
        """Get elapsed time since job started"""
        if self.started_at:
            end_time = self.completed_at or datetime.utcnow()
            return end_time - self.started_at
        return None

    def total_time(self) -> timedelta:
        """Get total time since job was created"""
        end_time = self.completed_at or datetime.utcnow()
        return end_time - self.created_at


class JobQueue:
    """
    Async job queue with priority handling, subscriber notifications, and job lifecycle management
    """

    def __init__(self):
        self._jobs: Dict[str, BackgroundJob] = {}
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

        # Queue statistics
        self._stats = {
            "jobs_queued": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "total_processing_time": 0.0,
        }

    async def enqueue(self, job: BackgroundJob) -> str:
        """Add job to queue and return job ID"""
        async with self._lock:
            self._jobs[job.id] = job

            # Priority queue uses tuples: (priority, creation_time, job)
            # Lower priority number = higher priority in queue
            priority_value = job.priority.value * -1  # Reverse for proper ordering
            await self._queue.put((priority_value, time.time(), job))

            self._stats["jobs_queued"] += 1

            logger.info(
                f"Queued job {job.id} ({job.type.value}) with priority {job.priority.value}"
            )
            await self._notify_subscribers(
                job.id,
                "job_queued",
                {
                    "job_id": job.id,
                    "type": job.type.value,
                    "priority": job.priority.value,
                    "created_at": job.created_at.isoformat(),
                },
            )

            return job.id

    async def get_next_job(self) -> Optional[BackgroundJob]:
        """Get next job from queue (blocks if empty)"""
        try:
            # Wait for job with 1 second timeout to allow worker shutdown
            priority, created_time, job = await asyncio.wait_for(
                self._queue.get(), timeout=1.0
            )

            async with self._lock:
                # Mark job as processing
                job.status = JobStatus.PROCESSING
                job.started_at = datetime.utcnow()

                logger.info(f"Started processing job {job.id} ({job.type.value})")
                await self._notify_subscribers(
                    job.id,
                    "job_started",
                    {"job_id": job.id, "started_at": job.started_at.isoformat()},
                )

                return job

        except asyncio.TimeoutError:
            return None

    async def update_progress(self, job_id: str, progress: int, message: str = ""):
        """Update job progress and notify subscribers"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.progress = max(0, min(100, progress))  # Clamp to 0-100
                job.message = message

                logger.debug(f"Job {job_id} progress: {progress}% - {message}")
                await self._notify_subscribers(
                    job_id,
                    "job_progress",
                    {
                        "job_id": job_id,
                        "progress": job.progress,
                        "message": job.message,
                    },
                )

                # Broadcast to WebSocket clients
                self._broadcast_websocket_update(job, "progress")

    async def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None):
        """Mark job as completed with optional result data"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.progress = 100
                job.message = "Completed successfully"
                job.result = result or {}

                # Update statistics
                self._stats["jobs_completed"] += 1
                if job.elapsed_time():
                    self._stats[
                        "total_processing_time"
                    ] += job.elapsed_time().total_seconds()

                logger.info(
                    f"Completed job {job_id} ({job.type.value}) in {job.elapsed_time()}"
                )
                await self._notify_subscribers(
                    job_id,
                    "job_completed",
                    {
                        "job_id": job_id,
                        "completed_at": job.completed_at.isoformat(),
                        "elapsed_time": (
                            job.elapsed_time().total_seconds()
                            if job.elapsed_time()
                            else 0
                        ),
                        "result": job.result,
                    },
                )

                # Broadcast to WebSocket clients
                self._broadcast_websocket_update(job, "completed")

    async def fail_job(self, job_id: str, error: str, retry: bool = True):
        """Mark job as failed and optionally retry"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.error_message = error

                if retry and job.retry_count < job.max_retries:
                    # Retry logic
                    job.status = JobStatus.RETRYING
                    job.retry_count += 1
                    job.message = f"Retrying... (attempt {job.retry_count + 1}/{job.max_retries + 1})"

                    logger.warning(
                        f"Job {job_id} failed, retrying in {job.retry_delay}s (attempt {job.retry_count}): {error}"
                    )

                    # Schedule retry
                    await asyncio.sleep(
                        job.retry_delay * job.retry_count
                    )  # Exponential backoff

                    # Reset job state for retry
                    job.status = JobStatus.QUEUED
                    job.started_at = None
                    job.progress = 0
                    job.message = ""

                    # Re-enqueue
                    priority_value = job.priority.value * -1
                    await self._queue.put((priority_value, time.time(), job))

                    await self._notify_subscribers(
                        job_id,
                        "job_retrying",
                        {
                            "job_id": job_id,
                            "retry_count": job.retry_count,
                            "error": error,
                            "next_attempt_in": job.retry_delay * job.retry_count,
                        },
                    )
                else:
                    # Final failure
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.utcnow()

                    self._stats["jobs_failed"] += 1

                    logger.error(
                        f"Job {job_id} failed permanently after {job.retry_count} retries: {error}"
                    )
                    await self._notify_subscribers(
                        job_id,
                        "job_failed",
                        {
                            "job_id": job_id,
                            "completed_at": job.completed_at.isoformat(),
                            "error": error,
                            "retry_count": job.retry_count,
                        },
                    )

                    # Broadcast to WebSocket clients
                    self._broadcast_websocket_update(job, "failed")

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                if job.status == JobStatus.QUEUED:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.utcnow()
                    job.message = "Cancelled by user"

                    logger.info(f"Cancelled job {job_id}")
                    await self._notify_subscribers(
                        job_id,
                        "job_cancelled",
                        {
                            "job_id": job_id,
                            "cancelled_at": job.completed_at.isoformat(),
                        },
                    )
                    return True
        return False

    def get_job(self, job_id: str) -> Optional[BackgroundJob]:
        """Get job by ID"""
        return self._jobs.get(job_id)

    def get_jobs_by_status(self, status: JobStatus) -> List[BackgroundJob]:
        """Get all jobs with specific status"""
        return [job for job in self._jobs.values() if job.status == status]

    def get_user_jobs(self, user_id: str, limit: int = 50) -> List[BackgroundJob]:
        """Get recent jobs for specific user"""
        user_jobs = [job for job in self._jobs.values() if job.created_by == user_id]
        # Sort by creation time, most recent first
        user_jobs.sort(key=lambda j: j.created_at, reverse=True)
        return user_jobs[:limit]

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        active_jobs = len(
            [j for j in self._jobs.values() if j.status == JobStatus.PROCESSING]
        )
        queued_jobs = len(
            [j for j in self._jobs.values() if j.status == JobStatus.QUEUED]
        )

        avg_processing_time = 0
        if self._stats["jobs_completed"] > 0:
            avg_processing_time = (
                self._stats["total_processing_time"] / self._stats["jobs_completed"]
            )

        return {
            "total_jobs": len(self._jobs),
            "active_jobs": active_jobs,
            "queued_jobs": queued_jobs,
            "completed_jobs": self._stats["jobs_completed"],
            "failed_jobs": self._stats["jobs_failed"],
            "average_processing_time": avg_processing_time,
            "queue_size": self._queue.qsize(),
        }

    async def subscribe(self, job_id: str, callback: Callable):
        """Subscribe to job events"""
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(callback)

    async def unsubscribe(self, job_id: str, callback: Callable):
        """Unsubscribe from job events"""
        if job_id in self._subscribers:
            if callback in self._subscribers[job_id]:
                self._subscribers[job_id].remove(callback)

    async def _notify_subscribers(
        self, job_id: str, event_type: str, data: Dict[str, Any]
    ):
        """Notify all subscribers of job events"""
        if job_id in self._subscribers:
            for callback in self._subscribers[job_id]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(job_id, event_type, data)
                    else:
                        callback(job_id, event_type, data)
                except Exception as e:
                    logger.error(f"Error calling subscriber callback: {e}")

    async def cleanup_old_jobs(self, days_to_keep: int = 7):
        """Remove old completed/failed jobs"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        removed_count = 0

        async with self._lock:
            jobs_to_remove = []
            for job_id, job in self._jobs.items():
                if (
                    job.status
                    in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
                    and job.completed_at
                    and job.completed_at < cutoff_date
                ):
                    jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self._jobs[job_id]
                # Clean up subscribers too
                if job_id in self._subscribers:
                    del self._subscribers[job_id]
                removed_count += 1

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old jobs")

        return removed_count

    def _broadcast_websocket_update(self, job: BackgroundJob, event_type: str):
        """Broadcast job update via WebSocket (non-blocking)"""
        try:
            # Use FastAPI WebSocket manager instead of Flask-SocketIO
            from src.api.fastapi.websocket_jobs import websocket_manager

            # Prepare progress data based on event type
            if event_type == "progress":
                progress_data = {
                    "job_id": job.id,
                    "type": job.type.value,
                    "status": job.status.value,
                    "progress": job.progress,
                    "message": job.message,
                    "started_at": (
                        job.started_at.isoformat() if job.started_at else None
                    ),
                }
            elif event_type == "completed":
                progress_data = {
                    "job_id": job.id,
                    "type": job.type.value,
                    "status": "completed",
                    "progress": 100,
                    "message": "Job completed successfully",
                    "started_at": (
                        job.started_at.isoformat() if job.started_at else None
                    ),
                    "completed_at": (
                        job.completed_at.isoformat() if job.completed_at else None
                    ),
                    "result": job.result,
                }
            elif event_type == "failed":
                progress_data = {
                    "job_id": job.id,
                    "type": job.type.value,
                    "status": "failed",
                    "progress": 0,
                    "message": job.error_message or "Job failed",
                    "started_at": (
                        job.started_at.isoformat() if job.started_at else None
                    ),
                    "error": job.error_message,
                }
            else:
                # Unknown event type, skip
                return

            # Use asyncio to run the async broadcast method
            import asyncio

            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule the coroutine
                    asyncio.create_task(
                        websocket_manager._broadcast_job_update(job.id, progress_data)
                    )
                else:
                    # If no loop is running, run it
                    loop.run_until_complete(
                        websocket_manager._broadcast_job_update(job.id, progress_data)
                    )
            except RuntimeError:
                # No event loop in thread, create a new one
                asyncio.run(
                    websocket_manager._broadcast_job_update(job.id, progress_data)
                )

        except ImportError:
            # WebSocket system not available
            pass
        except Exception as e:
            logger.warning(f"Failed to broadcast WebSocket update: {e}")
            import traceback

            logger.debug(
                f"WebSocket broadcast error traceback: {traceback.format_exc()}"
            )


# Global job queue instance
_global_job_queue: Optional[JobQueue] = None
_queue_lock = asyncio.Lock()


async def get_job_queue() -> JobQueue:
    """Get global job queue instance"""
    global _global_job_queue
    if _global_job_queue is None:
        async with _queue_lock:
            if _global_job_queue is None:
                _global_job_queue = JobQueue()
                logger.info("Created global job queue instance")
    return _global_job_queue


async def cleanup_job_queue():
    """Cleanup global job queue - call on application shutdown"""
    global _global_job_queue
    if _global_job_queue:
        # Perform any necessary cleanup
        await _global_job_queue.cleanup_old_jobs(
            days_to_keep=1
        )  # Aggressive cleanup on shutdown
        logger.info("Job queue cleanup completed")
