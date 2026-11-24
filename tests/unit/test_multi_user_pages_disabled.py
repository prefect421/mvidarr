"""#649: the Create User / User Details pages 500 and DB-backed users cannot
log in (#650), so both redirect to /admin until multi-user support (v2.0)."""

import asyncio
import pathlib

import src.api.fastapi.frontend_router as fr


def test_create_user_page_redirects_to_admin():
    resp = asyncio.run(fr.admin_create_user(request=None, user={"role": "admin"}))
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin"


def test_user_details_page_redirects_to_admin():
    resp = asyncio.run(
        fr.admin_user_details(request=None, user_id=3, admin_user={"role": "admin"})
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin"


def test_no_links_to_the_disabled_create_page():
    for t in ("admin/users.html", "admin/dashboard.html"):
        text = pathlib.Path("frontend/templates", t).read_text()
        assert 'href="/admin/users/create"' not in text
