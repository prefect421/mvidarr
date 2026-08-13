"""
Shared webhook event data structures (#315).

Split out of webhook_service.py so that provider-specific formatters
(discord_notification_formatter.py, apprise_notification_service.py) can
depend on WebhookEvent/WebhookEventType without creating a circular
import with webhook_service.py, which in turn imports those formatters
to use at delivery time. This module has no dependencies on any other
mvidarr webhook module, so it's safe for all of them to import from.

webhook_service.py re-exports WebhookEvent/WebhookEventType from here so
existing `from src.services.webhook_service import WebhookEvent,
WebhookEventType` call sites keep working unchanged.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict


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
