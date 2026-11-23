"""#622 ratchet: externally-sourced text must not reach innerHTML/attributes raw.

Titles, artist names and descriptions come from YouTube, yt-dlp, MusicBrainz and
the filesystem. This scans the frontend for the patterns that caused #622 so a
new one fails CI instead of shipping. Heuristic by design (line based): a line
that is genuinely safe can be marked with ``escape-ok`` in a comment on it.
"""

import glob
import re

FILES = [
    f
    for f in glob.glob("frontend/templates/**/*.html", recursive=True)
    + glob.glob("frontend/static/**/*.js", recursive=True)
    if ".min." not in f and not f.endswith("html-escape.js")
]
FIELD = re.compile(
    r"\b(title|description|channel_title|artist_name|album|genres?|folder_path|"
    r"local_path|name|display_name|username|label|path)\b"
)
SAFE = re.compile(
    r"escape\w*\(|sanitizeMessageHtml\(|highlightSearchTerms\(|encodeURIComponent|"
    r"\.length|\.toFixed|Number\(|parseInt|JSON\.stringify|toLocale|\bformat\w*\("
)


def _interpolations(line):
    i = 0
    while True:
        i = line.find("${", i)
        if i < 0:
            return
        depth, j = 1, i + 2
        while j < len(line) and depth:
            depth += {"{": 1, "}": -1}.get(line[j], 0)
            j += 1
        if depth:
            return
        yield line[i + 2 : j - 1]
        i = j


def test_no_weak_local_escape_html_definitions():
    weak = []
    for f in FILES:
        for n, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
            if re.search(
                r"function escapeHtml\s*\(|const escapeHtml\s*=|escapeHtmlAttr", line
            ):
                weak.append(f"{f}:{n}")
    assert (
        weak == []
    ), "define nothing locally: use js/html-escape.js (quote-safe): " + str(weak)


def test_no_unescaped_external_text_in_html_lines():
    bad = []
    for f in FILES:
        for n, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
            if "<" not in line or "escape-ok" in line:
                continue
            for expr in _interpolations(line):
                if "`" in expr or "=>" in expr:
                    continue  # nested template: checked where it is defined
                bare = re.sub(r"'[^']*'|\"[^\"]*\"", "''", expr)  # ignore literals
                if FIELD.search(bare) and not SAFE.search(expr):
                    bad.append(f"{f}:{n}: ${{{expr.strip()[:60]}}}")
    assert bad == [], "unescaped interpolation in HTML:\n" + "\n".join(bad)


def test_inline_handlers_never_embed_a_quoted_interpolation():
    # onclick="fn('${x}')": the browser decodes the attribute BEFORE the JS runs,
    # so HTML-escaping cannot protect a quoted JS string. Use escapeJsArg(x).
    bad = []
    pat = re.compile(r"""\bon[a-z]+="[^"]*['"`]\$\{(?!escapeJsArg)([^}]*)\}['"`]""")
    for f in FILES:
        for n, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
            if "escape-ok" in line:
                continue
            m = pat.search(line)
            if m and not re.search(r"\b(\w+\.)?(id|job_id|index|page)\b", m.group(1)):
                bad.append(f"{f}:{n}: {m.group(0)[:90]}")
    assert bad == [], "quoted interpolation in inline handler:\n" + "\n".join(bad)
