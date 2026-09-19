"""Tests for the default-password write gate (#510)."""

import bcrypt
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.middleware import default_password_gate as gate
from src.services import simple_auth_service as sas


def _ok(request):
    return JSONResponse({"ok": True})


@pytest.fixture
def client():
    routes = [
        Route(
            p, _ok, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
        )
        for p in (
            "/api/videos/1",
            "/api/auth/login",
            "/api/auth/credentials",
            "/api/wizard/complete",
            "/api/health",
            "/videos",
        )
    ]
    app = Starlette(routes=routes)
    app.add_middleware(gate.DefaultPasswordGateMiddleware)
    gate.invalidate_cache()
    return TestClient(app)


@pytest.fixture
def default_active(monkeypatch):
    monkeypatch.setattr(gate, "_bootstrap_password_active", lambda: True)
    monkeypatch.delenv("ALLOW_DEFAULT_PASSWORD", raising=False)


class TestGating:
    def test_write_blocked_while_default_password_active(self, client, default_active):
        for method in ("post", "put", "patch", "delete"):
            r = getattr(client, method)("/api/videos/1")
            assert r.status_code == 403, method
            assert r.json()["code"] == "default_password_active"

    def test_reads_and_pages_stay_open(self, client, default_active):
        assert client.get("/api/videos/1").status_code == 200
        assert client.get("/videos").status_code == 200
        assert client.head("/api/videos/1").status_code == 200
        assert client.options("/api/videos/1").status_code == 200

    def test_password_change_and_login_paths_stay_open(self, client, default_active):
        for path in (
            "/api/auth/login",
            "/api/auth/credentials",
            "/api/wizard/complete",
        ):
            assert client.post(path).status_code == 200, path

    def test_non_api_writes_not_gated(self, client, default_active):
        assert client.post("/videos").status_code == 200

    def test_open_once_password_changed(self, client, monkeypatch):
        monkeypatch.setattr(gate, "_bootstrap_password_active", lambda: False)
        assert client.post("/api/videos/1").status_code == 200

    def test_env_kill_switch(self, client, default_active, monkeypatch):
        monkeypatch.setenv("ALLOW_DEFAULT_PASSWORD", "true")
        assert client.post("/api/videos/1").status_code == 200


class TestCache:
    def test_result_cached_until_invalidated(self, monkeypatch):
        calls = []

        class Fake:
            @staticmethod
            def is_bootstrap_password_active():
                calls.append(1)
                return True

        monkeypatch.setattr(sas, "SimpleAuthService", Fake)
        gate.invalidate_cache()
        assert gate._bootstrap_password_active() is True
        assert gate._bootstrap_password_active() is True
        assert len(calls) == 1
        gate.invalidate_cache()
        gate._bootstrap_password_active()
        assert len(calls) == 2


class TestStrictCheck:
    def _with_hash(self, monkeypatch, value):
        monkeypatch.setattr(sas.SettingsService, "get", lambda key: value)

    def test_true_when_stored_hash_is_the_default(self, monkeypatch):
        self._with_hash(
            monkeypatch, bcrypt.hashpw(b"mvidarr", bcrypt.gensalt()).decode()
        )
        assert sas.SimpleAuthService.is_bootstrap_password_active() is True

    def test_false_after_password_changed(self, monkeypatch):
        self._with_hash(
            monkeypatch, bcrypt.hashpw(b"Zq7!vLm2$Xk9#Rt4", bcrypt.gensalt()).decode()
        )
        assert sas.SimpleAuthService.is_bootstrap_password_active() is False

    def test_fails_open_when_no_hash_stored(self, monkeypatch):
        # OAuth-only installs have no simple-auth password; the banner check
        # treats that as "default", the gate must not lock them out.
        self._with_hash(monkeypatch, None)
        assert sas.SimpleAuthService.is_bootstrap_password_active() is False
        assert sas.SimpleAuthService.is_default_password() is True

    def test_fails_open_on_settings_error(self, monkeypatch):
        def boom(key):
            raise RuntimeError("db down")

        monkeypatch.setattr(sas.SettingsService, "get", boom)
        assert sas.SimpleAuthService.is_bootstrap_password_active() is False
