"""Regression/feature test for #315: the Add Webhook form gains a Type
selector (Generic / Discord / Apprise). Selecting a type shows/hides
the relevant fields (Discord/Apprise don't use a secret or custom
headers -- Discord webhooks don't do HMAC, and Apprise's URL string is
the entire config). getFormData() includes provider_type in the
payload sent to POST /api/webhooks/.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestWebhooksProviderTypeUI:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "webhooks.html").read_text()

    def test_type_selector_exists_with_all_three_options(self):
        assert 'id="webhookProviderType"' in self.html
        start = self.html.index('id="webhookProviderType"')
        end = self.html.index("</select>", start)
        select_html = self.html[start:end]
        assert 'value="generic"' in select_html
        assert 'value="discord"' in select_html
        assert 'value="apprise"' in select_html

    def test_type_selector_has_a_change_handler(self):
        start = self.html.index('id="webhookProviderType"')
        end = self.html.index(">", start)
        tag = self.html[start:end]
        assert "onchange=" in tag

    def test_a_handler_function_exists_to_toggle_fields_by_type(self):
        assert "function updateWebhookFormForProviderType" in self.html

    def test_get_form_data_includes_provider_type(self):
        start = self.html.index("function getFormData()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "provider_type" in body
        assert "webhookProviderType" in body

    def test_hide_webhook_form_resyncs_provider_type_toggle_state(self):
        # hideWebhookForm() calls webhookConfigForm.reset(), which resets the
        # <select> back to "generic" but does NOT undo the field
        # show/hide/relabel side effects applied by
        # updateWebhookFormForProviderType(). Without an explicit resync
        # call, reopening the form after a reset leaves the URL
        # field/label/hint and Secret/Custom-Headers groups stuck in
        # whatever provider mode was last selected, desynced from the
        # (reset) dropdown value.
        start = self.html.index("function hideWebhookForm()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "updateWebhookFormForProviderType()" in body

    def test_show_add_webhook_form_syncs_provider_type_toggle_state(self):
        start = self.html.index("function showAddWebhookForm()")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "updateWebhookFormForProviderType()" in body
