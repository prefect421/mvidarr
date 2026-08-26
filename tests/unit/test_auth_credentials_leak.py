"""Test for a real gap in auth.py's otherwise-correctly-scoped auth (#392
Phase 2). Most of this file's routes are intentionally public by design
(login, logout, OAuth flows, health check -- you can't require a session to
log in) and POST /credentials is already correctly require_admin-gated
(fixed ahead of v1.0.0, per its own docstring: any authenticated
USER/MANAGER/READONLY session could previously change the instance-wide
login credentials).

GET /credentials (and its legacy twin, GET /auth/credentials) were missed:
they leak the stored simple-auth username to any unauthenticated caller.
frontend/static/main.js's loadCurrentCredentials() confirms this is only
ever called from the admin-only credentials-change form on settings.html
(pre-filling the username field before an admin edits it) -- never from
the login page -- so gating it with require_admin, matching its POST
sibling, breaks nothing.
"""

import ast
from pathlib import Path

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "auth.py"
)


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestGetCredentialsNoLongerLeaksUsername:
    def test_primary_route_requires_admin(self):
        source = _function_source("get_credentials")
        assert "Depends(require_admin)" in source

    def test_legacy_route_requires_admin(self):
        source = _function_source("get_credentials_legacy")
        assert "Depends(require_admin)" in source
