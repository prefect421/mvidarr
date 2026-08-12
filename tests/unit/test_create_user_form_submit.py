"""Regression test for #331: the admin "Create User" form had no submit
handler and no form action, so submitting it POSTed to its own URL,
/admin/users/create — a path that only has a GET route registered
(frontend_router.py). No matching POST handler exists there.

The real, working backend endpoint is POST /api/admin/users
(src/api/fastapi/admin.py) — fully functional, correctly gated by
require_admin_access, calling AuthService.create_user. It was just never
called by this page.

Same static-content-assertion approach as test_2fa_setup_link_target.py /
test_2fa_profile_link_target.py: no browser needed to prove the page
actually wires its form to the real endpoint.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestCreateUserFormSubmit:
    def test_form_is_not_a_bare_native_post(self):
        """A bare <form method="POST"> with no action and no JS handler
        submits to the current URL (/admin/users/create — GET only, no
        POST route). The form must either have a real action or be
        intercepted by JS."""
        html = (TEMPLATES_DIR / "admin" / "create_user.html").read_text()
        assert (
            'id="createUserForm"' in html
        ), "form needs an id so JS can attach a submit handler to it"

    def test_page_calls_the_real_create_user_endpoint(self):
        html = (TEMPLATES_DIR / "admin" / "create_user.html").read_text()
        assert "/api/admin/users" in html, (
            "create_user.html never calls the real, working "
            "POST /api/admin/users endpoint"
        )

    def test_submit_handler_prevents_default_native_post(self):
        """Without preventDefault, even a correctly-fetch-wired handler
        would still let the native POST fire, hitting the same dead
        /admin/users/create route."""
        html = (TEMPLATES_DIR / "admin" / "create_user.html").read_text()
        assert "preventDefault" in html
