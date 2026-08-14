"""Security regression test: Apprise URLs embed their credential directly
in the URL string by design (tgram://<bot_token>/<chat_id>,
discord://<id>/<token>, mailto://user:password@host). Log lines must never
contain the raw URL -- only the scheme -- so a delivery failure doesn't
write a live, usable credential into observability output.
"""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.services.apprise_notification_service import (
    _redact_apprise_url,
    send_apprise_notification,
)
from src.services.webhook_models import WebhookEvent, WebhookEventType


class TestRedactAppriseUrl:
    def test_keeps_only_the_scheme(self):
        assert (
            _redact_apprise_url("tgram://123456789:AABBccddEE/-1001234567890")
            == "tgram://***"
        )
        assert (
            _redact_apprise_url("discord://webhook_id/webhook_token") == "discord://***"
        )
        assert (
            _redact_apprise_url("mailto://user:hunter2@smtp.example.com")
            == "mailto://***"
        )

    def test_handles_a_url_with_no_scheme_separator_without_raising(self):
        assert _redact_apprise_url("not-a-real-url") == "unknown://***"


class TestAppriseServiceNeverLogsTheRawUrl:
    def test_exception_log_does_not_contain_the_credential(self, caplog):
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.side_effect = RuntimeError("boom")

        secret_url = "tgram://123456789:AABBccddEE/-1001234567890"
        event = WebhookEvent(
            event_type=WebhookEventType.VIDEO_DOWNLOADED,
            timestamp=datetime(2026, 8, 13, tzinfo=timezone.utc),
            data={},
            metadata={},
        )

        with caplog.at_level(logging.WARNING), patch(
            "src.services.apprise_notification_service.apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            send_apprise_notification(secret_url, event)

        assert "AABBccddEE" not in caplog.text
        assert "-1001234567890" not in caplog.text
        assert "tgram://***" in caplog.text
