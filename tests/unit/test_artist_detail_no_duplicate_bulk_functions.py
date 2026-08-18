"""Regression test for a duplicate-function-definition bug in
artist_detail.html: bulkDownloadSelected() and bulkDeleteSelected()
were each defined twice in the same <script>. JavaScript function
declarations with the same name in the same scope silently shadow one
another -- whichever definition appears LAST in source order wins at
runtime. The second (later) definitions of both functions here were
dead stubs (explicit "// Implement bulk download logic here" /
"// Implement bulk delete logic here" comments, no fetch() call at
all), which silently shadowed the real, working implementations
earlier in the file. The user-visible symptom: clicking "Download
Selected" on the artist page's video tab showed an "info" toast
("Starting download for N selected videos...") but never actually
sent anything to the backend.

Root cause fix: the dead stub definitions were removed, leaving each
function defined exactly once -- the real implementation that calls
the actual API endpoint.
"""

import re
from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent
    / "frontend"
    / "templates"
    / "artist_detail.html"
)


def _count_function_definitions(source: str, function_name: str) -> int:
    pattern = re.compile(rf"^function {re.escape(function_name)}\s*\(", re.MULTILINE)
    return len(pattern.findall(source))


class TestNoDuplicateBulkActionFunctions:
    def test_bulk_download_selected_defined_exactly_once(self):
        source = TEMPLATE_PATH.read_text()
        assert _count_function_definitions(source, "bulkDownloadSelected") == 1

    def test_bulk_delete_selected_defined_exactly_once(self):
        source = TEMPLATE_PATH.read_text()
        assert _count_function_definitions(source, "bulkDeleteSelected") == 1

    def test_bulk_download_selected_actually_calls_the_api(self):
        source = TEMPLATE_PATH.read_text()
        match = re.search(
            r"function bulkDownloadSelected\s*\([^)]*\)\s*\{(.*?)\n\}",
            source,
            re.DOTALL,
        )
        assert match, "bulkDownloadSelected() not found"
        body = match.group(1)
        assert "/api/videos/bulk/download" in body
        assert "fetch(" in body

    def test_bulk_delete_selected_actually_calls_the_api(self):
        source = TEMPLATE_PATH.read_text()
        match = re.search(
            r"function bulkDeleteSelected\s*\([^)]*\)\s*\{(.*?)\n\}",
            source,
            re.DOTALL,
        )
        assert match, "bulkDeleteSelected() not found"
        body = match.group(1)
        assert "/api/videos/bulk/delete" in body
        assert "fetch(" in body
