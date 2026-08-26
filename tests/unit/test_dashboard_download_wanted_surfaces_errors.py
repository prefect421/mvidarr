"""Live-reported: clicking "Download All Wanted" on the dashboard did
nothing useful when at least one WANTED video existed but had no
downloadable URL. Verified live: the backend
(bulk_download_wanted_videos()) correctly identifies this and reports
it -- success_count: 0, failed_count: 1,
errors: ["Video 229 (Ghost - Lachryma): No URL available"] -- the
backend was never broken.

Root cause: frontend/templates/index.html's proceedDownloadWantedVideos()
nested its entire failure-detail block (categorizing errors, showing
"N videos could not be downloaded: ...") INSIDE
`if (data.success_count > 0) { ... }`. When every wanted video fails
(the exact case here: one WANTED video, zero successes), that whole
branch is skipped, so the user only ever sees the bland
"Queued 0 wanted videos for download" with no indication why or what
to do about it -- indistinguishable from the button silently doing
nothing, even though the backend response already contained the real
reason.

Fix: the failure-detail block now runs whenever failed_count > 0,
regardless of whether success_count is also > 0 (siblings, not nested).
"""

from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "frontend" / "templates" / "index.html"
)


def _function_source() -> str:
    text = TEMPLATE_PATH.read_text()
    start = text.index("function proceedDownloadWantedVideos()")
    # Next top-level `function ` declaration after this one marks the end.
    next_fn = text.index("\nfunction ", start + 10)
    return text[start:next_fn]


class TestDownloadWantedSurfacesFailuresEvenWithZeroSuccesses:
    def test_failed_count_check_is_not_nested_inside_success_count_check(self):
        source = _function_source()

        success_count_if = source.index("if (data.success_count > 0)")
        failed_count_if = source.index("if (data.failed_count > 0)")

        # Find the closing brace of the `if (data.success_count > 0) {`
        # block by brace-matching from its opening brace.
        open_brace = source.index("{", success_count_if)
        depth = 0
        close_brace = None
        for i, ch in enumerate(source[open_brace:], start=open_brace):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close_brace = i
                    break
        assert close_brace is not None, "could not find matching brace"

        assert failed_count_if > close_brace, (
            "the failed_count > 0 error-detail block must not be nested "
            "inside success_count > 0 -- otherwise a batch where every "
            "video fails (success_count == 0) never shows the user why"
        )

    def test_still_shows_a_message_when_there_are_zero_successes(self):
        source = _function_source()
        assert "data.message" in source
