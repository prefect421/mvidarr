"""
Apprise notification delivery for MVidarr webhook events (#315).

Thin wrapper around the `apprise` library, which owns delivery to
whatever service the endpoint's URL string targets (Slack, Telegram,
ntfy, email, Discord-via-Apprise, ~100 others). MVidarr's own
retry/backoff loop in webhook_service.py still wraps a call to this
function, so a transient failure still gets MVidarr-level retries even
though Apprise's own .notify() call is fire-and-forget.

Reuses the same title logic as discord_notification_formatter.py but
kept as a small local copy rather than a shared import -- Apprise needs
a plain title/body string pair, not a Discord embed dict, and the two
are simple enough that a shared abstraction isn't worth the coupling
yet.
"""

import apprise

from src.services.webhook_models import WebhookEvent, WebhookEventType
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.apprise_notification")

_TITLES = {
    WebhookEventType.ARTIST_ADDED: "Artist Added",
    WebhookEventType.ARTIST_UPDATED: "Artist Updated",
    WebhookEventType.ARTIST_DELETED: "Artist Deleted",
    WebhookEventType.VIDEO_ADDED: "Video Added",
    WebhookEventType.VIDEO_UPDATED: "Video Updated",
    WebhookEventType.VIDEO_DELETED: "Video Deleted",
    WebhookEventType.VIDEO_DOWNLOADED: "Video Downloaded",
    WebhookEventType.VIDEO_DOWNLOAD_FAILED: "Video Download Failed",
    WebhookEventType.DOWNLOAD_STARTED: "Download Started",
    WebhookEventType.DOWNLOAD_COMPLETED: "Download Completed",
    WebhookEventType.DOWNLOAD_FAILED: "Download Failed",
    WebhookEventType.PLAYLIST_SYNC_STARTED: "Playlist Sync Started",
    WebhookEventType.PLAYLIST_SYNC_COMPLETED: "Playlist Sync Completed",
    WebhookEventType.EXTERNAL_IMPORT_STARTED: "External Import Started",
    WebhookEventType.EXTERNAL_IMPORT_COMPLETED: "External Import Completed",
    WebhookEventType.SYSTEM_HEALTH_CHANGED: "System Health Changed",
    WebhookEventType.SYSTEM_ERROR: "System Error",
}


def _title_for(event: WebhookEvent) -> str:
    return _TITLES.get(event.event_type, event.event_type.value)


def _body_for(event: WebhookEvent) -> str:
    data = event.data or {}

    title = data.get("title")
    artist_name = data.get("artist_name")
    if title and artist_name:
        return f"{title} by {artist_name}"
    if title:
        return str(title)

    name = data.get("name")
    if name:
        return str(name)

    message = data.get("message")
    if message:
        return str(message)

    return _title_for(event)


def send_apprise_notification(apprise_url: str, event: WebhookEvent) -> bool:
    """Deliver a webhook event via Apprise. Never raises -- returns False
    on any failure so the caller's retry loop can treat it the same way
    as a failed HTTP request."""
    try:
        notifier = apprise.Apprise()
        notifier.add(apprise_url)
        result = notifier.notify(title=_title_for(event), body=_body_for(event))
        return bool(result)
    except Exception as e:
        logger.warning(f"Apprise notification failed for {apprise_url}: {e}")
        return False
