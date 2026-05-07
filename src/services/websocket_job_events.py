"""
WebSocket Job Event System
Real-time job progress broadcasting using Flask-SocketIO for immediate user feedback.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from flask_socketio import SocketIO, emit, join_room, leave_room
from src.middleware.simple_auth_middleware import get_current_user

from .job_queue import BackgroundJob, JobStatus

logger = logging.getLogger(__name__)


class JobEventBroadcaster:
    """
    Manages WebSocket broadcasting of job progress updates and status changes
    """

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.user_subscriptions: Dict[str, Set[str]] = {}  # user_id -> set of job_ids
        self.job_subscribers: Dict[str, Set[str]] = {}  # job_id -> set of user_ids
        self._lock = asyncio.Lock()

        # Register SocketIO event handlers
        self.register_socketio_handlers()

        logger.info("Job event broadcaster initialized")

    def register_socketio_handlers(self):
        """Register WebSocket event handlers for job subscriptions"""

        @self.socketio.on("subscribe_job")
        def handle_job_subscription(data):
            """Handle user subscribing to job updates"""
            try:
                job_id = data.get("job_id")
                if not job_id:
                    emit("error", {"message": "job_id is required"})
                    return

                user = get_current_user()
                user_id = user.get("user_id") if user else None
                if not user_id:
                    emit("error", {"message": "Authentication required"})
                    return

                # Subscribe user to job updates
                self.subscribe_user_to_job(user_id, job_id)

                # Join SocketIO room for this job
                join_room(f"job_{job_id}")

                emit(
                    "subscription_confirmed",
                    {"job_id": job_id, "message": "Subscribed to job updates"},
                )

                logger.debug(f"User {user_id} subscribed to job {job_id}")

            except Exception as e:
                logger.error(f"Error handling job subscription: {e}")
                emit("error", {"message": "Failed to subscribe to job updates"})

        @self.socketio.on("unsubscribe_job")
        def handle_job_unsubscription(data):
            """Handle user unsubscribing from job updates"""
            try:
                job_id = data.get("job_id")
                if not job_id:
                    emit("error", {"message": "job_id is required"})
                    return

                user = get_current_user()
                user_id = user.get("user_id") if user else None
                if not user_id:
                    emit("error", {"message": "Authentication required"})
                    return

                # Unsubscribe user from job updates
                self.unsubscribe_user_from_job(user_id, job_id)

                # Leave SocketIO room for this job
                leave_room(f"job_{job_id}")

                emit(
                    "unsubscription_confirmed",
                    {"job_id": job_id, "message": "Unsubscribed from job updates"},
                )

                logger.debug(f"User {user_id} unsubscribed from job {job_id}")

            except Exception as e:
                logger.error(f"Error handling job unsubscription: {e}")
                emit("error", {"message": "Failed to unsubscribe from job updates"})

        @self.socketio.on("get_job_status")
        def handle_job_status_request(data):
            """Handle request for current job status"""
            try:
                job_id = data.get("job_id")
                if not job_id:
                    emit("error", {"message": "job_id is required"})
                    return

                user = get_current_user()
                user_id = user.get("user_id") if user else None
                if not user_id:
                    emit("error", {"message": "Authentication required"})
                    return

                # Get job status from queue (this will be implemented)
                # For now, emit a placeholder response
                emit(
                    "job_status",
                    {
                        "job_id": job_id,
                        "status": "pending",
                        "message": "Job status retrieval not yet implemented",
                    },
                )

            except Exception as e:
                logger.error(f"Error handling job status request: {e}")
                emit("error", {"message": "Failed to get job status"})

        @self.socketio.on("disconnect")
        def handle_disconnect():
            """Clean up user subscriptions on disconnect"""
            try:
                user = get_current_user()
                user_id = user.get("user_id") if user else None
                if user_id:
                    self.cleanup_user_subscriptions(user_id)
                    logger.debug(
                        f"Cleaned up subscriptions for disconnected user {user_id}"
                    )
            except Exception as e:
                logger.error(f"Error handling disconnect: {e}")

    def subscribe_user_to_job(self, user_id: str, job_id: str):
        """Subscribe a user to job updates"""
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        self.user_subscriptions[user_id].add(job_id)

        if job_id not in self.job_subscribers:
            self.job_subscribers[job_id] = set()
        self.job_subscribers[job_id].add(user_id)

    def unsubscribe_user_from_job(self, user_id: str, job_id: str):
        """Unsubscribe a user from job updates"""
        if user_id in self.user_subscriptions:
            self.user_subscriptions[user_id].discard(job_id)
            if not self.user_subscriptions[user_id]:
                del self.user_subscriptions[user_id]

        if job_id in self.job_subscribers:
            self.job_subscribers[job_id].discard(user_id)
            if not self.job_subscribers[job_id]:
                del self.job_subscribers[job_id]

    def cleanup_user_subscriptions(self, user_id: str):
        """Remove all subscriptions for a user (called on disconnect)"""
        if user_id not in self.user_subscriptions:
            return

        # Remove user from all job subscriber lists
        for job_id in self.user_subscriptions[user_id]:
            if job_id in self.job_subscribers:
                self.job_subscribers[job_id].discard(user_id)
                if not self.job_subscribers[job_id]:
                    del self.job_subscribers[job_id]

        # Remove user's subscriptions
        del self.user_subscriptions[user_id]

    def broadcast_job_update(self, job_id: str, event_type: str, data: Dict[str, Any]):
        """Broadcast job update to all subscribed users"""
        try:
            # Emit to SocketIO room for this job
            self.socketio.emit(
                "job_update",
                {
                    "job_id": job_id,
                    "event_type": event_type,
                    "data": data,
                    "timestamp": data.get("timestamp"),
                },
                room=f"job_{job_id}",
            )

            logger.debug(
                f"Broadcasted {event_type} for job {job_id} to room job_{job_id}"
            )

        except Exception as e:
            logger.error(f"Error broadcasting job update: {e}")

    def broadcast_job_progress(self, job: BackgroundJob):
        """Broadcast job progress update"""
        self.broadcast_job_update(
            job.id,
            "progress",
            {
                "job_id": job.id,
                "progress": job.progress,
                "message": job.message,
                "status": job.status.value,
                "timestamp": job.created_at.isoformat(),
            },
        )

    def broadcast_job_status_change(self, job: BackgroundJob, old_status: JobStatus):
        """Broadcast job status change"""
        self.broadcast_job_update(
            job.id,
            "status_change",
            {
                "job_id": job.id,
                "old_status": old_status.value,
                "new_status": job.status.value,
                "message": job.message,
                "progress": job.progress,
                "timestamp": job.created_at.isoformat(),
                # Include additional data based on status
                "error_message": (
                    job.error_message if job.status == JobStatus.FAILED else None
                ),
                "result": job.result if job.status == JobStatus.COMPLETED else None,
            },
        )

    def broadcast_job_completed(self, job: BackgroundJob):
        """Broadcast job completion with results"""
        self.broadcast_job_update(
            job.id,
            "completed",
            {
                "job_id": job.id,
                "status": job.status.value,
                "result": job.result,
                "progress": 100,
                "message": job.message or "Job completed successfully",
                "completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "elapsed_time": (
                    job.elapsed_time().total_seconds() if job.elapsed_time() else None
                ),
                "timestamp": job.created_at.isoformat(),
            },
        )

    def broadcast_job_failed(self, job: BackgroundJob):
        """Broadcast job failure with error details"""
        self.broadcast_job_update(
            job.id,
            "failed",
            {
                "job_id": job.id,
                "status": job.status.value,
                "error_message": job.error_message,
                "progress": job.progress,
                "message": job.message or "Job failed",
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
                "timestamp": job.created_at.isoformat(),
            },
        )

    def get_subscription_stats(self) -> Dict[str, Any]:
        """Get statistics about current subscriptions"""
        return {
            "active_users": len(self.user_subscriptions),
            "subscribed_jobs": len(self.job_subscribers),
            "total_subscriptions": sum(
                len(jobs) for jobs in self.user_subscriptions.values()
            ),
        }


# Global broadcaster instance
_job_broadcaster: Optional[JobEventBroadcaster] = None


def init_job_event_broadcaster(socketio: SocketIO) -> JobEventBroadcaster:
    """Initialize the global job event broadcaster"""
    global _job_broadcaster
    if _job_broadcaster is None:
        _job_broadcaster = JobEventBroadcaster(socketio)
        logger.info("Job event broadcaster initialized globally")
    return _job_broadcaster


def get_job_event_broadcaster() -> Optional[JobEventBroadcaster]:
    """Get the global job event broadcaster instance"""
    return _job_broadcaster


def broadcast_job_event(job_id: str, event_type: str, data: Dict[str, Any]):
    """Convenience function to broadcast job events"""
    broadcaster = get_job_event_broadcaster()
    if broadcaster:
        broadcaster.broadcast_job_update(job_id, event_type, data)
    else:
        logger.warning("Job event broadcaster not initialized")
