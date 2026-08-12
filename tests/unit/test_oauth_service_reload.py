"""Regression test for #336: OAuthService loads its provider config once
at process start (__init__ -> _load_providers) and never again — a
provider newly configured via Settings would be invisible to the running
app's login page until it was restarted, without an explicit reload."""

from unittest.mock import patch

from src.services.oauth_service import OAuthService


class TestOAuthServiceReload:
    def test_reload_settings_picks_up_a_newly_configured_provider(self):
        service = OAuthService()
        assert "github" not in service.get_available_providers()

        with patch(
            "src.services.settings_service.SettingsService.get",
            side_effect=lambda key: {
                "oauth_github_client_id": "id",
                "oauth_github_client_secret": "secret",
                "oauth_github_redirect_uri": "https://example.test/callback",
            }.get(key),
        ):
            service.reload_settings()

        assert "github" in service.get_available_providers()

    def test_reload_settings_drops_a_provider_that_was_removed(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            side_effect=lambda key: {
                "oauth_github_client_id": "id",
                "oauth_github_client_secret": "secret",
                "oauth_github_redirect_uri": "https://example.test/callback",
            }.get(key),
        ):
            service = OAuthService()
        assert "github" in service.get_available_providers()

        with patch(
            "src.services.settings_service.SettingsService.get", return_value=None
        ):
            service.reload_settings()

        assert "github" not in service.get_available_providers()
