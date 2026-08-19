"""Static source-assertion tests for videos_downloads.py's
resolve_video_url() wrapper fix (#380.1). The wrapper previously
imported a function that doesn't exist (src.api.fastapi.videos has no
resolve_video_url), so every call raised ImportError. This test proves
the fix: import the real, working implementation from
video_batch_service, and run it off the event loop since it's a
blocking subprocess call.

The video_batch_service import was originally function-local; a later
fix wave hoisted it to module level for consistency with this same
file's other module-level imports (claim_video_for_download), so the
module-level-import tests below check the whole file's source rather
than just the function's.
"""

import ast
from pathlib import Path

SOURCE_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "api"
    / "fastapi"
    / "videos_downloads.py"
)


def _module_source() -> str:
    return SOURCE_PATH.read_text()


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


class TestResolveVideoUrlWrapperFix:
    def test_no_longer_imports_from_nonexistent_videos_module(self):
        source = _module_source()
        assert "from src.api.fastapi.videos import" not in source

    def test_imports_the_real_implementation_from_video_batch_service(self):
        source = _module_source()
        assert "from src.services.video_batch_service import" in source
        assert "resolve_video_url as _resolve_video_url_sync" in source
        # ...and the wrapper function actually calls the hoisted import.
        function_source = _function_source("resolve_video_url")
        assert "_resolve_video_url_sync" in function_source

    def test_runs_the_blocking_call_off_the_event_loop(self):
        source = _function_source("resolve_video_url")
        assert "asyncio.to_thread(" in source

    def test_accepts_and_forwards_a_timeout_parameter(self):
        source = _function_source("resolve_video_url")
        assert "timeout: int = 30" in source
        assert "timeout" in source.split("asyncio.to_thread(")[1][:200]
