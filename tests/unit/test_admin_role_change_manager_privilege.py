"""Fix for #324: MANAGER role gets inconsistent admin-equivalent
treatment across auth checks.

Three places disagreed on whether MANAGER counts as admin:
- auth_dependencies.require_admin -- ADMIN-only.
- admin.py's UserInfo.can_access_admin() -- ADMIN + MANAGER.
- The OAuth callback's can_admin derivation vs. the password-login
  endpoints' derivation in auth.py.

The auth.py piece turns out to already be resolved: every can_admin
value in that file now flows through the shared role_permissions()
helper, whose own docstring documents the ADMIN-only decision explicitly
("can_admin is deliberately ADMIN-only ... because the branch's actual
admin gate (auth_dependencies.require_admin) is ADMIN-only") -- so OAuth
and password-login already agree.

The remaining, concrete piece: PUT /api/admin/users/{user_id}/role was
gated by require_admin_access (-> can_access_admin(), ADMIN+MANAGER),
letting a MANAGER session call it to set its own role to ADMIN --
self-promotion past the ADMIN-only gate enforced everywhere else. Per
UserRole's own docstring ("Can manage content and users (except
admins)"), role changes are an admin-level action, not general user
management -- MANAGER's "manage... users" mandate doesn't cover granting
itself admin.

Fix: PUT /users/{user_id}/role now uses a new, stricter
require_admin_only_access dependency (ADMIN-only) instead of
require_admin_access. Every other admin.py route (dashboard, user
listing/creation, activate/deactivate, sessions, audit logs, system
status/health/restart) is deliberately left on require_admin_access --
#324 only names role-change as the concrete forcing case, and widening
this fix to re-tier all 17 routes would be a separate, larger design
decision (which of them MANAGER should retain per "manage content and
users (except admins)") that #324 doesn't ask for.
"""

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.fastapi.admin import UserInfo, require_admin_only_access

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "admin.py"
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


class TestUpdateUserRoleUsesTheStricterDependency:
    def test_update_user_role_no_longer_uses_require_admin_access(self):
        source = _function_source("update_user_role")
        assert "Depends(require_admin_access)" not in source

    def test_update_user_role_uses_require_admin_only_access(self):
        source = _function_source("update_user_role")
        assert "Depends(require_admin_only_access)" in source

    def test_every_other_admin_route_still_uses_require_admin_access(self):
        # Regression guard: this fix is deliberately scoped to
        # role-change only. Every other admin.py route should be
        # untouched.
        other_routes = [
            "get_dashboard",
            "get_system_status",
            "restart_application",
            "get_recent_logs",
            "list_all_users",
            "create_new_user",
            "get_user_details",
            "deactivate_user_account",
            "activate_user_account",
            "unlock_user_account",
            "get_user_sessions",
            "revoke_user_session",
            "revoke_all_user_sessions",
            "get_audit_logs",
            "get_detailed_health",
        ]
        for function_name in other_routes:
            source = _function_source(function_name)
            assert (
                "Depends(require_admin_access)" in source
            ), f"{function_name} should still use Depends(require_admin_access)"


class TestRequireAdminOnlyAccess:
    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def test_admin_passes(self):
        user = UserInfo(id=1, username="root", role="ADMIN", is_active=True)
        result = self._run(require_admin_only_access(current_user=user))
        assert result == user

    def test_manager_is_rejected(self):
        # The exact self-promotion vector: a MANAGER previously passed
        # can_access_admin() and could reach update_user_role.
        user = UserInfo(id=2, username="mgr", role="MANAGER", is_active=True)
        with pytest.raises(HTTPException) as exc_info:
            self._run(require_admin_only_access(current_user=user))
        assert exc_info.value.status_code == 403

    def test_regular_user_is_rejected(self):
        user = UserInfo(id=3, username="user", role="USER", is_active=True)
        with pytest.raises(HTTPException) as exc_info:
            self._run(require_admin_only_access(current_user=user))
        assert exc_info.value.status_code == 403
