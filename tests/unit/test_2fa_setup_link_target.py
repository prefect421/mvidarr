"""Regression test: the "Enable Two-Factor Authentication" link must point
at the real HTML setup page, not the JSON-stub route of the same name.

Root cause of the original bug: settings.html and dashboard.html both
linked to /2fa/setup, a plain browser navigation target. That path is
served by two_factor_auth.py's setup_page — an unfinished placeholder
(literally commented "In a real implementation, this would render the 2FA
setup template. For now, return setup instructions") that always returns
JSONResponse regardless of its response_class=HTMLResponse annotation, so
clicking the link showed the browser's raw JSON viewer instead of a page.

The real, fully-built setup page (QR code, manual entry key, backup codes,
token confirmation form) lives at /auth/2fa/setup, registered in
frontend_router.py's two_fa_setup_page -> auth/2fa_setup.html. The two
paths differ only by the /auth prefix, and both resolve, which is exactly
why the wrong one silently "worked" (200 OK) without any error to notice.
"""

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"

# The JSON-stub route. Any href pointing exactly here (not /auth/2fa/setup)
# is the regression this test guards against.
STUB_PATH_PATTERN = re.compile(r'href=["\']\/2fa\/setup["\']')

REAL_SETUP_PATH = "/auth/2fa/setup"


class TestTwoFactorSetupLinkTarget:
    def test_settings_page_links_to_real_setup_page(self):
        html = (TEMPLATES_DIR / "settings.html").read_text()
        assert not STUB_PATH_PATTERN.search(html), (
            "settings.html links to the /2fa/setup JSON stub instead of "
            f"the real {REAL_SETUP_PATH} HTML page"
        )
        assert REAL_SETUP_PATH in html

    def test_dashboard_page_links_to_real_setup_page(self):
        html = (TEMPLATES_DIR / "dashboard.html").read_text()
        assert not STUB_PATH_PATTERN.search(html), (
            "dashboard.html links to the /2fa/setup JSON stub instead of "
            f"the real {REAL_SETUP_PATH} HTML page"
        )
        assert REAL_SETUP_PATH in html
