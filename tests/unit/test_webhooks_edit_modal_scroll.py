"""Regression test: the Edit Webhook modal's content could run off the
bottom of the page with no way to scroll down to reach the Save/Cancel
buttons -- .modal-content had no max-height or overflow-y at all.

Same class of bug and same fix pattern as the #351 login-card fix
(max-height + overflow-y: auto).
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestWebhooksEditModalScroll:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "webhooks.html").read_text()

    def test_modal_content_has_a_max_height_and_scrolls(self):
        start = self.html.index(".modal-content {")
        end = self.html.index("}", start)
        rule = self.html[start:end]
        assert "max-height" in rule
        assert "overflow-y: auto" in rule
