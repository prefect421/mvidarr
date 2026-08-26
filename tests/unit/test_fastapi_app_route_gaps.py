"""Regression test for a class of route-auth gap that #392's entire file-
by-file sweep this session structurally could not find: routes defined
directly in fastapi_app.py itself via @app.get/@app.post/@app.delete,
rather than in any router module under src/api/fastapi/. Found during a
systematic audit of #392's actual current status (tracing every route
FastAPI would really dispatch to, starting from fastapi_app.py's own
app.include_router()/@app.<method> calls, not just grepping router
files in isolation).

Two of these duplicate paths already defined in an authenticated router
module mounted earlier in the file (metube.py's /queue, /history,
/clear-stuck, /download/{id}/retry, /history/clear; imvdb.py's
/search-videos) -- FastAPI's first-registered-route-wins matching means
those specific fastapi_app.py duplicates are dead code, live-confirmed
via curl (401, not the stub/mock content). Left untouched here --
removing genuinely dead code is a separate cleanup task, not a security
fix.

Three routes were NOT shadowed and are live, unauthenticated, and touch
real data or state:
- GET /api/discover: runs real Artist/Video DB queries, unauthenticated
  (no colliding route exists anywhere else).
- POST /api/metube/process-queue: state-changing (submits all queued
  downloads to the job queue), unauthenticated -- metube.py only has a
  same-purpose /process-pending, a different path, so no shadowing.
- DELETE /api/metube/download/{download_id}: destructive (deletes a
  queued download), unauthenticated -- metube.py has no plain DELETE
  /download/{id} route (only /download/{id}/stop, POST), so no
  shadowing.

fastapi_app.py can't be imported directly in this test venv (importing
it pulls in all 65+ mounted routers transitively, one of which imports
netifaces -- a C extension with no build toolchain here, the same
constraint hit earlier for mobile_access.py -- and likely others further
down the same import chain). Static source-assertion test instead;
behavioral correctness verified live against the deployed mvidarr-dev
container via curl (documented in the fix's commit message).
"""

import ast
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parents[2] / "fastapi_app.py"

NEWLY_GATED_ROUTES = {
    "discover_search",
    "process_queued_downloads",
    "delete_download",
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


class TestFastapiAppDirectlyDefinedRoutesRequireAuth:
    def test_every_newly_gated_route_requires_authentication(self):
        for function_name in NEWLY_GATED_ROUTES:
            source = _function_source(function_name)
            assert (
                "Depends(require_authentication)" in source
            ), f"{function_name} should use Depends(require_authentication), got:\n{source}"

    def test_module_imports_require_authentication(self):
        text = SOURCE_PATH.read_text()
        assert (
            "from src.api.fastapi.auth_dependencies import" in text
            and "require_authentication" in text
        )
