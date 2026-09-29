"""Runs tests/unit/js/universal_search_race.test.js (#545) under node so the
frontend race regression test is part of the normal pytest run."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TEST = Path(__file__).parent / "js" / "universal_search_race.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_universal_search_always_searches_latest_query():
    result = subprocess.run(
        ["node", "--test", str(JS_TEST)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


ENTER_JS_TEST = Path(__file__).parent / "js" / "universal_search_enter.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_universal_search_box_searches_only_on_enter():
    result = subprocess.run(
        ["node", "--test", str(ENTER_JS_TEST)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
