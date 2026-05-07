"""
Webhook Service for event-driven notifications and integrations
"""

import asyncio
import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.webhook")


class WebhookEventType(Enum):
    """Webhook event types"""

    ARTIST_ADDED = "artist.added"
    ARTIST_UPDATED = "artist.updated"
    ARTIST_DELETED = "artist.deleted"
    VIDEO_ADDED = "video.added"
    VIDEO_UPDATED = "video.updated"
    VIDEO_DELETED = "video.deleted"
    VIDEO_DOWNLOADED = "video.downloaded"
    VIDEO_DOWNLOAD_FAILED = "video.download_failed"
    DOWNLOAD_STARTED = "download.started"
    DOWNLOAD_COMPLETED = "download.completed"
    DOWNLOAD_FAILED = "download.failed"
    PLAYLIST_SYNC_STARTED = "playlist.sync_started"
    PLAYLIST_SYNC_COMPLETED = "playlist.sync_completed"
    EXTERNAL_IMPORT_STARTED = "external.import_started"
    EXTERNAL_IMPORT_COMPLETED = "external.import_completed"
    SYSTEM_HEALTH_CHANGED = "system.health_changed"
    SYSTEM_ERROR = "system.error"


@dataclass
class WebhookEvent:
    """Webhook event data structure"""

    event_type: WebhookEventType
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata or {},
        }


@dataclass
class WebhookEndpoint:
    """Webhook endpoint configuration"""

    url: str
    secret: Optional[str] = None
    events: List[WebhookEventType] = None
    enabled: bool = True
    max_retries: int = 3
    timeout: int = 30
    headers: Dict[str, str] = None

    def __post_init__(self):
        if self.events is None:
            self.events = []
        if self.headers is None:
            self.headers = {}


class WebhookService:
    """Service for managing and delivering webhooks"""

    def __init__(self):
        self.endpoints: List[WebhookEndpoint] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.delivery_threads: List[threading.Thread] = []
        self.running = False
        self.load_endpoints()

    def load_endpoints(self):
        """Load webhook endpoints from settings"""
        try:
            webhooks_config = SettingsService.get_json("webhooks_config", {})
            self.endpoints = []

            for endpoint_config in webhooks_config.get("endpoints", []):
                # Convert event strings back to enum
                events = []
                for event_str in endpoint_config.get("events", []):
                    try:
                        events.append(WebhookEventType(event_str))
                    except ValueError:
                        logger.warning(f"Unknown webhook event type: {event_str}")

                endpoint = WebhookEndpoint(
                    url=endpoint_config["url"],
                    secret=endpoint_config.get("secret"),
                    events=events,
                    enabled=endpoint_config.get("enabled", True),
                    max_retries=endpoint_config.get("max_retries", 3),
                    timeout=endpoint_config.get("timeout", 30),
                    headers=endpoint_config.get("headers", {}),
                )
                self.endpoints.append(endpoint)

            logger.info(f"Loaded {len(self.endpoints)} webhook endpoints")

        except Exception as e:
            logger.error(f"Failed to load webhook endpoints: {e}")
            self.endpoints = []

    def save_endpoints(self):
        """Save webhook endpoints to settings"""
        try:
            endpoints_data = []
            for endpoint in self.endpoints:
                endpoint_data = {
                    "url": endpoint.url,
                    "secret": endpoint.secret,
                    "events": [event.value for event in endpoint.events],
                    "enabled": endpoint.enabled,
                    "max_retries": endpoint.max_retries,
                    "timeout": endpoint.timeout,
                    "headers": endpoint.headers,
                }
                endpoints_data.append(endpoint_data)

            webhooks_config = {"endpoints": endpoints_data}

            SettingsService.set_json("webhooks_config", webhooks_config)
            logger.info(f"Saved {len(self.endpoints)} webhook endpoints")

        except Exception as e:
            logger.error(f"Failed to save webhook endpoints: {e}")

    def add_endpoint(self, endpoint: WebhookEndpoint) -> bool:
        """Add a new webhook endpoint"""
        try:
            # Validate URL
            parsed_url = urlparse(endpoint.url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError("Invalid webhook URL")

            # Check for duplicates
            for existing in self.endpoints:
                if existing.url == endpoint.url:
                    raise ValueError("Endpoint URL already exists")

            self.endpoints.append(endpoint)
            self.save_endpoints()
            logger.info(f"Added webhook endpoint: {endpoint.url}")
            return True

        except Exception as e:
            logger.error(f"Failed to add webhook endpoint: {e}")
            return False

    def remove_endpoint(self, url: str) -> bool:
        """Remove webhook endpoint by URL"""
        try:
            self.endpoints = [ep for ep in self.endpoints if ep.url != url]
            self.save_endpoints()
            logger.info(f"Removed webhook endpoint: {url}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove webhook endpoint: {e}")
            return False

    def update_endpoint(self, url: str, updates: Dict) -> bool:
        """Update webhook endpoint configuration"""
        try:
            for endpoint in self.endpoints:
                if endpoint.url == url:
                    # Update allowed fields
                    if "secret" in updates:
                        endpoint.secret = updates["secret"]
                    if "events" in updates:
                        endpoint.events = [
                            WebhookEventType(event) for event in updates["events"]
                        ]
                    if "enabled" in updates:
                        endpoint.enabled = updates["enabled"]
                    if "max_retries" in updates:
                        endpoint.max_retries = updates["max_retries"]
                    if "timeout" in updates:
                        endpoint.timeout = updates["timeout"]
                    if "headers" in updates:
                        endpoint.headers = updates["headers"]

                    self.save_endpoints()
                    logger.info(f"Updated webhook endpoint: {url}")
                    return True

            raise ValueError("Endpoint not found")

        except Exception as e:
            logger.error(f"Failed to update webhook endpoint: {e}")
            return False

    def get_endpoints(self) -> List[Dict]:
        """Get all webhook endpoints"""
        return [
            {
                "url": ep.url,
                "secret": "***" if ep.secret else None,
                "events": [event.value for event in ep.events],
                "enabled": ep.enabled,
                "max_retries": ep.max_retries,
                "timeout": ep.timeout,
                "headers": ep.headers,
            }
            for ep in self.endpoints
        ]

    def trigger_event(
        self, event_type: WebhookEventType, data: Dict, metadata: Dict = None
    ):
        """Trigger a webhook event"""
        try:
            event = WebhookEvent(
                event_type=event_type,
                timestamp=datetime.now(),
                data=data,
                metadata=metadata or {},
            )

            # Find matching endpoints
            matching_endpoints = [
                ep
                for ep in self.endpoints
                if ep.enabled and (not ep.events or event_type in ep.events)
            ]

            if not matching_endpoints:
                logger.debug(f"No matching endpoints for event: {event_type.value}")
                return

            # Deliver to each endpoint
            for endpoint in matching_endpoints:
                self._deliver_webhook(endpoint, event)

            logger.info(
                f"Triggered webhook event: {event_type.value} to {len(matching_endpoints)} endpoints"
            )

        except Exception as e:
            logger.error(f"Failed to trigger webhook event: {e}")

    def _deliver_webhook(self, endpoint: WebhookEndpoint, event: WebhookEvent):
        """Deliver webhook to endpoint with retry logic"""

        def delivery_task():
            payload = event.to_dict()
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "MVidarr-Enhanced-Webhook/1.0",
                "X-Webhook-Event": event.event_type.value,
                "X-Webhook-Timestamp": str(int(event.timestamp.timestamp())),
            }

            # Add custom headers
            headers.update(endpoint.headers)

            # Add signature if secret is configured
            if endpoint.secret:
                signature = self._generate_signature(
                    endpoint.secret, json.dumps(payload)
                )
                headers["X-Webhook-Signature"] = signature

            # SSRF protection - validate webhook URL
            from src.utils.url_validator import validate_url_or_raise

            validate_url_or_raise(endpoint.url, allow_local_network=True)

            # Retry logic
            for attempt in range(endpoint.max_retries + 1):
                try:
                    response = requests.post(
                        endpoint.url,
                        json=payload,
                        headers=headers,
                        timeout=endpoint.timeout,
                    )

                    if response.status_code in [200, 201, 202, 204]:
                        logger.info(
                            f"Webhook delivered successfully to {endpoint.url} (attempt {attempt + 1})"
                        )
                        return
                    else:
                        logger.warning(
                            f"Webhook delivery failed to {endpoint.url}: HTTP {response.status_code}"
                        )

                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"Webhook delivery failed to {endpoint.url} (attempt {attempt + 1}): {e}"
                    )

                # Wait before retry (exponential backoff)
                if attempt < endpoint.max_retries:
                    wait_time = (2**attempt) * 1
                    time.sleep(wait_time)

            logger.error(
                f"Webhook delivery failed permanently to {endpoint.url} after {endpoint.max_retries + 1} attempts"
            )

        # Run delivery in separate thread
        thread = threading.Thread(target=delivery_task)
        thread.daemon = True
        thread.start()

    def _generate_signature(self, secret: str, payload: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload"""
        signature = hmac.new(
            secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def test_endpoint(self, url: str, secret: Optional[str] = None) -> Dict:
        """Test webhook endpoint with a test event"""
        try:
            test_event = WebhookEvent(
                event_type=WebhookEventType.SYSTEM_HEALTH_CHANGED,
                timestamp=datetime.now(),
                data={
                    "test": True,
                    "message": "This is a test webhook from MVidarr",
                    "version": "1.0.0",
                },
                metadata={
                    "source": "webhook_test",
                    "user_agent": "MVidarr-Enhanced-Webhook/1.0",
                },
            )

            payload = test_event.to_dict()
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "MVidarr-Enhanced-Webhook/1.0",
                "X-Webhook-Event": test_event.event_type.value,
                "X-Webhook-Timestamp": str(int(test_event.timestamp.timestamp())),
            }

            # Add signature if secret provided
            if secret:
                signature = self._generate_signature(secret, json.dumps(payload))
                headers["X-Webhook-Signature"] = signature

            # SSRF protection
            from src.utils.url_validator import validate_url_or_raise

            validate_url_or_raise(url, allow_local_network=True)

            response = requests.post(url, json=payload, headers=headers, timeout=10)

            return {
                "success": True,
                "status_code": response.status_code,
                "response_text": response.text[:200],
                "response_time": response.elapsed.total_seconds(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_event_types(self) -> List[Dict]:
        """Get available webhook event types"""
        return [
            {
                "value": event.value,
                "name": event.name,
                "description": self._get_event_description(event),
            }
            for event in WebhookEventType
        ]

    def _get_event_description(self, event: WebhookEventType) -> str:
        """Get human-readable description for event type"""
        descriptions = {
            WebhookEventType.ARTIST_ADDED: "New artist added to the system",
            WebhookEventType.ARTIST_UPDATED: "Artist information updated",
            WebhookEventType.ARTIST_DELETED: "Artist deleted from the system",
            WebhookEventType.VIDEO_ADDED: "New video added to the system",
            WebhookEventType.VIDEO_UPDATED: "Video information updated",
            WebhookEventType.VIDEO_DELETED: "Video deleted from the system",
            WebhookEventType.VIDEO_DOWNLOADED: "Video successfully downloaded",
            WebhookEventType.VIDEO_DOWNLOAD_FAILED: "Video download failed",
            WebhookEventType.DOWNLOAD_STARTED: "Download process started",
            WebhookEventType.DOWNLOAD_COMPLETED: "Download process completed",
            WebhookEventType.DOWNLOAD_FAILED: "Download process failed",
            WebhookEventType.PLAYLIST_SYNC_STARTED: "Playlist synchronization started",
            WebhookEventType.PLAYLIST_SYNC_COMPLETED: "Playlist synchronization completed",
            WebhookEventType.EXTERNAL_IMPORT_STARTED: "External service import started",
            WebhookEventType.EXTERNAL_IMPORT_COMPLETED: "External service import completed",
            WebhookEventType.SYSTEM_HEALTH_CHANGED: "System health status changed",
            WebhookEventType.SYSTEM_ERROR: "System error occurred",
        }
        return descriptions.get(event, "Unknown event type")


# Global instance
webhook_service = WebhookService()


# Convenience functions for triggering common events
def trigger_artist_added(artist_data: Dict, metadata: Dict = None):
    """Trigger artist added event"""
    webhook_service.trigger_event(WebhookEventType.ARTIST_ADDED, artist_data, metadata)


def trigger_artist_updated(artist_data: Dict, metadata: Dict = None):
    """Trigger artist updated event"""
    webhook_service.trigger_event(
        WebhookEventType.ARTIST_UPDATED, artist_data, metadata
    )


def trigger_artist_deleted(artist_data: Dict, metadata: Dict = None):
    """Trigger artist deleted event"""
    webhook_service.trigger_event(
        WebhookEventType.ARTIST_DELETED, artist_data, metadata
    )


def trigger_video_added(video_data: Dict, metadata: Dict = None):
    """Trigger video added event"""
    webhook_service.trigger_event(WebhookEventType.VIDEO_ADDED, video_data, metadata)


def trigger_video_updated(video_data: Dict, metadata: Dict = None):
    """Trigger video updated event"""
    webhook_service.trigger_event(WebhookEventType.VIDEO_UPDATED, video_data, metadata)


def trigger_video_deleted(video_data: Dict, metadata: Dict = None):
    """Trigger video deleted event"""
    webhook_service.trigger_event(WebhookEventType.VIDEO_DELETED, video_data, metadata)


def trigger_video_downloaded(video_data: Dict, metadata: Dict = None):
    """Trigger video downloaded event"""
    webhook_service.trigger_event(
        WebhookEventType.VIDEO_DOWNLOADED, video_data, metadata
    )


def trigger_video_download_failed(video_data: Dict, error: str, metadata: Dict = None):
    """Trigger video download failed event"""
    data = video_data.copy()
    data["error"] = error
    webhook_service.trigger_event(
        WebhookEventType.VIDEO_DOWNLOAD_FAILED, data, metadata
    )


def trigger_download_started(download_data: Dict, metadata: Dict = None):
    """Trigger download started event"""
    webhook_service.trigger_event(
        WebhookEventType.DOWNLOAD_STARTED, download_data, metadata
    )


def trigger_download_completed(download_data: Dict, metadata: Dict = None):
    """Trigger download completed event"""
    webhook_service.trigger_event(
        WebhookEventType.DOWNLOAD_COMPLETED, download_data, metadata
    )


def trigger_download_failed(download_data: Dict, error: str, metadata: Dict = None):
    """Trigger download failed event"""
    data = download_data.copy()
    data["error"] = error
    webhook_service.trigger_event(WebhookEventType.DOWNLOAD_FAILED, data, metadata)


def trigger_playlist_sync_started(playlist_data: Dict, metadata: Dict = None):
    """Trigger playlist sync started event"""
    webhook_service.trigger_event(
        WebhookEventType.PLAYLIST_SYNC_STARTED, playlist_data, metadata
    )


def trigger_playlist_sync_completed(
    playlist_data: Dict, results: Dict, metadata: Dict = None
):
    """Trigger playlist sync completed event"""
    data = playlist_data.copy()
    data["results"] = results
    webhook_service.trigger_event(
        WebhookEventType.PLAYLIST_SYNC_COMPLETED, data, metadata
    )


def trigger_external_import_started(
    service: str, import_data: Dict, metadata: Dict = None
):
    """Trigger external import started event"""
    data = import_data.copy()
    data["service"] = service
    webhook_service.trigger_event(
        WebhookEventType.EXTERNAL_IMPORT_STARTED, data, metadata
    )


def trigger_external_import_completed(
    service: str, import_data: Dict, results: Dict, metadata: Dict = None
):
    """Trigger external import completed event"""
    data = import_data.copy()
    data["service"] = service
    data["results"] = results
    webhook_service.trigger_event(
        WebhookEventType.EXTERNAL_IMPORT_COMPLETED, data, metadata
    )


def trigger_system_health_changed(health_data: Dict, metadata: Dict = None):
    """Trigger system health changed event"""
    webhook_service.trigger_event(
        WebhookEventType.SYSTEM_HEALTH_CHANGED, health_data, metadata
    )


def trigger_system_error(error_data: Dict, metadata: Dict = None):
    """Trigger system error event"""
    webhook_service.trigger_event(WebhookEventType.SYSTEM_ERROR, error_data, metadata)
