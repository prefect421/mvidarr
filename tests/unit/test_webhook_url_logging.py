"""Regression test for #369: webhook_service.py logged raw endpoint
URLs, which may embed credentials -- same risk class as #315's
Apprise-specific redaction fix, but for the generic/Discord HTTP
delivery path this time.

Apprise URLs always carry a credential (tgram://<bot_token>/<chat_id>,
etc. -- already redacted since #315). A Discord webhook URL
(https://discord.com/api/webhooks/{id}/{token}) ALWAYS carries a
credential too -- the token IS the path. A truly generic http(s)
webhook URL might or might not, so this fix does not blanket-redact
every http(s) URL -- only Apprise-shaped and Discord-shaped ones.

`_log_safe_url()` (webhook_service.py) already existed from #315's fix
wave and already handled the Apprise case; this extends it to also
redact Discord, and wires the three remaining raw-`endpoint.url` log
lines in `_deliver_webhook()`'s generic/discord HTTP path plus the two
raw-URL log lines in webhooks.py's create_webhook()/test_webhook()
(previously apprise-only) to use it.
"""

import logging
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.webhook_models import WebhookEvent, WebhookEventType
from src.services.webhook_service import (
    WebhookEndpoint,
    WebhookService,
    log_safe_url,
)


class TestLogSafeUrl:
    def test_generic_http_url_is_returned_unchanged(self):
        assert (
            log_safe_url("https://example.com/my-webhook-endpoint")
            == "https://example.com/my-webhook-endpoint"
        )

    def test_apprise_url_is_redacted_to_scheme_only(self):
        assert (
            log_safe_url("tgram://123456789:AABBccddEE/-1001234567890") == "tgram://***"
        )

    def test_discord_webhook_url_redacts_the_credential_bearing_path(self):
        url = "https://discord.com/api/webhooks/123456789012345678/AbCdEfGhIjKlMnOpQrStUvWxYz"
        redacted = log_safe_url(url)
        assert "AbCdEfGhIjKlMnOpQrStUvWxYz" not in redacted
        assert redacted.startswith("https://discord.com/api/webhooks/")

    def test_discordapp_com_legacy_host_is_also_redacted(self):
        url = "https://discordapp.com/api/webhooks/123456789012345678/secrettoken"
        redacted = log_safe_url(url)
        assert "secrettoken" not in redacted


def _make_service_with_no_saved_endpoints(monkeypatch):
    monkeypatch.setattr(
        "src.services.webhook_service.SettingsService.get_json",
        lambda key, default: {"endpoints": []},
    )
    monkeypatch.setattr(
        "src.services.webhook_service.SettingsService.set_json",
        lambda key, value: None,
    )
    return WebhookService()


class TestDeliverWebhookLogsDoNotContainTheRawDiscordToken:
    def test_success_failure_and_permanent_failure_logs_redact_the_discord_token(
        self, monkeypatch, caplog
    ):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        secret_token = "AbCdEfGhIjKlMnOpQrStUvWxYzSecretToken"
        endpoint = WebhookEndpoint(
            url=f"https://discord.com/api/webhooks/123456789012345678/{secret_token}",
            provider_type="discord",
            max_retries=0,
        )
        event = WebhookEvent(
            event_type=WebhookEventType.VIDEO_DOWNLOADED,
            timestamp=datetime.now(),
            data={},
            metadata={},
        )

        with caplog.at_level(logging.WARNING), patch(
            "src.services.webhook_service.requests.post"
        ) as mock_post, patch("src.utils.url_validator.validate_url_or_raise"):
            mock_post.return_value = MagicMock(status_code=400)
            service._deliver_webhook(endpoint, event)
            time.sleep(0.2)  # delivery runs in a background thread

        assert secret_token not in caplog.text
