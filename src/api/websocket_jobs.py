"""
WebSocket Job Progress API
Real-time job progress endpoints using Flask-SocketIO for live updates.
"""

import logging
from typing import Any, Dict

from flask import Blueprint, current_app, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from src.middleware.simple_auth_middleware import get_current_user
from src.services.job_queue import JobStatus, get_job_queue
from src.services.websocket_job_events import get_job_event_broadcaster

logger = logging.getLogger(__name__)

# Create blueprint for WebSocket job endpoints
websocket_jobs_bp = Blueprint("websocket_jobs", __name__)


def init_websocket_job_endpoints(socketio: SocketIO):
    """Initialize WebSocket endpoints for job progress"""

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection"""
        try:
            user = get_current_user()
            user_id = user.get("user_id") if user else None
            if not user_id:
                logger.warning("WebSocket connection without authentication")
                return False  # Reject connection

            logger.info(f"WebSocket client connected: user {user_id}")
            emit("connected", {"message": "Connected to job progress updates"})

        except Exception as e:
            logger.error(f"Error handling WebSocket connection: {e}")
            return False

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection"""
        try:
            user = get_current_user()
            user_id = user.get("user_id") if user else None
            if user_id:
                # Cleanup will be handled by the broadcaster
                logger.info(f"WebSocket client disconnected: user {user_id}")

        except Exception as e:
            logger.error(f"Error handling WebSocket disconnect: {e}")

    @socketio.on("subscribe_job_progress")
    def handle_job_progress_subscription(data):
        """Handle subscription to specific job progress updates"""
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

            # Verify user has access to this job
            job_queue = current_app.extensions.get("job_queue")
            if job_queue:
                job = job_queue.get_job(job_id)
                if not job:
                    emit("error", {"message": "Job not found"})
                    return

                if job.created_by and job.created_by != user_id:
                    emit("error", {"message": "Access denied"})
                    return

            # Join room for this specific job
            join_room(f"job_{job_id}")

            # Send current job status
            if job_queue and job:
                emit(
                    "job_status",
                    {
                        "job_id": job.id,
                        "type": job.type.value,
                        "status": job.status.value,
                        "progress": job.progress,
                        "message": job.message,
                        "created_at": job.created_at.isoformat(),
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                    },
                )

            emit(
                "subscription_confirmed",
                {
                    "job_id": job_id,
                    "message": f"Subscribed to job {job_id} progress updates",
                },
            )

            logger.debug(f"User {user_id} subscribed to job {job_id} progress")

        except Exception as e:
            logger.error(f"Error handling job progress subscription: {e}")
            emit("error", {"message": "Failed to subscribe to job progress"})

    @socketio.on("unsubscribe_job_progress")
    def handle_job_progress_unsubscription(data):
        """Handle unsubscription from job progress updates"""
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

            # Leave room for this job
            leave_room(f"job_{job_id}")

            emit(
                "unsubscription_confirmed",
                {
                    "job_id": job_id,
                    "message": f"Unsubscribed from job {job_id} progress updates",
                },
            )

            logger.debug(f"User {user_id} unsubscribed from job {job_id} progress")

        except Exception as e:
            logger.error(f"Error handling job progress unsubscription: {e}")
            emit("error", {"message": "Failed to unsubscribe from job progress"})

    @socketio.on("get_user_jobs")
    def handle_get_user_jobs(data):
        """Get current user's recent jobs"""
        try:
            user = get_current_user()
            user_id = user.get("user_id") if user else None
            if not user_id:
                emit("error", {"message": "Authentication required"})
                return

            limit = min(50, max(1, data.get("limit", 10)))
            status_filter = data.get("status")

            job_queue = current_app.extensions.get("job_queue")
            if not job_queue:
                emit("error", {"message": "Job system not available"})
                return

            # Get user's jobs
            user_jobs = job_queue.get_user_jobs(user_id, limit)

            # Apply status filter if provided
            if status_filter:
                try:
                    status_enum = JobStatus(status_filter)
                    user_jobs = [job for job in user_jobs if job.status == status_enum]
                except ValueError:
                    emit(
                        "error", {"message": f"Invalid status filter: {status_filter}"}
                    )
                    return

            # Format jobs for response
            jobs_data = []
            for job in user_jobs:
                jobs_data.append(
                    {
                        "job_id": job.id,
                        "type": job.type.value,
                        "status": job.status.value,
                        "progress": job.progress,
                        "message": job.message,
                        "created_at": job.created_at.isoformat(),
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "error_message": (
                            job.error_message
                            if job.status == JobStatus.FAILED
                            else None
                        ),
                    }
                )

            emit(
                "user_jobs",
                {
                    "jobs": jobs_data,
                    "total": len(jobs_data),
                    "filters": {"status": status_filter, "limit": limit},
                },
            )

            logger.debug(f"Sent {len(jobs_data)} jobs to user {user_id}")

        except Exception as e:
            logger.error(f"Error getting user jobs: {e}")
            emit("error", {"message": "Failed to get user jobs"})

    @socketio.on("get_job_details")
    def handle_get_job_details(data):
        """Get detailed information about a specific job"""
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

            job_queue = current_app.extensions.get("job_queue")
            if not job_queue:
                emit("error", {"message": "Job system not available"})
                return

            job = job_queue.get_job(job_id)
            if not job:
                emit("error", {"message": "Job not found"})
                return

            # Check access permissions
            if job.created_by and job.created_by != user_id:
                emit("error", {"message": "Access denied"})
                return

            # Send detailed job information
            job_details = {
                "job_id": job.id,
                "type": job.type.value,
                "status": job.status.value,
                "priority": job.priority.value,
                "progress": job.progress,
                "message": job.message,
                "payload": job.payload,
                "result": job.result if job.status == JobStatus.COMPLETED else None,
                "error_message": (
                    job.error_message if job.status == JobStatus.FAILED else None
                ),
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
                "tags": job.tags,
            }

            # Add timing information
            if job.elapsed_time():
                job_details["elapsed_seconds"] = job.elapsed_time().total_seconds()

            job_details["total_seconds"] = job.total_time().total_seconds()

            emit("job_details", job_details)

            logger.debug(f"Sent details for job {job_id} to user {user_id}")

        except Exception as e:
            logger.error(f"Error getting job details: {e}")
            emit("error", {"message": "Failed to get job details"})

    logger.info("WebSocket job progress endpoints initialized")


def create_websocket_test_page() -> str:
    """Create a simple test page for WebSocket job progress"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Job Progress WebSocket Test</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .job-update { 
            margin: 10px 0; 
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 5px;
            background: #f9f9f9;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background-color: #f0f0f0;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background-color: #4CAF50;
            transition: width 0.3s ease;
        }
        button { margin: 5px; padding: 10px 15px; }
        #log { 
            height: 400px; 
            overflow-y: scroll; 
            border: 1px solid #ccc; 
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <h1>Job Progress WebSocket Test</h1>
    
    <div>
        <button onclick="connectWebSocket()">Connect</button>
        <button onclick="disconnectWebSocket()">Disconnect</button>
        <button onclick="getUserJobs()">Get My Jobs</button>
    </div>
    
    <div>
        <input type="text" id="jobId" placeholder="Job ID" />
        <button onclick="subscribeToJob()">Subscribe to Job</button>
        <button onclick="unsubscribeFromJob()">Unsubscribe from Job</button>
        <button onclick="getJobDetails()">Get Job Details</button>
    </div>
    
    <div id="jobStatus" style="margin: 20px 0;">
        <h3>Current Job Status</h3>
        <div id="currentJob">No job selected</div>
    </div>
    
    <div id="log"></div>
    
    <script>
        let socket = null;
        let currentJobId = null;
        
        function log(message) {
            const logDiv = document.getElementById('log');
            const timestamp = new Date().toLocaleTimeString();
            logDiv.innerHTML += `[${timestamp}] ${message}<br>`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        function connectWebSocket() {
            if (socket) {
                socket.disconnect();
            }
            
            socket = io();
            
            socket.on('connect', function() {
                log('Connected to WebSocket');
            });
            
            socket.on('disconnect', function() {
                log('Disconnected from WebSocket');
            });
            
            socket.on('job_update', function(data) {
                log(`Job Update: ${JSON.stringify(data)}`);
                updateJobDisplay(data);
            });
            
            socket.on('job_status', function(data) {
                log(`Job Status: ${JSON.stringify(data)}`);
                updateJobDisplay(data);
            });
            
            socket.on('user_jobs', function(data) {
                log(`User Jobs: ${data.jobs.length} jobs found`);
                data.jobs.forEach(job => {
                    log(`  - ${job.job_id}: ${job.type} (${job.status}) ${job.progress}%`);
                });
            });
            
            socket.on('error', function(data) {
                log(`ERROR: ${data.message}`);
            });
            
            socket.on('subscription_confirmed', function(data) {
                log(`Subscribed to job ${data.job_id}`);
                currentJobId = data.job_id;
            });
        }
        
        function disconnectWebSocket() {
            if (socket) {
                socket.disconnect();
                socket = null;
                log('Disconnected');
            }
        }
        
        function getUserJobs() {
            if (!socket) {
                log('Not connected');
                return;
            }
            socket.emit('get_user_jobs', {limit: 10});
        }
        
        function subscribeToJob() {
            const jobId = document.getElementById('jobId').value;
            if (!jobId) {
                log('Please enter a job ID');
                return;
            }
            if (!socket) {
                log('Not connected');
                return;
            }
            socket.emit('subscribe_job_progress', {job_id: jobId});
        }
        
        function unsubscribeFromJob() {
            const jobId = document.getElementById('jobId').value || currentJobId;
            if (!jobId) {
                log('Please enter a job ID');
                return;
            }
            if (!socket) {
                log('Not connected');
                return;
            }
            socket.emit('unsubscribe_job_progress', {job_id: jobId});
        }
        
        function getJobDetails() {
            const jobId = document.getElementById('jobId').value;
            if (!jobId) {
                log('Please enter a job ID');
                return;
            }
            if (!socket) {
                log('Not connected');
                return;
            }
            socket.emit('get_job_details', {job_id: jobId});
        }
        
        function updateJobDisplay(data) {
            const jobDiv = document.getElementById('currentJob');
            if (data.job_id || data.data?.job_id) {
                const job = data.data || data;
                jobDiv.innerHTML = `
                    <div class="job-update">
                        <strong>Job ${job.job_id}</strong><br>
                        Type: ${job.type || 'N/A'}<br>
                        Status: ${job.status}<br>
                        Progress: ${job.progress || 0}%<br>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${job.progress || 0}%"></div>
                        </div>
                        Message: ${job.message || 'N/A'}<br>
                        ${job.error_message ? `Error: ${job.error_message}<br>` : ''}
                    </div>
                `;
            }
        }
    </script>
</body>
</html>
    """
