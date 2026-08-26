"""Static-content regression test for the frontend/backend password-length
mismatch reported in dev testing: updateCredentials() in main.js accepted
any password >= 6 characters and forwarded it to POST /api/auth/credentials,
but SimpleAuthService.set_credentials() (see test_credentials_endpoint.py)
requires >= 8 -- a 6-7 char password, including "mvidarr" (the bootstrap
default), passed the frontend check only to be rejected by the backend
with a message the frontend's apiRequest() then discarded (it read
data.error; FastAPI's HTTPException returns data.detail), surfacing as a
bare "HTTP error! status: 400".

The Settings page itself (settings.html's userCredentialsSection) had its
own separate copies of the stale 6-char rule -- a <small> hint and, worse,
HTML minlength="6" attributes on both the password and confirm-password
inputs, which enforce browser-native validation independently of the JS
check above. Found by the user reading the actual rendered page after the
main.js fix, since that fix alone didn't touch this template.

Matches the static-content-assertion approach already established this
session for template/script changes (e.g. test_login_page_redesign_ui.py):
reads the raw source, no browser/render step.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static"
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestUpdateCredentialsLengthMatchesBackend:
    def setup_method(self):
        self.js = (STATIC_DIR / "main.js").read_text()

    def test_frontend_minimum_is_eight_not_six(self):
        assert "password.length < 8" in self.js
        assert "password.length < 6" not in self.js

    def test_frontend_message_matches_the_enforced_minimum(self):
        assert "Password must be at least 8 characters long" in self.js
        assert "Password must be at least 6 characters long" not in self.js


class TestSettingsPageCredentialsFormMatchesBackend:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_password_field_hint_matches_the_enforced_minimum(self):
        assert "Password must be at least 8 characters long" in self.html
        assert "Password must be at least 6 characters long" not in self.html

    def test_password_and_confirm_fields_use_minlength_eight(self):
        assert 'id="auth_password" name="auth_password"' in self.html
        assert 'id="auth_password_confirm"' in self.html
        assert 'minlength="6"' not in self.html
        # Both the password and its confirm field carry minlength="8" --
        # count rather than a single substring check so a regression in
        # either one is still caught.
        assert self.html.count('minlength="8"') >= 2


class TestApiRequestSurfacesFastApiErrorDetail:
    def setup_method(self):
        self.js = (STATIC_DIR / "main.js").read_text()

    def test_api_request_checks_detail_before_falling_back_to_generic_message(self):
        # FastAPI's HTTPException responses are {"detail": "..."}, not
        # {"error": "..."} -- apiRequest must check data.detail (in
        # addition to the legacy data.error some endpoints still use)
        # or every FastAPI validation message gets silently replaced
        # with "HTTP error! status: <code>".
        assert "data.detail || data.error" in self.js
