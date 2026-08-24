"""
FastAPI WebSocket Job Progress System
Real-time job progress streaming for Celery background jobs
Phase 2: Media Processing Optimization - Week 17
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from src.api.fastapi.auth_dependencies import require_authentication
from src.jobs.redis_manager import redis_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.websocket.jobs")


class WebSocketJobManager:
    """
    Manages WebSocket connections for real-time Celery job progress updates
    """

    def __init__(self):
        # Track active connections per user
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # Track job subscriptions per connection
        self.connection_subscriptions: Dict[WebSocket, Set[str]] = {}
        # Track which connections are subscribed to each job
        self.job_subscribers: Dict[str, Set[WebSocket]] = {}

        # Redis pub/sub for job progress updates
        self.redis_subscriber = None
        self.subscription_task: Optional[asyncio.Task] = None

        logger.info("WebSocket Job Manager initialized")

    async def start_redis_subscriber(self):
        """Start Redis pub/sub subscriber for job progress updates"""
        try:
            # Ensure Redis connection is available
            if not redis_manager.ensure_connection():
                logger.warning("Redis not available, WebSocket updates will be limited")
                return

            self.redis_subscriber = redis_manager.redis_client.pubsub()
            self.redis_subscriber.psubscribe("progress:*")

            self.subscription_task = asyncio.create_task(self._process_redis_messages())
            logger.info(
                "📡 Redis subscriber started for WebSocket job updates - listening on 'progress:*'"
            )

        except Exception as e:
            logger.error(f"❌ Failed to start Redis subscriber: {e}")

    async def stop_redis_subscriber(self):
        """Stop Redis pub/sub subscriber"""
        try:
            if self.subscription_task:
                self.subscription_task.cancel()

            if self.redis_subscriber:
                self.redis_subscriber.punsubscribe("progress:*")
                self.redis_subscriber.close()

            logger.info("✅ Redis subscriber stopped")

        except Exception as e:
            logger.error(f"❌ Error stopping Redis subscriber: {e}")

    async def _process_redis_messages(self):
        """Process incoming Redis pub/sub messages"""
        try:
            while True:
                # Use sync get_message since we're using sync Redis client
                message = self.redis_subscriber.get_message(
                    ignore_subscribe_messages=True, timeout=0.1
                )
                if message:
                    await self._handle_redis_message(message)
                await asyncio.sleep(0.01)  # Small delay to prevent busy loop

        except asyncio.CancelledError:
            logger.info("🚫 Redis message processing cancelled")
        except Exception as e:
            logger.error(f"❌ Error processing Redis messages: {e}")

    async def _handle_redis_message(self, message):
        """Handle individual Redis pub/sub message"""
        try:
            if message["type"] == "pmessage":
                # Handle both byte and string data types
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()

                # Extract job ID from channel (format: progress:job_id)
                if channel.startswith("progress:"):
                    job_id = channel[9:]  # Remove 'progress:' prefix

                    # Parse progress data
                    try:
                        progress_data = json.loads(data)
                        logger.debug(
                            f"📡 WEBSOCKET RECEIVED: Job {job_id} progress update: {progress_data.get('progress', 0)}% - {progress_data.get('message', '')}"
                        )
                        await self._broadcast_job_update(job_id, progress_data)
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ Invalid JSON in Redis message: {data}")

        except Exception as e:
            logger.error(f"❌ Error handling Redis message: {e}")

    async def _broadcast_job_update(self, job_id: str, progress_data: Dict[str, Any]):
        """Broadcast job update to all subscribed connections"""
        if job_id not in self.job_subscribers:
            logger.debug(f"📡 No subscribers for job {job_id} - skipping broadcast")
            return

        # Prepare message
        message = {
            "type": "job_update",
            "job_id": job_id,
            "data": progress_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Send to all subscribers
        disconnected_connections = set()
        successful_sends = 0
        for connection in self.job_subscribers[job_id]:
            try:
                await connection.send_json(message)
                successful_sends += 1
            except Exception as send_error:
                logger.debug(f"❌ WebSocket send failed for job {job_id}: {send_error}")
                disconnected_connections.add(connection)

        logger.debug(
            f"📡 WEBSOCKET BROADCAST: Job {job_id} update sent to {successful_sends} clients: {progress_data.get('progress', 0)}% - {progress_data.get('message', '')}"
        )

        # Clean up disconnected connections
        for connection in disconnected_connections:
            await self._cleanup_connection(connection)

    async def connect_user(self, websocket: WebSocket, user_id: Optional[str] = None):
        """Handle new WebSocket connection"""
        try:
            await websocket.accept()

            if user_id:
                if user_id not in self.user_connections:
                    self.user_connections[user_id] = set()
                self.user_connections[user_id].add(websocket)

            self.connection_subscriptions[websocket] = set()

            # Send welcome message
            await websocket.send_json(
                {
                    "type": "connected",
                    "message": "Connected to job progress updates",
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            logger.info(f"WebSocket connected: user {user_id}")

        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}")
            await websocket.close()

    async def disconnect_user(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        await self._cleanup_connection(websocket)
        logger.info("WebSocket disconnected")

    async def _cleanup_connection(self, websocket: WebSocket):
        """Clean up connection subscriptions"""
        try:
            # Remove from user connections
            for user_id, connections in self.user_connections.items():
                connections.discard(websocket)

            # Remove from job subscriptions
            if websocket in self.connection_subscriptions:
                subscribed_jobs = self.connection_subscriptions[websocket]
                for job_id in subscribed_jobs:
                    if job_id in self.job_subscribers:
                        self.job_subscribers[job_id].discard(websocket)
                        if not self.job_subscribers[job_id]:
                            del self.job_subscribers[job_id]

                del self.connection_subscriptions[websocket]

        except Exception as e:
            logger.error(f"Error cleaning up connection: {e}")

    async def subscribe_to_job(self, websocket: WebSocket, job_id: str) -> bool:
        """Subscribe connection to job progress updates"""
        try:
            # Add to connection subscriptions
            if websocket not in self.connection_subscriptions:
                self.connection_subscriptions[websocket] = set()
            self.connection_subscriptions[websocket].add(job_id)

            # Add to job subscribers
            if job_id not in self.job_subscribers:
                self.job_subscribers[job_id] = set()
            self.job_subscribers[job_id].add(websocket)

            # Send current job status if available
            current_status = await self._get_job_status(job_id)
            if current_status:
                await websocket.send_json(
                    {
                        "type": "job_status",
                        "job_id": job_id,
                        "data": current_status,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            logger.debug(f"Subscribed WebSocket to job {job_id}")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to job {job_id}: {e}")
            return False

    async def unsubscribe_from_job(self, websocket: WebSocket, job_id: str) -> bool:
        """Unsubscribe connection from job progress updates"""
        try:
            # Remove from connection subscriptions
            if websocket in self.connection_subscriptions:
                self.connection_subscriptions[websocket].discard(job_id)

            # Remove from job subscribers
            if job_id in self.job_subscribers:
                self.job_subscribers[job_id].discard(websocket)
                if not self.job_subscribers[job_id]:
                    del self.job_subscribers[job_id]

            logger.debug(f"Unsubscribed WebSocket from job {job_id}")
            return True

        except Exception as e:
            logger.error(f"Error unsubscribing from job {job_id}: {e}")
            return False

    async def _get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current job status from Redis"""
        try:
            if not redis_manager.redis_client:
                return None

            # Get job progress from Redis
            progress_key = f"job_progress:{job_id}"
            progress_data = redis_manager.redis_client.get(progress_key)

            if progress_data:
                return json.loads(progress_data)

            return None

        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {e}")
            return None

    async def get_active_jobs(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get list of active jobs for user"""
        try:
            # This would typically query the job system for active jobs
            # For now, return basic stats
            return {
                "active_connections": len(self.connection_subscriptions),
                "subscribed_jobs": len(self.job_subscribers),
                "user_connections": (
                    len(self.user_connections.get(user_id, [])) if user_id else 0
                ),
            }

        except Exception as e:
            logger.error(f"Error getting active jobs: {e}")
            return {}


# Global WebSocket manager instance
websocket_manager = WebSocketJobManager()


async def get_websocket_manager():
    """Dependency to get WebSocket manager"""
    return websocket_manager


async def _get_websocket_authenticated_user(
    websocket: WebSocket,
) -> Optional[Dict[str, Any]]:
    """Resolve the authenticated user for a WebSocket connection.

    Mirrors auth_dependencies.get_current_user_session() +
    require_authentication(), which can't be reused directly here:
    get_current_user_session() is typed to Request, and FastAPI's
    WebSocket routes inject a WebSocket-typed scope, not Request, so a
    Depends() chain built on that type won't resolve in a websocket
    route (same constraint documented in monitoring_dashboard.py's own
    _get_websocket_admin_user, which this mirrors). WebSocket, like
    Request, inherits .cookies from Starlette's HTTPConnection, so the
    same session_token lookup and SessionStore.validate_session() call
    work unchanged.

    Any authenticated role passes (unlike monitoring_dashboard.py's
    admin-only gate) -- job/download progress is regular library
    content, not host-system metrics.
    """
    try:
        session_token = websocket.cookies.get("session_token")
        if not session_token:
            return None
        from src.services.session_store import SessionStore

        user_data = SessionStore.validate_session(session_token)
        if user_data and user_data.get("authenticated"):
            return user_data
        return None
    except Exception as e:
        logger.error(f"Error resolving WebSocket session: {e}")
        return None


async def websocket_job_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time job progress updates.

    Previously accepted every connection unauthenticated ("Authentication
    simplified for now") -- once connected, the server's Redis subscriber
    broadcasts real-time progress for every Celery job in the system to
    every connected client with no further gating, so this was a
    complete, unauthenticated exposure of live download/job activity.
    Found via a systematic re-audit of #392's actual current status.
    """
    user = await _get_websocket_authenticated_user(websocket)
    if not user:
        await websocket.close(code=1008)
        return

    user_id = user.get("user_id")

    try:
        await websocket_manager.connect_user(websocket, user_id)

        # Start Redis subscriber if not already running (fallback)
        # Note: This should normally be started during app startup now
        if not websocket_manager.subscription_task:
            logger.info(
                "🔄 Starting Redis subscriber as fallback (should have started at app startup)"
            )
            await websocket_manager.start_redis_subscriber()

        while True:
            # Listen for client messages
            try:
                data = await websocket.receive_json()
                await handle_websocket_message(websocket, data, user_id)
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket_manager.disconnect_user(websocket)


async def websocket_test_page(
    current_user: dict = Depends(require_authentication),
):
    """Test page for WebSocket job progress"""
    return get_websocket_test_page()


def setup_websocket_routes(app: FastAPI):
    """Setup WebSocket routes for job progress"""
    app.add_api_websocket_route("/ws/jobs", websocket_job_progress)
    app.add_api_route(
        "/ws/jobs/test",
        websocket_test_page,
        methods=["GET"],
        response_class=HTMLResponse,
    )


async def handle_websocket_message(
    websocket: WebSocket, data: Dict[str, Any], user_id: Optional[str]
):
    """Handle incoming WebSocket messages from clients"""
    try:
        message_type = data.get("type")

        if message_type == "subscribe_job":
            job_id = data.get("job_id")
            if job_id:
                success = await websocket_manager.subscribe_to_job(websocket, job_id)
                await websocket.send_json(
                    {
                        "type": "subscription_response",
                        "job_id": job_id,
                        "success": success,
                        "message": f"{'Subscribed to' if success else 'Failed to subscribe to'} job {job_id}",
                    }
                )

        elif message_type == "unsubscribe_job":
            job_id = data.get("job_id")
            if job_id:
                success = await websocket_manager.unsubscribe_from_job(
                    websocket, job_id
                )
                await websocket.send_json(
                    {
                        "type": "unsubscription_response",
                        "job_id": job_id,
                        "success": success,
                        "message": f"{'Unsubscribed from' if success else 'Failed to unsubscribe from'} job {job_id}",
                    }
                )

        elif message_type == "get_active_jobs":
            jobs = await websocket_manager.get_active_jobs(user_id)
            await websocket.send_json(
                {
                    "type": "active_jobs",
                    "data": jobs,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

        elif message_type == "ping":
            await websocket.send_json(
                {"type": "pong", "timestamp": datetime.utcnow().isoformat()}
            )

        else:
            await websocket.send_json(
                {"type": "error", "message": f"Unknown message type: {message_type}"}
            )

    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        await websocket.send_json(
            {"type": "error", "message": "Failed to process message"}
        )


def get_websocket_test_page() -> str:
    """Generate HTML test page for WebSocket job progress"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>FastAPI WebSocket Job Progress Test</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #fff; }
        .container { max-width: 1000px; margin: 0 auto; }
        .controls { margin: 20px 0; padding: 20px; background: #2a2a2a; border-radius: 8px; }
        .controls button { margin: 5px; padding: 10px 15px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .controls button:hover { background: #2563eb; }
        .controls input { padding: 8px; margin: 5px; border: 1px solid #444; background: #333; color: #fff; border-radius: 4px; }
        .status { margin: 20px 0; padding: 15px; background: #333; border-radius: 8px; }
        .job-progress { margin: 10px 0; padding: 15px; background: #2a2a2a; border-radius: 8px; border-left: 4px solid #3b82f6; }
        .progress-bar { width: 100%; height: 8px; background: #444; border-radius: 4px; margin: 10px 0; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #10b981); transition: width 0.3s ease; }
        #log { height: 400px; overflow-y: scroll; border: 1px solid #444; padding: 15px; background: #1a1a1a; font-family: monospace; font-size: 12px; border-radius: 8px; }
        .log-entry { margin: 2px 0; }
        .log-info { color: #3b82f6; }
        .log-success { color: #10b981; }
        .log-error { color: #ef4444; }
        .log-warning { color: #f59e0b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 FastAPI WebSocket Job Progress Test</h1>
        <p>Real-time Celery background job progress streaming via WebSocket</p>
        
        <div class="controls">
            <h3>Connection</h3>
            <button onclick="connectWebSocket()">Connect</button>
            <button onclick="disconnectWebSocket()">Disconnect</button>
            <button onclick="pingServer()">Ping Server</button>
            <button onclick="getActiveJobs()">Get Active Jobs</button>
        </div>
        
        <div class="controls">
            <h3>Job Subscription</h3>
            <input type="text" id="jobId" placeholder="Enter Job ID" />
            <button onclick="subscribeToJob()">Subscribe</button>
            <button onclick="unsubscribeFromJob()">Unsubscribe</button>
        </div>
        
        <div class="status" id="connectionStatus">
            <h3>Connection Status</h3>
            <div id="statusText">Disconnected</div>
        </div>
        
        <div class="status">
            <h3>Active Job Progress</h3>
            <div id="jobProgress">No active job subscriptions</div>
        </div>
        
        <div class="status">
            <h3>WebSocket Log</h3>
            <div id="log"></div>
        </div>
    </div>
    
    <script>
        let ws = null;
        let activeJobs = {};
        
        function log(message, type = 'info') {
            const logDiv = document.getElementById('log');
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            entry.innerHTML = `[${timestamp}] ${message}`;
            logDiv.appendChild(entry);
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        function updateConnectionStatus(connected) {
            const statusText = document.getElementById('statusText');
            if (connected) {
                statusText.innerHTML = '<span style="color: #10b981;">✅ Connected</span>';
            } else {
                statusText.innerHTML = '<span style="color: #ef4444;">❌ Disconnected</span>';
            }
        }
        
        function connectWebSocket() {
            if (ws) {
                ws.close();
            }
            
            const wsUrl = `ws://${window.location.host}/ws/jobs`;
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function(event) {
                log('Connected to WebSocket', 'success');
                updateConnectionStatus(true);
            };
            
            ws.onclose = function(event) {
                log('WebSocket connection closed', 'warning');
                updateConnectionStatus(false);
            };
            
            ws.onerror = function(error) {
                log('WebSocket error: ' + error, 'error');
            };
            
            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    handleWebSocketMessage(data);
                } catch (e) {
                    log('Failed to parse message: ' + event.data, 'error');
                }
            };
        }
        
        function disconnectWebSocket() {
            if (ws) {
                ws.close();
                ws = null;
                activeJobs = {};
                updateJobProgress();
            }
        }
        
        function pingServer() {
            if (!ws) {
                log('Not connected', 'warning');
                return;
            }
            
            ws.send(JSON.stringify({
                type: 'ping'
            }));
        }
        
        function subscribeToJob() {
            const jobId = document.getElementById('jobId').value.trim();
            if (!jobId) {
                log('Please enter a job ID', 'warning');
                return;
            }
            
            if (!ws) {
                log('Not connected', 'warning');
                return;
            }
            
            ws.send(JSON.stringify({
                type: 'subscribe_job',
                job_id: jobId
            }));
            
            log(`Subscribing to job: ${jobId}`, 'info');
        }
        
        function unsubscribeFromJob() {
            const jobId = document.getElementById('jobId').value.trim();
            if (!jobId) {
                log('Please enter a job ID', 'warning');
                return;
            }
            
            if (!ws) {
                log('Not connected', 'warning');
                return;
            }
            
            ws.send(JSON.stringify({
                type: 'unsubscribe_job',
                job_id: jobId
            }));
            
            log(`Unsubscribing from job: ${jobId}`, 'info');
        }
        
        function getActiveJobs() {
            if (!ws) {
                log('Not connected', 'warning');
                return;
            }
            
            ws.send(JSON.stringify({
                type: 'get_active_jobs'
            }));
        }
        
        function handleWebSocketMessage(data) {
            switch (data.type) {
                case 'connected':
                    log(`Welcome message: ${data.message}`, 'success');
                    break;
                    
                case 'job_update':
                    log(`Job update for ${data.job_id}: ${data.data.message || 'Progress update'}`, 'info');
                    activeJobs[data.job_id] = data.data;
                    updateJobProgress();
                    break;
                    
                case 'job_status':
                    log(`Job status for ${data.job_id}: ${data.data.message || 'Status update'}`, 'info');
                    activeJobs[data.job_id] = data.data;
                    updateJobProgress();
                    break;
                    
                case 'subscription_response':
                    log(`Subscription: ${data.message}`, data.success ? 'success' : 'error');
                    break;
                    
                case 'unsubscription_response':
                    log(`Unsubscription: ${data.message}`, data.success ? 'success' : 'warning');
                    if (data.success && data.job_id) {
                        delete activeJobs[data.job_id];
                        updateJobProgress();
                    }
                    break;
                    
                case 'active_jobs':
                    log(`Active jobs info: ${JSON.stringify(data.data)}`, 'info');
                    break;
                    
                case 'pong':
                    log('Pong received from server', 'success');
                    break;
                    
                case 'error':
                    log(`Error: ${data.message}`, 'error');
                    break;
                    
                default:
                    log(`Unknown message type: ${data.type}`, 'warning');
            }
        }
        
        function updateJobProgress() {
            const progressDiv = document.getElementById('jobProgress');
            
            if (Object.keys(activeJobs).length === 0) {
                progressDiv.innerHTML = 'No active job subscriptions';
                return;
            }
            
            let html = '';
            for (const [jobId, jobData] of Object.entries(activeJobs)) {
                const progress = jobData.percent || jobData.progress || 0;
                const message = jobData.message || 'Processing...';
                const status = jobData.status || 'running';
                
                html += `
                    <div class="job-progress">
                        <div><strong>Job ${jobId}</strong></div>
                        <div>Status: ${status}</div>
                        <div>Progress: ${progress}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <div>Message: ${message}</div>
                        <small>Updated: ${jobData.updated_at || new Date().toLocaleTimeString()}</small>
                    </div>
                `;
            }
            
            progressDiv.innerHTML = html;
        }
        
        // Auto-connect on page load
        window.onload = function() {
            log('Page loaded. Click Connect to start WebSocket connection.', 'info');
        };
    </script>
</body>
</html>
    """


# Initialize WebSocket routes when app starts
async def init_websocket_system(app: FastAPI):
    """Initialize WebSocket system on app startup"""
    setup_websocket_routes(app)

    # FIX: Start Redis subscriber immediately on app startup
    # This prevents the race condition where progress updates are lost
    # if jobs start before WebSocket connections are made
    try:
        await websocket_manager.start_redis_subscriber()
        logger.info(
            "✅ FastAPI WebSocket job progress system initialized with Redis subscriber"
        )
    except Exception as e:
        logger.error(f"❌ Failed to start Redis subscriber during app startup: {e}")
        logger.info(
            "⚠️ WebSocket job progress will start when first connection is made"
        )


# Cleanup on app shutdown
async def cleanup_websocket_system():
    """Cleanup WebSocket system on app shutdown"""
    await websocket_manager.stop_redis_subscriber()
    logger.info("WebSocket system cleaned up")
