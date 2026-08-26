"""Regression test for a live-reproduced self-deadlock in
queue_download_video() (and defensively, its sibling
queue_video_download()): both staged the new Download row on the
request's own FastAPI session (session.add(download), and in
queue_download_video()'s case an explicit session.flush()) *before*
calling claim_video_for_redownload().

downloads.video_id has a real, enforced InnoDB foreign key to videos.id
(downloads_ibfk_2). Flushing the staged Download row therefore takes an
InnoDB lock on the referenced video's row on the request's own session
connection -- before that row is committed. claim_video_for_redownload()
then opens a *second*, independent DB connection (by design, so it's
immune to whatever session state its caller holds) and tries to
UPDATE that exact same video row. That second connection queues behind
the first connection's own uncommitted FK lock -- from the very same
request -- and can only be freed by MariaDB's innodb_lock_wait_timeout
(~50s), which fires and fails with error 1205 every single time this
ordering is used to claim a video that isn't already mid-download.

Live-reproduced 2026-08-20: caught the exact signature
(1 row modified, 2 rows locked, connection idle mid-transaction) via
information_schema.innodb_trx while a /queue-download request for
video 106 was itself stuck waiting -- on a lock its own request held.
Repeated clicks stacked multiple such self-deadlocks and one capture
even hit the reverse proxy's 90s gateway timeout (504) before the DB's
own 50s timeout could even return.

Fix: claim the video first (on claim_video_for_redownload()'s own,
separate, immediately-committed connection) and only stage the Download
row afterwards -- the same order bulk_download_videos() (this file's
already-correct sibling, #377) already uses.
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


class TestQueueDownloadVideoClaimsBeforeStagingDownloadRow:
    """/{video_id}/queue-download -- the endpoint the video detail page's
    Download button actually calls, and the one confirmed live to
    self-deadlock on every genuinely-new download attempt."""

    FUNCTION_NAME = "queue_download_video"

    def test_claims_the_video_before_adding_the_download_row(self):
        source = _function_source(self.FUNCTION_NAME)
        claim_pos = source.index(
            "asyncio.to_thread(claim_video_for_redownload, video_id)"
        )
        add_pos = source.index("session.add(download)")
        assert claim_pos < add_pos, (
            "session.add(download) must not run before "
            "claim_video_for_redownload(): downloads.video_id has a real "
            "FK to videos.id, so flushing the staged row locks the video "
            "on this request's own session connection before "
            "claim_video_for_redownload()'s separate connection tries to "
            "UPDATE that same row -- a guaranteed self-deadlock."
        )


class TestQueueVideoDownloadClaimsBeforeStagingDownloadRow:
    """/{video_id}/download -- sibling endpoint with the same ordering
    anti-pattern. No explicit session.flush() between session.add() and
    the claim call, so it doesn't reproduce the self-deadlock as
    reliably as queue_download_video() -- but the same fix closes it
    defensively rather than leaving the fragile ordering in place."""

    FUNCTION_NAME = "queue_video_download"

    def test_claims_the_video_before_adding_the_download_row(self):
        source = _function_source(self.FUNCTION_NAME)
        claim_pos = source.index(
            "asyncio.to_thread(claim_video_for_redownload, video_id)"
        )
        add_pos = source.index("session.add(download)")
        assert claim_pos < add_pos, (
            "session.add(download) must not run before "
            "claim_video_for_redownload(): the same self-deadlock risk "
            "as queue_download_video() applies here too."
        )
