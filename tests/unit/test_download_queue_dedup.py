"""Regression test for a live-reported bug: a manually-queued download
showed up TWICE in the Download Queue dashboard widget while it was
downloading (both entries reading "Downloading (0%)"), even though the
`downloads` table only ever had one row for it.

Root cause: GET /api/metube/queue (get_download_queue() in metube.py)
merges two sources -- unified_download_service.get_download_queue()
(one entry per Video.status == DOWNLOADING, id "video_{video.id}",
carrying a "video_id" field but no "db_download_id") and a direct scan
of recent Download rows in ["queued", "downloading"] status (id
"db_{download.id}", carrying "db_download_id"). The merge's dedup check
only ever looked at "db_download_id" -- a key the first source never
sets -- so it was permanently a no-op: every download normally
represented by *both* sources (the common case, since claiming a video
sets it DOWNLOADING and always creates a matching Download row) was
appended twice.

This went unnoticed before #401 because queue_download_video() was
self-deadlocking on every genuinely-new download (~50s per attempt),
so a download rarely got far enough, fast enough, for both sources to
report it as in-progress at the same moment a user looked.

Fix: dedup by video_id in addition to db_download_id, since the first
source always sets video_id even though it never sets db_download_id.
"""

from src.api.fastapi.metube import _dedupe_recent_db_downloads


class TestDedupeRecentDbDownloads:
    def test_skips_a_db_row_whose_video_id_is_already_queued(self):
        """The exact live-reported shape: a video-status entry (no
        db_download_id) and a recent Download row for the same video."""
        queue_items = [
            {
                "id": "video_149",
                "title": "My Spirit Animal Ate Your Spirit Animal",
                "artist": "Dead Pioneers",
                "status": "downloading",
                "video_id": 149,
            }
        ]
        recent_downloads = [
            {
                "id": "db_95",
                "title": "My Spirit Animal Ate Your Spirit Animal",
                "artist": "Dead Pioneers",
                "status": "downloading",
                "db_download_id": 95,
                "video_id": 149,
            }
        ]

        merged = _dedupe_recent_db_downloads(queue_items, recent_downloads)

        assert len(merged) == 1
        assert merged[0]["id"] == "video_149"

    def test_skips_a_db_row_whose_download_id_is_already_queued(self):
        """Belt-and-braces: still dedupes the original db_download_id
        match too, for whichever source (if any) ever sets it."""
        queue_items = [{"id": "db_95", "db_download_id": 95, "video_id": 149}]
        recent_downloads = [{"id": "db_95", "db_download_id": 95, "video_id": 149}]

        merged = _dedupe_recent_db_downloads(queue_items, recent_downloads)

        assert len(merged) == 1

    def test_keeps_a_genuinely_different_download(self):
        """Two unrelated downloads (different videos) must both survive
        the merge -- the fix must not over-dedupe."""
        queue_items = [{"id": "video_149", "video_id": 149}]
        recent_downloads = [{"id": "db_96", "db_download_id": 96, "video_id": 200}]

        merged = _dedupe_recent_db_downloads(queue_items, recent_downloads)

        assert len(merged) == 2
        assert {item["id"] for item in merged} == {"video_149", "db_96"}

    def test_recent_download_with_no_video_id_is_not_dropped(self):
        """A Download row with no video_id (nullable in the schema)
        must never accidentally match every video-less queue_item on a
        shared `None` key."""
        queue_items = [{"id": "video_149", "video_id": 149}]
        recent_downloads = [{"id": "db_97", "db_download_id": 97, "video_id": None}]

        merged = _dedupe_recent_db_downloads(queue_items, recent_downloads)

        assert len(merged) == 2
