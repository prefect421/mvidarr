"""Tests for parsing queue item IDs in the stop/retry endpoints.

The download queue mixes two ID spaces: "db_123"/bare "123" identify a
Download.id row, while "video_123" identifies a Video.id (queue entries
built from Video.status == DOWNLOADING with no live Download row to match).
_parse_queue_item_id must route each form to the right table.
"""

import pytest
from fastapi import HTTPException

from src.api.fastapi.metube import _parse_queue_item_id


class TestParseQueueItemId:
    def test_bare_integer_is_a_download_id(self):
        assert _parse_queue_item_id("1982") == ("download", 1982)

    def test_db_prefixed_is_a_download_id(self):
        assert _parse_queue_item_id("db_1982") == ("download", 1982)

    def test_video_prefixed_is_a_video_id(self):
        assert _parse_queue_item_id("video_1982") == ("video", 1982)

    @pytest.mark.parametrize("bad_id", ["not-a-number", "db_abc", "video_", ""])
    def test_invalid_formats_raise_400(self, bad_id):
        with pytest.raises(HTTPException) as exc_info:
            _parse_queue_item_id(bad_id)
        assert exc_info.value.status_code == 400
