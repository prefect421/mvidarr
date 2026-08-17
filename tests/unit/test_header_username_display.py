"""Regression test: the header's username display (top-right corner)
was permanently stuck on the literal hardcoded placeholder "admin"
regardless of who was actually logged in.

Root cause: checkUserAuthentication() (base.html) fetched
'/auth/check' -- a route that doesn't exist anywhere in src/ -- and,
even if it had, looked for DOM elements #userMenu/#username, neither of
which exist in the current header markup (only #headerUsername/
#headerUserRole do, from an earlier header refactor that never updated
this function). On top of that, checkUserAuthentication() was never
even called anywhere. The real, working endpoint is GET /api/auth/user
(src/api/fastapi/auth.py's get_current_user_info, mounted under the
/api/auth router prefix).
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestHeaderUsernameDisplay:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "base.html").read_text()

    def _function_body(self, signature):
        start = self.html.index(signature)
        end = self.html.index("\n        }", start)
        return self.html[start:end]

    def test_check_user_authentication_calls_the_real_user_endpoint(self):
        body = self._function_body("function checkUserAuthentication()")
        assert "/api/auth/user" in body
        assert "/auth/check" not in body

    def test_check_user_authentication_targets_the_real_header_elements(self):
        body = self._function_body("function checkUserAuthentication()")
        assert "headerUsername" in body
        assert "getElementById('username')" not in body
        assert "getElementById('userMenu')" not in body

    def test_check_user_authentication_is_actually_called_on_init(self):
        # It was defined but had zero call sites anywhere -- confirm it's
        # wired into the header's init sequence now.
        init_start = self.html.index("function initializeHeader()")
        init_end = self.html.index("\n        }", init_start)
        init_body = self.html[init_start:init_end]
        assert "checkUserAuthentication()" in init_body
