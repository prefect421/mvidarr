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
    redact_apprise_url,
    send_apprise_notification,
)
from src.services.webhook_models import WebhookEvent, WebhookEventType
from src.services.webhook_service import WebhookEndpoint, WebhookService


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


class TestRedactAppriseUrl:
    def test_keeps_only_the_scheme(self):
        assert (
            redact_apprise_url("tgram://123456789:AABBccddEE/-1001234567890")
            == "tgram://***"
        )
        assert (
            redact_apprise_url("discord://webhook_id/webhook_token") == "discord://***"
        )
        assert (
            redact_apprise_url("mailto://user:hunter2@smtp.example.com")
            == "mailto://***"
        )

    def test_handles_a_url_with_no_scheme_separator_without_raising(self):
        assert redact_apprise_url("not-a-real-url") == "unknown://***"


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

        # apprise_notification_service.py imports `apprise` locally inside
        # send_apprise_notification() (#315 Finding 7 -- so a missing
        # apprise install is a per-delivery failure, not a boot-time
        # ImportError for the whole app), so there's no module-level
        # `apprise` attribute on apprise_notification_service to patch
        # through -- patch the real `apprise` package directly instead.
        with caplog.at_level(logging.WARNING), patch(
            "apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            send_apprise_notification(secret_url, event)

        assert "AABBccddEE" not in caplog.text
        assert "-1001234567890" not in caplog.text
        assert "tgram://***" in caplog.text


class TestGetEndpointsRedactsAppriseUrls:
    """Final-review Finding 5: get_endpoints() masked `secret` as "***"
    but returned `url` in full -- for an Apprise endpoint the URL *is*
    the credential, so GET /api/webhooks/ handed it back to the browser
    unmasked, which webhooks.html then printed as-is."""

    def test_apprise_endpoint_url_is_redacted(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        service.add_endpoint(
            WebhookEndpoint(
                url="tgram://123456789:AABBccddEE/-1001234567890",
                provider_type="apprise",
            )
        )

        endpoints = service.get_endpoints()

        assert endpoints[0]["url"] == "tgram://***"

    def test_generic_endpoint_url_is_returned_in_full(self, monkeypatch):
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        service.add_endpoint(
            WebhookEndpoint(
                url="https://example.com/hook",
                provider_type="generic",
            )
        )

        endpoints = service.get_endpoints()

        assert endpoints[0]["url"] == "https://example.com/hook"


class TestCrudLogLinesRedactAppriseUrls:
    """Final-review Finding 5: add_endpoint()/remove_endpoint()/
    update_endpoint() each logged the raw URL directly, leaking the
    credential embedded in an Apprise URL into application logs."""

    def test_add_endpoint_does_not_log_the_raw_apprise_url(self, monkeypatch, caplog):
        service = _make_service_with_no_saved_endpoints(monkeypatch)

        with caplog.at_level(logging.INFO):
            service.add_endpoint(
                WebhookEndpoint(
                    url="tgram://123456789:AABBccddEE/-1001234567890",
                    provider_type="apprise",
                )
            )

        assert "AABBccddEE" not in caplog.text
        assert "tgram://***" in caplog.text

    def test_update_endpoint_does_not_log_the_raw_apprise_url(
        self, monkeypatch, caplog
    ):
        secret_url = "tgram://123456789:AABBccddEE/-1001234567890"
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        service.add_endpoint(WebhookEndpoint(url=secret_url, provider_type="apprise"))
        caplog.clear()

        with caplog.at_level(logging.INFO):
            service.update_endpoint(secret_url, {"enabled": False})

        assert "AABBccddEE" not in caplog.text
        assert "tgram://***" in caplog.text

    def test_remove_endpoint_does_not_log_the_raw_apprise_url(
        self, monkeypatch, caplog
    ):
        # remove_endpoint() only ever receives a bare URL string, not a
        # WebhookEndpoint with a tracked provider_type -- the redaction
        # here keys off the URL's own scheme (non-http(s) == credential
        # bearing) rather than a lookup against the stored endpoint.
        secret_url = "tgram://123456789:AABBccddEE/-1001234567890"
        service = _make_service_with_no_saved_endpoints(monkeypatch)
        service.add_endpoint(WebhookEndpoint(url=secret_url, provider_type="apprise"))
        caplog.clear()

        with caplog.at_level(logging.INFO):
            service.remove_endpoint(secret_url)

        assert "AABBccddEE" not in caplog.text
        assert "tgram://***" in caplog.text
