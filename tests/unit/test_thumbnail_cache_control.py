"""#614: thumbnail URLs are stable (/api/videos/<id>/thumbnail), so a cacheable
200 placeholder gets stuck in the browser after a real thumbnail exists. Every
FileResponse in the thumbnail routers must force revalidation."""

import ast
import pathlib

import pytest

FILES = [
    "src/api/fastapi/videos_thumbnails.py",
    "src/api/fastapi/artists_thumbnails.py",
]


@pytest.mark.parametrize("path", FILES)
def test_every_file_response_revalidates(path):
    src = pathlib.Path(path).read_text()
    calls = [
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", "")) == "FileResponse"
    ]
    assert calls, "expected FileResponse calls"
    missing = [
        n.lineno
        for n in calls
        if "no-cache" not in (ast.get_source_segment(src, n) or "")
        and "NO_CACHE" not in (ast.get_source_segment(src, n) or "")
    ]
    assert missing == []
