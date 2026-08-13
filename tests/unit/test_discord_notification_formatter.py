"""Unit tests for src/services/discord_notification_formatter.py (#315).

Pure function, no I/O -- given a WebhookEvent, returns a Discord-shaped
embed payload. No thumbnail/image art (self-hosted instances often have
no publicly reachable URL for Discord to fetch an image from -- design
doc's explicit non-goal).
"""

from datetime import datetime, timezone

from src.services.discord_notification_formatter import format_discord_embed
from src.services.webhook_service import WebhookEvent, WebhookEventType

FIXED_TIME = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _event(event_type, data=None):
    return WebhookEvent(
        event_type=event_type, timestamp=FIXED_TIME, data=data or {}, metadata={}
    )


class TestFormatDiscordEmbed:
    def test_returns_a_single_embed_in_the_embeds_list(self):
        payload = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOADED))
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

    def test_embed_has_no_image_or_thumbnail_keys(self):
        embed = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOADED))[
            "embeds"
        ][0]
        assert "image" not in embed
        assert "thumbnail" not in embed

    def test_embed_includes_iso_timestamp(self):
        embed = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOADED))[
            "embeds"
        ][0]
        assert embed["timestamp"] == FIXED_TIME.isoformat()

    def test_downloaded_event_is_green(self):
        embed = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOADED))[
            "embeds"
        ][0]
        assert embed["color"] == 0x2ECC71  # green

    def test_download_failed_event_is_red(self):
        embed = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOAD_FAILED))[
            "embeds"
        ][0]
        assert embed["color"] == 0xE74C3C  # red

    def test_system_error_event_is_red(self):
        embed = format_discord_embed(_event(WebhookEventType.SYSTEM_ERROR))["embeds"][
            0
        ]
        assert embed["color"] == 0xE74C3C

    def test_started_event_is_blue(self):
        embed = format_discord_embed(_event(WebhookEventType.DOWNLOAD_STARTED))[
            "embeds"
        ][0]
        assert embed["color"] == 0x3498DB  # blue

    def test_title_is_human_readable_not_the_raw_enum_value(self):
        embed = format_discord_embed(_event(WebhookEventType.VIDEO_DOWNLOADED))[
            "embeds"
        ][0]
        assert embed["title"] == "Video Downloaded"
        assert "video.downloaded" not in embed["title"]

    def test_description_incorporates_event_data(self):
        embed = format_discord_embed(
            _event(
                WebhookEventType.VIDEO_DOWNLOADED,
                data={"title": "Example Song", "artist_name": "Example Artist"},
            )
        )["embeds"][0]
        assert "Example Song" in embed["description"]
        assert "Example Artist" in embed["description"]

    def test_description_falls_back_gracefully_with_no_data(self):
        embed = format_discord_embed(_event(WebhookEventType.SYSTEM_HEALTH_CHANGED))[
            "embeds"
        ][0]
        assert isinstance(embed["description"], str)
        assert len(embed["description"]) > 0
