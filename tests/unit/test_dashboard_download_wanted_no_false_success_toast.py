"""Follow-up to PR #476 (test_dashboard_download_wanted_surfaces_errors.py),
found by code review of that fix.

That PR made the failure-detail block run regardless of success_count, so
the real failure reason ("No URL available") does surface -- but as a
second, delayed (2s) error toast. Before it appears, the code still
unconditionally calls showSuccess() when success_count is 0: it falls into
the `else { showSuccess(data.message || ...) }` branch, showing a green
"success"-styled toast for a batch that was 100% failures. The user's
first signal for an all-failed batch was a false "success" notification --
the same misleading-UX class the earlier fix was written to close, just not
fully closed.

Fix: only show the "no wanted videos" success toast when there were no
failures either (success_count === 0 AND failed_count === 0). When
success_count === 0 but failed_count > 0, skip the success toast entirely --
the error toast (with the real reason) is the only signal the user gets.
"""

from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / "frontend" / "templates" / "index.html"
)


def _function_source() -> str:
    text = TEMPLATE_PATH.read_text()
    start = text.index("function proceedDownloadWantedVideos()")
    next_fn = text.index("\nfunction ", start + 10)
    return text[start:next_fn]


class TestNoFalseSuccessToastWhenBatchEntirelyFails:
    def test_the_zero_successes_message_branch_is_guarded_by_failed_count(self):
        source = _function_source()

        # The "no wanted videos" success toast must not fire unconditionally
        # whenever success_count is 0 -- it must also check that there were
        # no failures, otherwise an all-failed batch shows a false "success"
        # toast before the real error appears 2s later.
        message_call = source.index("showSuccess(data.message")

        # Walk backwards from the showSuccess(data.message call to its
        # nearest guarding `if`/`else if` condition and confirm it checks
        # failed_count, not just success_count.
        preceding = source[:message_call]
        last_else_if = preceding.rfind("else if")
        last_bare_else = preceding.rfind("else {")

        assert last_else_if != -1 and last_else_if > last_bare_else, (
            "showSuccess(data.message...) must be reached through an "
            "`else if` that also checks data.failed_count, not a bare "
            "`else` that fires whenever success_count is 0 regardless of "
            "failures"
        )

        guard = source[last_else_if : message_call + 1]
        assert "failed_count" in guard, (
            "the guard reaching showSuccess(data.message...) must "
            "reference data.failed_count, so an all-failed batch "
            "(success_count == 0, failed_count > 0) does not get a false "
            "success toast"
        )
