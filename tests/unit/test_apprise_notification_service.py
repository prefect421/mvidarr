"""Unit tests for src/services/apprise_notification_service.py (#315).

Mocks the apprise.Apprise object -- no real network calls, no real
Apprise-supported service needed to test this.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.services.apprise_notification_service import send_apprise_notification
from src.services.webhook_service import WebhookEvent, WebhookEventType

FIXED_TIME = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _event(event_type=WebhookEventType.VIDEO_DOWNLOADED, data=None):
    return WebhookEvent(
        event_type=event_type, timestamp=FIXED_TIME, data=data or {}, metadata={}
    )


class TestSendAppriseNotification:
    def test_adds_the_url_and_calls_notify(self):
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        with patch(
            "src.services.apprise_notification_service.apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            result = send_apprise_notification("tgram://bottoken/ChatID", _event())

        mock_apprise_instance.add.assert_called_once_with("tgram://bottoken/ChatID")
        mock_apprise_instance.notify.assert_called_once()
        assert result is True

    def test_notify_receives_a_title_and_body(self):
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        with patch(
            "src.services.apprise_notification_service.apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            send_apprise_notification(
                "tgram://bottoken/ChatID",
                _event(data={"title": "Example Song", "artist_name": "Example Artist"}),
            )

        _, kwargs = mock_apprise_instance.notify.call_args
        assert kwargs["title"] == "Video Downloaded"
        assert "Example Song" in kwargs["body"]
        assert "Example Artist" in kwargs["body"]

    def test_returns_false_when_notify_returns_false(self):
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = False

        with patch(
            "src.services.apprise_notification_service.apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            result = send_apprise_notification("tgram://bottoken/ChatID", _event())

        assert result is False

    def test_returns_false_instead_of_raising_on_exception(self):
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.side_effect = RuntimeError("boom")

        with patch(
            "src.services.apprise_notification_service.apprise.Apprise",
            return_value=mock_apprise_instance,
        ):
            result = send_apprise_notification("tgram://bottoken/ChatID", _event())

        assert result is False
