"""Regression/feature test for #315: WebhookEndpoint gains a
provider_type field ("generic" | "discord" | "apprise") so
_deliver_webhook() can format payloads correctly per destination
instead of always sending the same generic MVidarr envelope (which a
real Discord webhook would reject -- it validates against its own
{content, embeds: [...]} schema).

Defaults to "generic" so every endpoint saved before this field
existed loads and behaves exactly as it does today -- no migration.
"""

from src.services.webhook_service import WebhookEndpoint, WebhookService


class TestWebhookEndpointProviderType:
    def test_defaults_to_generic(self):
        endpoint = WebhookEndpoint(url="https://example.com/hook")
        assert endpoint.provider_type == "generic"

    def test_accepts_discord_and_apprise(self):
        discord_ep = WebhookEndpoint(
            url="https://discord.com/api/webhooks/123/abc",
            provider_type="discord",
        )
        assert discord_ep.provider_type == "discord"

        apprise_ep = WebhookEndpoint(
            url="tgram://bottoken/ChatID", provider_type="apprise"
        )
        assert apprise_ep.provider_type == "apprise"


class TestLoadEndpointsDefaultsProviderType:
    def test_pre_existing_saved_endpoint_with_no_provider_type_loads_as_generic(
        self, monkeypatch
    ):
        """Simulates real pre-existing data: a webhooks_config JSON blob
        saved before this field existed, with no provider_type key at
        all. Must load as "generic", not crash or default to None."""
        saved_config = {
            "endpoints": [
                {
                    "url": "https://example.com/hook",
                    "secret": None,
                    "events": [],
                    "enabled": True,
                    "max_retries": 3,
                    "timeout": 30,
                    "headers": {},
                    # deliberately no "provider_type" key
                }
            ]
        }
        monkeypatch.setattr(
            "src.services.webhook_service.SettingsService.get_json",
            lambda key, default: saved_config,
        )

        service = WebhookService()

        assert len(service.endpoints) == 1
        assert service.endpoints[0].provider_type == "generic"


class TestGetEndpointsIncludesProviderType:
    def test_get_endpoints_reports_provider_type(self, monkeypatch):
        monkeypatch.setattr(
            "src.services.webhook_service.SettingsService.get_json",
            lambda key, default: {"endpoints": []},
        )
        service = WebhookService()
        service.endpoints = [
            WebhookEndpoint(url="https://example.com/hook", provider_type="discord")
        ]

        result = service.get_endpoints()

        assert result[0]["provider_type"] == "discord"
