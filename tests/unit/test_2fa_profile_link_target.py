"""Regression test: 2FA setup's "Return to Profile"/"Cancel" links, and
dashboard's "Manage two-factor authentication" link, must point at a real
page.

Root cause: /profile is not a registered route anywhere in this app (no
frontend_router.py route, no template_system.py handler) — it 404s with
FastAPI's default JSON {"detail":"Not Found"}, which is what a browser's
devtools JSON viewer was showing users after completing 2FA setup and
clicking "Return to Profile."

The real page that actually hosts 2FA management is /settings, in the
#twoFactorSection section (settings.html) — confirmed live via
test_2fa_setup_link_target.py's sibling regression coverage of the same
section.
"""

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"

# Any href pointing at the nonexistent /profile page (with or without a
# trailing slash or #fragment) is the regression this test guards against.
DEAD_PROFILE_LINK_PATTERN = re.compile(r'href=["\']\/profile\/?(#[^"\']*)?["\']')

REAL_DESTINATION = "/settings#twoFactorSection"


class TestTwoFactorProfileLinkTarget:
    def test_2fa_setup_page_links_to_real_settings_page(self):
        html = (TEMPLATES_DIR / "auth" / "2fa_setup.html").read_text()
        assert not DEAD_PROFILE_LINK_PATTERN.search(html), (
            "auth/2fa_setup.html links to /profile, which is not a "
            f"registered route — should link to {REAL_DESTINATION}"
        )
        assert REAL_DESTINATION in html

    def test_dashboard_page_links_to_real_settings_page(self):
        html = (TEMPLATES_DIR / "dashboard.html").read_text()
        assert not DEAD_PROFILE_LINK_PATTERN.search(html), (
            "dashboard.html links to /profile, which is not a registered "
            f"route — should link to {REAL_DESTINATION}"
        )
        assert REAL_DESTINATION in html
