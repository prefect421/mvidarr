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


class TestPasswordLengthMismatchBetweenFrontendAndBackend:
    """Regression for a real bug reported in dev testing: the frontend's
    updateCredentials() accepted any password >= 6 characters, but
    SimpleAuthService.set_credentials() (the actual backend enforcement)
    requires >= 8. A 6-7 char password -- including "mvidarr", the
    bootstrap default -- passed client-side validation and reached this
    route, only to be rejected here with a 400 whose real message
    ("Password must be at least 8 characters long") main.js's apiRequest()
    then discarded in favor of a generic "HTTP error! status: 400"
    (apiRequest checked data.error; FastAPI's HTTPException returns
    data.detail). Both the frontend length check and the error-message
    extraction were fixed in frontend/static/main.js; this test exercises
    the backend half of the contract those fixes now actually match,
    using the real (unmocked) set_credentials -- the 7-char password is
    rejected before any DB access happens.
    """

    def test_seven_char_password_is_rejected_with_the_real_length_message(self):
        client = _make_client({"role": "ADMIN", "user_id": 1})
        response = client.post(
            "/api/auth/credentials",
            json={"username": "admin", "password": "mvidarr"},
        )
        assert response.status_code == 400
        assert "8 characters" in response.json()["detail"]

    def test_eight_char_password_reaches_set_credentials_unmodified(self):
        # The route itself does no length check of its own -- that lives
        # entirely in set_credentials. Confirms the route doesn't add a
        # second, possibly-different length gate in front of it.
        client = _make_client({"role": "ADMIN", "user_id": 1})
        with patch(
            "src.services.simple_auth_service.SimpleAuthService.set_credentials",
            return_value=(True, "Credentials updated"),
        ) as mock_set:
            response = client.post(
                "/api/auth/credentials",
                json={"username": "admin", "password": "8charpw!"},
            )
        assert response.status_code == 200
        mock_set.assert_called_once_with("admin", "8charpw!")
