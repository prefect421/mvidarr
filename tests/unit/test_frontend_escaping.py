"""#622: shared frontend escaping helpers, exercised in Node with real attack strings."""

import json
import pathlib
import shutil
import subprocess

import pytest

JS = pathlib.Path("frontend/static/js/html-escape.js").resolve()
pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def run(fn, value):
    script = f"""
    const h = require({json.dumps(str(JS))});
    process.stdout.write(JSON.stringify(h[{json.dumps(fn)}]({json.dumps(value)})));
    """
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.mark.parametrize(
    "attack",
    [
        '" onerror="alert(1)',
        "' onmouseover='alert(1)",
        "<img src=x onerror=alert(1)>",
        "</div><script>alert(1)</script>",
        '"><svg/onload=alert(1)>',
        "`${alert(1)}`",
    ],
)
def test_escape_html_leaves_no_raw_markup_or_quotes(attack):
    out = run("escapeHtml", attack)
    for ch in "<>\"'`":
        assert ch not in out, (attack, out)


def test_escape_html_keeps_valid_entities_so_stored_titles_still_display():
    assert run("escapeHtml", "Tom &amp; Jerry &quot;live&quot; Where&#39;s") == (
        "Tom &amp; Jerry &quot;live&quot; Where&#39;s"
    )
    assert run("escapeHtml", "AT&T <b>") == "AT&amp;T &lt;b&gt;"


def test_escape_html_is_idempotent_and_null_safe():
    once = run("escapeHtml", 'a & b "c" <d>')
    assert run("escapeHtml", once) == once
    assert run("escapeHtml", None) == ""
    assert run("escapeHtml", 0) == "0"


def test_strict_always_encodes_ampersand():
    assert run("escapeHtmlStrict", "&quot;") == "&amp;quot;"


def test_escape_js_arg_cannot_break_out_of_an_inline_handler():
    attack = "x');alert(1);//"
    out = run("escapeJsArg", attack)
    # Browser view: attribute value entity-decoded, then parsed as JS.
    decoded = (
        out.replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    assert json.loads(decoded) == attack  # round-trips as ONE string literal
    assert "'" not in out and '"' not in out.replace("&quot;", "")


def test_sanitize_message_allows_only_br():
    assert run("sanitizeMessageHtml", "Done:<br>ok") == "Done:<br>ok"
    out = run("sanitizeMessageHtml", 'Video "<img src=x onerror=1>" saved<br/>')
    assert "<img" not in out and "<br>" in out
