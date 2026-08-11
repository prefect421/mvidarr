"""Tests for POST /api/auth/credentials — found broken during manual dev
testing ahead of v1.0.0 (2026-08-11):

1. The frontend's "Update Credentials" button called POST /auth/credentials
   (the legacy_router prefix), but only GET is registered there — the real
   POST-capable route lives under /api/auth/credentials. Fixed in
   frontend/static/main.js; not covered here (that's a frontend bug, this
   file covers the backend route itself).
2. The route only required `require_authentication` — any authenticated
   session (USER, MANAGER, READONLY) could change the instance-wide
   SimpleAuth login credential, not just admins. Fixed by switching to
   `require_admin`; this file pins that behavior.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.fastapi.auth import router
from src.api.fastapi.auth_dependencies import require_admin


def _make_client(current_user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: current_user
    return TestClient(app)


class TestUpdateCredentialsRoleGating:
    def test_admin_can_update_credentials(self):
        client = _make_client({"role": "ADMIN", "user_id": 1})
        with patch(
            "src.services.simple_auth_service.SimpleAuthService.set_credentials",
            return_value=(True, "Credentials updated"),
        ):
            response = client.post(
                "/api/auth/credentials",
                json={"username": "admin", "password": "N3wPassw0rd!"},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_non_admin_role_is_rejected_before_reaching_the_route(self):
        # require_admin itself raises 403 for a non-ADMIN role — this test
        # exercises the real dependency (not overridden) to confirm the
        # route is actually wired to it, not merely require_authentication.
        app = FastAPI()
        app.include_router(router)

        from src.api.fastapi.auth_dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "role": "USER",
            "user_id": 2,
            "authenticated": True,
        }
        client = TestClient(app)

        response = client.post(
            "/api/auth/credentials",
            json={"username": "admin", "password": "N3wPassw0rd!"},
        )
        assert response.status_code == 403

    def test_missing_fields_still_validated_after_role_check(self):
        client = _make_client({"role": "ADMIN", "user_id": 1})
        response = client.post(
            "/api/auth/credentials", json={"username": "", "password": ""}
        )
        assert response.status_code in (400, 422)
