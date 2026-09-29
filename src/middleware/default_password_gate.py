"""
Default Password Write Gate (#510)

A fresh install bootstraps the shared admin/mvidarr credential. The nag banner
alone lets an install stay on that public default indefinitely, so until the
password is changed this middleware refuses state-changing API calls.

Deliberately narrow, to make a lockout hard:
- Only POST/PUT/PATCH/DELETE under /api/ are refused; pages, reads, playback
  and the change-password banner all keep working.
- Login/logout/credentials (/api/auth/), the installation wizard and health
  stay open so the password can always be changed.
- Fails open: only a stored hash that positively matches the shipped default
  triggers it (see SimpleAuthService.is_bootstrap_password_active).
- Escape hatch: ALLOW_DEFAULT_PASSWORD=true disables it entirely.
"""

import os
import threading
import time

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.default_password_gate")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EXEMPT_PREFIXES = ("/api/auth/", "/api/wizard", "/api/health")
CACHE_TTL_SECONDS = 5.0

_cache_lock = threading.Lock()
_cache = {"value": None, "at": 0.0}


def invalidate_cache() -> None:
    """Drop the cached check so a just-changed password takes effect at once."""
    with _cache_lock:
        _cache["value"] = None
        _cache["at"] = 0.0


def gate_disabled() -> bool:
    return os.environ.get("ALLOW_DEFAULT_PASSWORD", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _bootstrap_password_active() -> bool:
    """bcrypt-backed check, cached briefly so it only costs one compare per TTL."""
    now = time.monotonic()
    with _cache_lock:
        if _cache["value"] is not None and now - _cache["at"] < CACHE_TTL_SECONDS:
            return _cache["value"]

    from src.services.simple_auth_service import SimpleAuthService

    value = SimpleAuthService.is_bootstrap_password_active()
    with _cache_lock:
        _cache["value"] = value
        _cache["at"] = now
    return value


def _is_gated_request(method: str, path: str) -> bool:
    if method in SAFE_METHODS:
        return False
    if not path.startswith("/api/"):
        return False
    return not path.startswith(EXEMPT_PREFIXES)


class DefaultPasswordGateMiddleware:
    """Pure ASGI middleware (no BaseHTTPMiddleware body buffering/streaming quirks)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not _is_gated_request(scope["method"], scope["path"])
            or gate_disabled()
        ):
            await self.app(scope, receive, send)
            return

        if await run_in_threadpool(_bootstrap_password_active):
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "This instance is still using the default admin password. "
                        "Change it (Settings → account credentials) before making "
                        "changes."
                    ),
                    "code": "default_password_active",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
