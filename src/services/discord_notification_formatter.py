"""
Discord embed formatter for MVidarr webhook events (#315).

Pure functions only -- no network I/O here. _deliver_webhook() in
webhook_service.py calls format_discord_embed() to build the payload,
then does the actual HTTP POST itself (same retry/backoff/SSRF-validated
path already used for generic webhooks -- a Discord webhook URL is a
normal HTTPS URL).

No thumbnail/poster art: self-hosted MVidarr instances often have no
publicly reachable URL for Discord's servers to fetch an image from.
"""

from src.services.webhook_models import WebhookEvent, WebhookEventType

# Discord embed colors (decimal, as Discord's API expects) by outcome.
_COLOR_GREEN = 0x2ECC71  # success: added/downloaded/completed
_COLOR_RED = 0xE74C3C  # failure: failed/error
_COLOR_BLUE = 0x3498DB  # neutral/in-progress: started/updated/changed

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


def _color_for(event_type: WebhookEventType) -> int:
    value = event_type.value
    if value.endswith("_failed") or "failed" in value or "error" in value:
        return _COLOR_RED
    if (
        value.endswith("downloaded")
        or value.endswith("completed")
        or value.endswith("added")
    ):
        return _COLOR_GREEN
    return _COLOR_BLUE


def _description_for(event: WebhookEvent) -> str:
    data = event.data or {}

    title = data.get("title")
    artist_name = data.get("artist_name")
    if title and artist_name:
        return f"**{title}** by **{artist_name}**"
    if title:
        return f"**{title}**"

    name = data.get("name")
    if name:
        return f"**{name}**"

    message = data.get("message")
    if message:
        return str(message)

    # Generic fallback -- always return something non-empty rather than
    # an empty embed description, which Discord renders as a blank gap.
    return _TITLES.get(event.event_type, event.event_type.value)


def format_discord_embed(event: WebhookEvent) -> dict:
    """Build a Discord-shaped embed payload for a webhook event."""
    return {
        "embeds": [
            {
                "title": _TITLES.get(event.event_type, event.event_type.value),
                "description": _description_for(event),
                "color": _color_for(event.event_type),
                "timestamp": event.timestamp.isoformat(),
            }
        ]
    }
