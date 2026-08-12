"""Regression test for #336: no admin UI existed to configure OAuth
provider credentials — the entire feature was settings-table-driven with
zero corresponding fields on the Settings page (oauth_service.py's
_load_providers() reads nine oauth_* keys that settings.html never
exposed at all).

Same static-content-assertion approach as the other template regression
tests in this suite (e.g. test_2fa_setup_link_target.py): confirms the
real setting keys oauth_service.py actually reads are present as form
fields, and that client secrets are excluded from the page's generic
settings-load loop (see settings.py's OAUTH_SECRET_KEYS for the matching
backend-side "blank means unchanged" behavior this depends on).
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"

# Exactly the keys OAuthService._load_providers() reads.
REAL_OAUTH_SETTING_KEYS = [
    "oauth_authentik_base_url",
    "oauth_authentik_client_id",
    "oauth_authentik_client_secret",
    "oauth_authentik_redirect_uri",
    "oauth_google_client_id",
    "oauth_google_client_secret",
    "oauth_google_redirect_uri",
    "oauth_github_client_id",
    "oauth_github_client_secret",
    "oauth_github_redirect_uri",
]

OAUTH_SECRET_KEYS = [
    "oauth_authentik_client_secret",
    "oauth_google_client_secret",
    "oauth_github_client_secret",
]


class TestOAuthSettingsUI:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_every_real_oauth_setting_key_has_a_form_field(self):
        for key in REAL_OAUTH_SETTING_KEYS:
            assert f'name="{key}"' in self.html, (
                f"settings.html has no input for {key}, which "
                "OAuthService._load_providers() reads"
            )

    def test_client_secret_fields_are_password_type(self):
        for key in OAUTH_SECRET_KEYS:
            assert f'id="{key}" name="{key}"' in self.html
            # Confirm it's specifically a password-type input, not just
            # present anywhere in the key's name substring match.
            start = self.html.index(f'id="{key}"')
            tag = self.html[max(0, start - 40) : start + 100]
            assert 'type="password"' in tag

    def test_client_secrets_are_excluded_from_the_generic_load_loop(self):
        assert "OAUTH_SECRET_SETTING_KEYS" in self.html
        for key in OAUTH_SECRET_KEYS:
            assert f"'{key}'" in self.html

    def test_redirect_uri_defaults_match_the_real_callback_route(self):
        # The real route is /api/auth/oauth/{provider}/callback
        # (src/api/fastapi/auth.py's oauth_callback).
        assert "/api/auth/oauth/${provider}/callback" in self.html
