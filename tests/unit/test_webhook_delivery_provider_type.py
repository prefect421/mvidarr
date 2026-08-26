"""Regression/feature test for #315: _deliver_webhook() and
test_endpoint() must format the payload per endpoint.provider_type
instead of always sending the generic MVidarr envelope, which a real
Discord webhook rejects and which isn't how Apprise delivery works at
all.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.services.webhook_service import (
    WebhookEndpoint,
    WebhookEvent,
    WebhookEventType,
    WebhookService,
)


def _make_service_with_no_saved_endpoints(monkeypatch):
    monkeypatch.setattr(
        "src.services.webhook_service.SettingsService.get_json",
        lambda key, default: {"endpoints": []},
    )
    return WebhookService()


class TestDeliverWebhookProviderTypeBranching:
    def test_discord_endpoint_posts_the_embed_shaped_payload(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        endpoint = WebhookEndpoint(
            url="https://discord.com/api/webhooks/123/abc",
            provider_type="discord",
            max_retries=0,
        )
        event = WebhookEvent(
            event_type=WebhookEventType.VIDEO_DOWNLOADED,
            timestamp=datetime.now(),
            data={},
            metadata={},
        )

        with patch("src.services.webhook_service.requests.post") as mock_post, patch(
            "src.utils.url_validator.validate_url_or_raise"
        ):
            mock_post.return_value = MagicMock(status_code=204)
            service._deliver_webhook(endpoint, event)
            time.sleep(0.2)  # delivery runs in a background thread

        _, kwargs = mock_post.call_args
        assert "embeds" in kwargs["json"]

    def test_apprise_endpoint_calls_send_apprise_notification_not_requests_post(
        self, monkeypatch
    ):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        endpoint = WebhookEndpoint(
            url="tgram://bottoken/ChatID", provider_type="apprise", max_retries=0
        )
        event = WebhookEvent(
            event_type=WebhookEventType.VIDEO_DOWNLOADED,
            timestamp=datetime.now(),
            data={},
            metadata={},
        )

        with patch(
            "src.services.webhook_service.send_apprise_notification"
        ) as mock_send, patch(
            "src.services.webhook_service.requests.post"
        ) as mock_post:
            mock_send.return_value = True
            service._deliver_webhook(endpoint, event)
            time.sleep(0.2)

        mock_send.assert_called_once_with("tgram://bottoken/ChatID", event)
        mock_post.assert_not_called()

    def test_generic_endpoint_still_posts_the_raw_envelope(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        endpoint = WebhookEndpoint(
            url="https://example.com/hook", provider_type="generic", max_retries=0
        )
        event = WebhookEvent(
            event_type=WebhookEventType.VIDEO_DOWNLOADED,
            timestamp=datetime.now(),
            data={"title": "Example"},
            metadata={},
        )

        with patch("src.services.webhook_service.requests.post") as mock_post, patch(
            "src.utils.url_validator.validate_url_or_raise"
        ):
            mock_post.return_value = MagicMock(status_code=204)
            service._deliver_webhook(endpoint, event)
            time.sleep(0.2)

        _, kwargs = mock_post.call_args
        assert kwargs["json"] == event.to_dict()


class TestTestEndpointProviderTypeBranching:
    def test_discord_test_sends_an_embed_shaped_payload(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)

        with patch("src.services.webhook_service.requests.post") as mock_post, patch(
            "src.utils.url_validator.validate_url_or_raise"
        ):
            mock_post.return_value = MagicMock(
                status_code=204, elapsed=MagicMock(total_seconds=lambda: 0.1), text=""
            )
            service.test_endpoint(
                "https://discord.com/api/webhooks/123/abc", provider_type="discord"
            )

        _, kwargs = mock_post.call_args
        assert "embeds" in kwargs["json"]

    def test_apprise_test_calls_send_apprise_notification(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)

        with patch(
            "src.services.webhook_service.send_apprise_notification"
        ) as mock_send:
            mock_send.return_value = True
            result = service.test_endpoint(
                "tgram://bottoken/ChatID", provider_type="apprise"
            )

        mock_send.assert_called_once()
        assert result["success"] is True
