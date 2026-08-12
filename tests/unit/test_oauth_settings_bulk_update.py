"""Tests for #336: OAuth provider settings, saved via the bulk settings
endpoint.

Covers two behaviors added alongside the new admin UI:

1. Blank oauth_*_client_secret values must NOT overwrite an already-saved
   secret. The settings page has a single page-wide "Save" button that
   PUTs every input's current value in one request — a client_secret
   field left blank (because the admin was only editing an unrelated
   setting, and the real secret is deliberately never round-tripped back
   into the field on page load) would otherwise silently wipe the stored
   secret on the next save.
2. oauth_service is a module-level singleton that loads provider config
   once at process start (OAuthService.__init__ -> _load_providers). A
   bulk update touching any oauth_* key must reload it, the same way an
   update touching spotify_* keys already reloads spotify_service — see
   the sibling "Auto-reload Spotify service" block this mirrors.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth_dependencies import require_admin
from src.api.fastapi.settings import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: {
        "user_id": 1,
        "username": "admin",
        "role": "ADMIN",
        "authenticated": True,
    }
    return TestClient(app)


class TestBlankSecretDoesNotOverwrite:
    def test_blank_oauth_client_secret_is_excluded_from_the_write(self):
        client = _make_client()

        with patch(
            "src.api.fastapi.settings.settings.set_multiple", return_value=True
        ) as mock_set_multiple, patch(
            "src.api.fastapi.settings.oauth_service.reload_settings"
        ):
            response = client.put(
                "/api/settings/bulk",
                json={
                    "settings": {
                        "oauth_authentik_client_id": "new-client-id",
                        "oauth_authentik_client_secret": "",
                    }
                },
            )

        assert response.status_code == 200
        written = mock_set_multiple.call_args[0][0]
        assert written["oauth_authentik_client_id"] == "new-client-id"
        assert "oauth_authentik_client_secret" not in written

    def test_non_blank_oauth_client_secret_is_written_normally(self):
        client = _make_client()

        with patch(
            "src.api.fastapi.settings.settings.set_multiple", return_value=True
        ) as mock_set_multiple, patch(
            "src.api.fastapi.settings.oauth_service.reload_settings"
        ):
            response = client.put(
                "/api/settings/bulk",
                json={
                    "settings": {
                        "oauth_authentik_client_secret": "a-real-secret",
                    }
                },
            )

        assert response.status_code == 200
        written = mock_set_multiple.call_args[0][0]
        assert written["oauth_authentik_client_secret"] == "a-real-secret"


class TestOAuthServiceReloadedAfterBulkUpdate:
    def test_oauth_key_update_triggers_reload(self):
        client = _make_client()

        with patch(
            "src.api.fastapi.settings.settings.set_multiple", return_value=True
        ), patch(
            "src.api.fastapi.settings.oauth_service.reload_settings"
        ) as mock_reload:
            client.put(
                "/api/settings/bulk",
                json={"settings": {"oauth_google_client_id": "abc"}},
            )

        mock_reload.assert_called_once()

    def test_unrelated_key_update_does_not_trigger_reload(self):
        client = _make_client()

        with patch(
            "src.api.fastapi.settings.settings.set_multiple", return_value=True
        ), patch(
            "src.api.fastapi.settings.oauth_service.reload_settings"
        ) as mock_reload:
            client.put(
                "/api/settings/bulk",
                json={"settings": {"ui_theme": "dark"}},
            )

        mock_reload.assert_not_called()
