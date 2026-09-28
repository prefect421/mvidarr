"""Runs tests/unit/js/universal_search_race.test.js (#545) under node so the
frontend race regression test is part of the normal pytest run."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).parent / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_universal_search_always_searches_latest_query():
    result = subprocess.run(
        ["node", "--test", str(JS_DIR)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
