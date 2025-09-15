"""
FastAPI WebSocket Integration - Issue 130 Template System Migration
Real-time WebSocket support replacing Flask-SocketIO
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

import uvicorn
from fastapi import Depends, WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.websocket_integration")


@dataclass
class WebSocketConnection:
    """WebSocket connection information"""

    websocket: WebSocket
    client_id: str
    user_id: Optional[str] = None
    subscriptions: Set[str] = None
    connected_at: datetime = None
    last_ping: datetime = None

    def __post_init__(self):
        if self.subscriptions is None:
            self.subscriptions = set()
        if self.connected_at is None:
            self.connected_at = datetime.utcnow()
        if self.last_ping is None:
            self.last_ping = datetime.utcnow()


@dataclass
class WebSocketMessage:
    """WebSocket message structure"""

    type: str
    data: Any = None
    target: Optional[str] = None
    timestamp: datetime = None
    client_id: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "target": self.target,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "client_id": self.client_id,
        }


class WebSocketManager:
    """WebSocket connection manager"""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        self.message_handlers: Dict[str, Callable] = {}
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_task = None

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a message handler for a specific message type"""
        self.message_handlers[message_type] = handler

    async def connect(
        self, websocket: WebSocket, client_id: str
    ) -> WebSocketConnection:
        """Accept WebSocket connection"""
        await websocket.accept()

        connection = WebSocketConnection(websocket=websocket, client_id=client_id)

        self.connections[client_id] = connection

        # Send connection confirmation
        await self.send_to_client(
            client_id,
            WebSocketMessage(
                type="connection_established",
                data={
                    "client_id": client_id,
                    "server_time": datetime.utcnow().isoformat(),
                },
            ),
        )

        logger.info(f"WebSocket client connected: {client_id}")

        # Start heartbeat if this is the first connection
        if len(self.connections) == 1 and not self.heartbeat_task:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return connection

    async def disconnect(self, client_id: str):
        """Disconnect WebSocket client"""
        if client_id in self.connections:
            connection = self.connections[client_id]

            # Remove from all subscriptions
            for topic, subscribers in self.subscriptions.items():
                subscribers.discard(client_id)

            # Clean up empty subscriptions
            self.subscriptions = {
                topic: subscribers
                for topic, subscribers in self.subscriptions.items()
                if subscribers
            }

            # Remove connection
            del self.connections[client_id]

            logger.info(f"WebSocket client disconnected: {client_id}")

            # Stop heartbeat if no connections remain
            if not self.connections and self.heartbeat_task:
                self.heartbeat_task.cancel()
                self.heartbeat_task = None

    async def send_to_client(self, client_id: str, message: WebSocketMessage):
        """Send message to specific client"""
        if client_id not in self.connections:
            logger.warning(f"Attempted to send to disconnected client: {client_id}")
            return False

        try:
            connection = self.connections[client_id]
            await connection.websocket.send_text(
                json.dumps(message.to_dict(), default=str)
            )
            return True
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def broadcast(
        self, message: WebSocketMessage, exclude_client: Optional[str] = None
    ):
        """Broadcast message to all connected clients"""
        disconnected_clients = []

        for client_id, connection in self.connections.items():
            if exclude_client and client_id == exclude_client:
                continue

            try:
                await connection.websocket.send_text(
                    json.dumps(message.to_dict(), default=str)
                )
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def subscribe(self, client_id: str, topic: str):
        """Subscribe client to a topic"""
        if client_id not in self.connections:
            return False

        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()

        self.subscriptions[topic].add(client_id)
        self.connections[client_id].subscriptions.add(topic)

        logger.debug(f"Client {client_id} subscribed to {topic}")
        return True

    async def unsubscribe(self, client_id: str, topic: str):
        """Unsubscribe client from a topic"""
        if client_id not in self.connections:
            return False

        if topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
            if not self.subscriptions[topic]:
                del self.subscriptions[topic]

        self.connections[client_id].subscriptions.discard(topic)

        logger.debug(f"Client {client_id} unsubscribed from {topic}")
        return True

    async def publish_to_topic(self, topic: str, message: WebSocketMessage):
        """Publish message to all subscribers of a topic"""
        if topic not in self.subscriptions:
            logger.debug(f"No subscribers for topic: {topic}")
            return 0

        subscribers = self.subscriptions[topic].copy()
        disconnected_clients = []
        sent_count = 0

        for client_id in subscribers:
            if client_id not in self.connections:
                disconnected_clients.append(client_id)
                continue

            try:
                connection = self.connections[client_id]
                await connection.websocket.send_text(
                    json.dumps(message.to_dict(), default=str)
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error publishing to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

        logger.debug(f"Published to topic {topic}: {sent_count} recipients")
        return sent_count

    async def handle_message(self, client_id: str, raw_message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(raw_message)
            message_type = data.get("type")

            if not message_type:
                await self.send_to_client(
                    client_id,
                    WebSocketMessage(
                        type="error", data={"error": "Message type required"}
                    ),
                )
                return

            # Update last ping
            if client_id in self.connections:
                self.connections[client_id].last_ping = datetime.utcnow()

            # Handle built-in message types
            if message_type == "ping":
                await self.send_to_client(client_id, WebSocketMessage(type="pong"))
                return

            elif message_type == "subscribe":
                topic = data.get("topic")
                if topic:
                    await self.subscribe(client_id, topic)
                    await self.send_to_client(
                        client_id,
                        WebSocketMessage(type="subscribed", data={"topic": topic}),
                    )
                return

            elif message_type == "unsubscribe":
                topic = data.get("topic")
                if topic:
                    await self.unsubscribe(client_id, topic)
                    await self.send_to_client(
                        client_id,
                        WebSocketMessage(type="unsubscribed", data={"topic": topic}),
                    )
                return

            # Handle custom message types
            if message_type in self.message_handlers:
                handler = self.message_handlers[message_type]
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(client_id, data)
                    else:
                        handler(client_id, data)
                except Exception as e:
                    logger.error(f"Message handler error for {message_type}: {e}")
                    await self.send_to_client(
                        client_id,
                        WebSocketMessage(
                            type="error", data={"error": f"Handler error: {str(e)}"}
                        ),
                    )
            else:
                logger.warning(f"Unknown message type: {message_type}")
                await self.send_to_client(
                    client_id,
                    WebSocketMessage(
                        type="error",
                        data={"error": f"Unknown message type: {message_type}"},
                    ),
                )

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from client {client_id}: {raw_message}")
            await self.send_to_client(
                client_id,
                WebSocketMessage(type="error", data={"error": "Invalid JSON format"}),
            )
        except Exception as e:
            logger.error(f"Error handling message from {client_id}: {e}")
            await self.send_to_client(
                client_id,
                WebSocketMessage(type="error", data={"error": "Internal server error"}),
            )

    async def _heartbeat_loop(self):
        """Background heartbeat to detect disconnected clients"""
        while self.connections:
            try:
                current_time = datetime.utcnow()
                timeout_threshold = 60  # 60 seconds timeout

                disconnected_clients = []

                for client_id, connection in self.connections.items():
                    # Check if client has been inactive too long
                    inactive_duration = (
                        current_time - connection.last_ping
                    ).total_seconds()

                    if inactive_duration > timeout_threshold:
                        logger.warning(
                            f"Client {client_id} timed out after {inactive_duration}s"
                        )
                        disconnected_clients.append(client_id)
                    elif inactive_duration > self.heartbeat_interval:
                        # Send ping to check if client is still alive
                        try:
                            await connection.websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "ping",
                                        "timestamp": current_time.isoformat(),
                                    }
                                )
                            )
                        except Exception:
                            disconnected_clients.append(client_id)

                # Clean up timed out clients
                for client_id in disconnected_clients:
                    await self.disconnect(client_id)

                await asyncio.sleep(self.heartbeat_interval)

            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled")
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(5)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics"""
        return {
            "total_connections": len(self.connections),
            "total_subscriptions": len(self.subscriptions),
            "topics": list(self.subscriptions.keys()),
            "connections": [
                {
                    "client_id": conn.client_id,
                    "user_id": conn.user_id,
                    "connected_at": conn.connected_at.isoformat(),
                    "subscriptions": list(conn.subscriptions),
                }
                for conn in self.connections.values()
            ],
        }


# Global WebSocket manager
websocket_manager = WebSocketManager()

# WebSocket router
websocket_router = APIRouter()


@websocket_router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Main WebSocket endpoint"""
    connection = await websocket_manager.connect(websocket, client_id)

    try:
        while True:
            # Receive message from client
            message = await websocket.receive_text()
            await websocket_manager.handle_message(client_id, message)

    except WebSocketDisconnect:
        await websocket_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
        await websocket_manager.disconnect(client_id)


# Background job monitoring (replacing Flask-SocketIO functionality)
class BackgroundJobMonitor:
    """Monitor and broadcast background job status"""

    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager

        # Register message handlers
        websocket_manager.register_message_handler(
            "job_status_request", self.handle_job_status_request
        )
        websocket_manager.register_message_handler(
            "job_cancel_request", self.handle_job_cancel_request
        )

    async def handle_job_status_request(self, client_id: str, data: Dict[str, Any]):
        """Handle job status request"""
        try:
            # TODO: Get actual job status from job service
            job_status = {"active_jobs": [], "completed_jobs": [], "failed_jobs": []}

            await self.websocket_manager.send_to_client(
                client_id, WebSocketMessage(type="job_status_response", data=job_status)
            )
        except Exception as e:
            logger.error(f"Job status request error: {e}")

    async def handle_job_cancel_request(self, client_id: str, data: Dict[str, Any]):
        """Handle job cancellation request"""
        try:
            job_id = data.get("job_id")
            if not job_id:
                await self.websocket_manager.send_to_client(
                    client_id,
                    WebSocketMessage(type="error", data={"error": "Job ID required"}),
                )
                return

            # TODO: Cancel actual job
            success = True  # Placeholder

            await self.websocket_manager.send_to_client(
                client_id,
                WebSocketMessage(
                    type="job_cancel_response",
                    data={"job_id": job_id, "success": success},
                ),
            )
        except Exception as e:
            logger.error(f"Job cancel request error: {e}")

    async def broadcast_job_update(self, job_data: Dict[str, Any]):
        """Broadcast job status update to all subscribers"""
        await self.websocket_manager.publish_to_topic(
            "job_updates", WebSocketMessage(type="job_update", data=job_data)
        )

    async def broadcast_job_completed(self, job_data: Dict[str, Any]):
        """Broadcast job completion to all subscribers"""
        await self.websocket_manager.publish_to_topic(
            "job_updates", WebSocketMessage(type="job_completed", data=job_data)
        )


# Real-time notifications
class NotificationService:
    """Real-time notification service"""

    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager

        # Register message handlers
        websocket_manager.register_message_handler(
            "notification_settings", self.handle_notification_settings
        )

    async def handle_notification_settings(self, client_id: str, data: Dict[str, Any]):
        """Handle notification settings update"""
        try:
            settings = data.get("settings", {})

            # Subscribe to requested notification types
            for notification_type, enabled in settings.items():
                if enabled:
                    await self.websocket_manager.subscribe(
                        client_id, f"notifications_{notification_type}"
                    )
                else:
                    await self.websocket_manager.unsubscribe(
                        client_id, f"notifications_{notification_type}"
                    )

            await self.websocket_manager.send_to_client(
                client_id,
                WebSocketMessage(
                    type="notification_settings_updated", data={"status": "success"}
                ),
            )
        except Exception as e:
            logger.error(f"Notification settings error: {e}")

    async def send_notification(
        self,
        notification_type: str,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
    ):
        """Send notification to all subscribers of a type"""
        notification_data = {
            "title": title,
            "message": message,
            "type": notification_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {},
        }

        await self.websocket_manager.publish_to_topic(
            f"notifications_{notification_type}",
            WebSocketMessage(type="notification", data=notification_data),
        )


# Universal search real-time updates
class SearchService:
    """Real-time search service"""

    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager

        # Register message handlers
        websocket_manager.register_message_handler(
            "search_request", self.handle_search_request
        )

    async def handle_search_request(self, client_id: str, data: Dict[str, Any]):
        """Handle real-time search request"""
        try:
            query = data.get("query", "").strip()
            search_type = data.get("type", "all")

            if len(query) < 2:
                await self.websocket_manager.send_to_client(
                    client_id,
                    WebSocketMessage(
                        type="search_results", data={"results": [], "query": query}
                    ),
                )
                return

            # TODO: Implement actual search logic
            results = {
                "videos": [],
                "artists": [],
                "playlists": [],
                "query": query,
                "total": 0,
            }

            await self.websocket_manager.send_to_client(
                client_id, WebSocketMessage(type="search_results", data=results)
            )
        except Exception as e:
            logger.error(f"Search request error: {e}")


# Initialize services
job_monitor = BackgroundJobMonitor(websocket_manager)
notification_service = NotificationService(websocket_manager)
search_service = SearchService(websocket_manager)


# WebSocket status endpoint
@websocket_router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status"""
    return websocket_manager.get_connection_stats()


# Helper functions for integration
def get_websocket_manager() -> WebSocketManager:
    """Get global WebSocket manager"""
    return websocket_manager


def get_job_monitor() -> BackgroundJobMonitor:
    """Get job monitor service"""
    return job_monitor


def get_notification_service() -> NotificationService:
    """Get notification service"""
    return notification_service


def get_search_service() -> SearchService:
    """Get search service"""
    return search_service


async def send_system_notification(
    title: str, message: str, notification_type: str = "info"
):
    """Send system-wide notification"""
    await notification_service.send_notification(notification_type, title, message)


async def broadcast_job_update(
    job_id: str, status: str, progress: int = None, message: str = None
):
    """Broadcast job status update"""
    job_data = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await job_monitor.broadcast_job_update(job_data)
