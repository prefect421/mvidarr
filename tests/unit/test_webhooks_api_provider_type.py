"""Regression/feature test for #315: the webhooks API must accept
provider_type, and must accept a plain (non-HTTP) URL string for Apprise
endpoints -- Apprise URLs like "tgram://bottoken/ChatID" or
"discord://webhook_id/token" are not standard HTTP(S) URLs and would be
rejected by Pydantic's HttpUrl validator, which the request model used
for every endpoint before this change.
"""

import pytest
from pydantic import ValidationError

from src.api.fastapi.webhooks import WebhookEndpointRequest, WebhookTestRequest


class TestWebhookEndpointRequestProviderType:
    def test_defaults_to_generic(self):
        req = WebhookEndpointRequest(url="https://example.com/hook")
        assert req.provider_type == "generic"

    def test_accepts_discord_with_a_real_https_url(self):
        req = WebhookEndpointRequest(
            url="https://discord.com/api/webhooks/123/abc", provider_type="discord"
        )
        assert req.provider_type == "discord"

    def test_accepts_an_apprise_style_non_http_url(self):
        req = WebhookEndpointRequest(
            url="tgram://bottoken/ChatID", provider_type="apprise"
        )
        assert req.url == "tgram://bottoken/ChatID"

    def test_rejects_garbage_url_for_generic(self):
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(url="not a url at all", provider_type="generic")

    def test_rejects_garbage_url_for_discord(self):
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(url="not a url at all", provider_type="discord")

    def test_rejects_empty_url_for_apprise(self):
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(url="", provider_type="apprise")

    def test_rejects_invalid_provider_type(self):
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(
                url="https://example.com/hook", provider_type="carrier_pigeon"
            )

    def test_rejects_url_with_injection_characters_for_generic(self):
        # Final-review Finding 1 (Critical, stored XSS): url is a plain
        # str (not HttpUrl) so it no longer gets percent-encoded, and
        # webhooks.html interpolates it raw into innerHTML. A URL
        # containing HTML/attribute-breakout characters must never pass
        # validation for generic/discord endpoints.
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(
                url='https://example.com/x"><img src=x onerror=alert(1)>',
                provider_type="generic",
            )

    def test_rejects_url_with_single_quote_for_discord(self):
        with pytest.raises(ValidationError):
            WebhookEndpointRequest(
                url="https://example.com/x'onmouseover='alert(1)",
                provider_type="discord",
            )

    def test_apprise_url_is_not_checked_for_injection_characters(self):
        # Apprise URLs skip the http(s)-shape check entirely (they're not
        # HTTP URLs), so this documents that the injection-character
        # check only applies within the non-apprise branch, same as the
        # scheme/netloc check it sits next to.
        req = WebhookEndpointRequest(
            url="tgram://bottoken/ChatID?title=<b>", provider_type="apprise"
        )
        assert req.url == "tgram://bottoken/ChatID?title=<b>"


class TestWebhookTestRequestInjectionCharacters:
    # WebhookTestRequest.validate_url is the identical validator to
    # WebhookEndpointRequest's -- the Test Webhook panel posts straight
    # to this model, so it needs the same Finding 1 hardening.
    def test_rejects_url_with_injection_characters_for_generic(self):
        with pytest.raises(ValidationError):
            WebhookTestRequest(
                url='https://example.com/x"><img src=x onerror=alert(1)>',
                provider_type="generic",
            )

    def test_accepts_a_clean_url(self):
        req = WebhookTestRequest(
            url="https://example.com/hook", provider_type="generic"
        )
        assert req.url == "https://example.com/hook"
