"""#457: the FastAPI process froze completely (all routes, including
totally unrelated ones and the health check) after two overlapping
download requests for the same video. Root cause, found via code
audit: metube.py's `async def retry_download()` called the fully
synchronous `ytdlp_service.retry_download()`/`retry_video_download()`
directly, with no `await`/threadpool offload. Those methods open a DB
session and call `claim_video_for_redownload()`, which runs a row-
locking `UPDATE ... WHERE status='WANTED'` on its own raw connection.
If that has to wait on an InnoDB row lock (any two requests touching
the same video's row close together), the wait runs synchronously on
the single asyncio event loop thread -- freezing the *entire
application*, not just the one request, for up to
innodb_lock_wait_timeout (~50s default). Multiple overlapping requests
stack this into a multi-minute outage.

Fix: the route now awaits `asyncio.to_thread(...)`, moving the
blocking call onto a worker thread. A lock wait there still slows that
one request, but no longer blocks every other request in the
application.
"""

import asyncio
from unittest.mock import MagicMock, patch

from src.api.fastapi.metube import retry_download


def _run(coro):
    return asyncio.run(coro)


class TestRetryDownloadOffloadsToAThread:
    def test_video_kind_offloads_retry_video_download_to_a_thread(self):
        with patch("src.api.fastapi.metube.ytdlp_service") as mock_service, patch(
            "src.api.fastapi.metube.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = {"success": True}

            _run(
                retry_download(
                    "video_5",
                    current_user={"user_id": 1, "username": "mike"},
                    session=MagicMock(),
                )
            )

        mock_to_thread.assert_called_once_with(mock_service.retry_video_download, 5)
        mock_service.retry_video_download.assert_not_called()

    def test_download_kind_offloads_retry_download_to_a_thread(self):
        with patch("src.api.fastapi.metube.ytdlp_service") as mock_service, patch(
            "src.api.fastapi.metube.asyncio.to_thread"
        ) as mock_to_thread:
            mock_to_thread.return_value = {"success": True}

            _run(
                retry_download(
                    "42",
                    current_user={"user_id": 1, "username": "mike"},
                    session=MagicMock(),
                )
            )

        mock_to_thread.assert_called_once_with(mock_service.retry_download, 42)
        mock_service.retry_download.assert_not_called()
