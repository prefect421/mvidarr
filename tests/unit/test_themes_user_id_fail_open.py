"""Regression test for a HIGH-severity fail-open default flagged by
background security review right after #392 Phase 2's IDOR fix (PR #431):
every route in themes.py extracted the caller's id via
`current_user.get("user_id", 6)` -- if "user_id" were ever absent from
the session dict (a future refactor changing its shape, a bug elsewhere),
this would silently attribute the action to a fixed, unrelated user id
(6) instead of failing closed. Since delete_theme and export_all_themes
now gate real deletion/export access on this exact value (#392 IDOR fix,
PR #431), a fail-open default here would have undermined that fix
outright: anyone hitting the fallback would be silently treated as user
6, able to delete or export user 6's themes.

Every route in this file (get_themes, apply_theme, create_theme,
get_theme, delete_theme, export_all_themes) used the same pattern --
fixed uniformly via a shared _require_user_id() helper that raises 401
instead of defaulting.
"""

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.fastapi.themes import _require_user_id

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "themes.py"
)

ROUTES_USING_USER_ID = {
    "get_themes",
    "apply_theme",
    "create_theme",
    "get_theme",
    "delete_theme",
    "export_all_themes",
}


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


class TestNoRouteHasAFailOpenDefault:
    def test_no_route_defaults_user_id_to_a_fixed_fallback(self):
        # Checked per-route-function, not against the whole file's text --
        # _require_user_id's own docstring legitimately quotes the old
        # pattern to explain what it replaced.
        for function_name in ROUTES_USING_USER_ID:
            source = _function_source(function_name)
            assert 'current_user.get("user_id", 6)' not in source

    def test_every_route_that_needs_user_id_uses_the_strict_helper(self):
        for function_name in ROUTES_USING_USER_ID:
            source = _function_source(function_name)
            assert (
                "_require_user_id(current_user)" in source
            ), f"{function_name} should call _require_user_id(current_user), got:\n{source}"


class TestRequireUserIdHelper:
    def test_returns_the_user_id_when_present(self):
        assert _require_user_id({"user_id": 42, "authenticated": True}) == 42

    def test_raises_401_when_user_id_is_missing(self):
        with pytest.raises(HTTPException) as exc_info:
            _require_user_id({"authenticated": True})
        assert exc_info.value.status_code == 401

    def test_raises_401_when_user_id_is_none(self):
        with pytest.raises(HTTPException) as exc_info:
            _require_user_id({"user_id": None, "authenticated": True})
        assert exc_info.value.status_code == 401
