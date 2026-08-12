"""Regression test for a live incident (2026-08-12): after saving OAuth
settings via the new #336 UI and restarting the app, the login page
showed no OAuth provider buttons at all — even though the settings were
genuinely saved to the database.

Root cause: oauth_service is a module-level singleton
(src/services/oauth_service.py's `oauth_service = OAuthService()`),
constructed once at Python import time — which happens before
fastapi_app.py finishes initializing the database connection.
SettingsService.load_cache() correctly detects this
("Database not initialized") and deliberately avoids marking its own
cache as loaded, so IT retries successfully on the next call. But
OAuthService.__init__ -> _load_providers() only ever runs once: every
SettingsService.get(oauth_*) call during that one doomed attempt returns
"" (not found), so self.providers is permanently left {} for the rest
of the process's life. Confirmed via fastapi_error.log: "Failed to load
settings cache: Database not initialized" immediately followed by
"Setting 'oauth_authentik_base_url' not found" etc. for all nine oauth_*
keys, on a restart that happened after those exact settings were
already committed to the database.
"""

from unittest.mock import patch

from src.services.oauth_service import OAuthService

_VALID_AUTHENTIK_SETTINGS = {
    "oauth_authentik_base_url": "https://auth.example.com",
    "oauth_authentik_client_id": "client-id",
    "oauth_authentik_client_secret": "client-secret",
    "oauth_authentik_redirect_uri": "https://mvidarr.example.com/api/auth/oauth/authentik/callback",
}


class TestOAuthServiceSurvivesTheBootRace:
    def test_construction_during_the_db_not_ready_race_does_not_permanently_break_it(
        self,
    ):
        # Simulate exactly what the logs showed: every setting lookup
        # fails during __init__ because the database isn't initialized
        # yet at Python import time.
        with patch(
            "src.services.settings_service.SettingsService.get", return_value=""
        ):
            service = OAuthService()

        assert service.get_available_providers() == {}

        # The database is now genuinely ready and the settings are
        # genuinely saved (matching the real post-restart state) — but
        # nothing has explicitly called reload_settings(). A real login
        # page render just calls get_available_providers().
        with patch(
            "src.services.settings_service.SettingsService.get",
            side_effect=lambda key, default=None: _VALID_AUTHENTIK_SETTINGS.get(
                key, default
            ),
        ):
            assert "authentik" in service.get_available_providers()

    def test_get_provider_also_self_heals(self):
        with patch(
            "src.services.settings_service.SettingsService.get", return_value=""
        ):
            service = OAuthService()

        with patch(
            "src.services.settings_service.SettingsService.get",
            side_effect=lambda key, default=None: _VALID_AUTHENTIK_SETTINGS.get(
                key, default
            ),
        ):
            assert service.get_provider("authentik") is not None

    def test_is_oauth_enabled_also_self_heals(self):
        """The actual gate the login page checks first
        (template_system.py: `if oauth_service.is_oauth_enabled():
        oauth_providers = oauth_service.get_available_providers()`) — if
        this alone doesn't self-heal, get_available_providers() is never
        even called and the login page shows no OAuth section at all,
        regardless of what get_available_providers() itself would return.
        """
        with patch(
            "src.services.settings_service.SettingsService.get", return_value=""
        ):
            service = OAuthService()
        assert service.is_oauth_enabled() is False

        with patch(
            "src.services.settings_service.SettingsService.get",
            side_effect=lambda key, default=None: _VALID_AUTHENTIK_SETTINGS.get(
                key, default
            ),
        ):
            assert service.is_oauth_enabled() is True
