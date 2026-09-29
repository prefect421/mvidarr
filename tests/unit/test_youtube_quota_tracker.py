"""Tests for YouTubeQuotaTracker enforcement logic"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

from src.utils.youtube_quota_tracker import YouTubeQuotaTracker


@pytest.fixture
def tracker(tmp_path):
    """Quota tracker backed by a temp file"""
    storage = str(tmp_path / "quota.json")
    return YouTubeQuotaTracker(storage_path=storage)


def test_has_budget_returns_true_when_empty(tracker):
    assert tracker.has_budget(100) is True


def test_has_budget_returns_false_when_exhausted(tracker):
    # Burn all budget via consume()
    for _ in range(100):  # 100 × 100 = 10,000 units
        tracker.consume("search", count=1)
    assert tracker.has_budget(100) is False


def test_consume_returns_false_when_over_budget(tracker):
    for _ in range(100):
        tracker.consume("search", count=1)
    result = tracker.consume("search", count=1)
    assert result is False


def test_consume_returns_true_when_budget_available(tracker):
    result = tracker.consume("search", count=1)
    assert result is True


def test_has_budget_partial_remaining(tracker):
    # Use 9,900 units — 100 remaining
    for _ in range(99):
        tracker.consume("search", count=1)
    assert tracker.has_budget(100) is True
    assert tracker.has_budget(101) is False


def test_quota_persisted_to_disk(tmp_path):
    storage = str(tmp_path / "quota.json")
    t1 = YouTubeQuotaTracker(storage_path=storage)
    t1.consume("search", count=1)  # 100 units

    # Second instance reads same file
    t2 = YouTubeQuotaTracker(storage_path=storage)
    assert t2.get_stats()["total_used"] == 100


def test_quota_resets_on_new_day(tmp_path):
    storage = str(tmp_path / "quota.json")
    t = YouTubeQuotaTracker(storage_path=storage)
    t.consume("search", count=1)

    # Simulate yesterday's data
    with open(storage) as f:
        data = json.load(f)
    data["date"] = "2000-01-01"
    with open(storage, "w") as f:
        json.dump(data, f)

    t2 = YouTubeQuotaTracker(storage_path=storage)
    assert t2.get_stats()["total_used"] == 0


# --- Google-reported exhaustion (the local count can disagree with Google's) ---


def test_mark_exhausted_blocks_budget_even_when_local_count_is_low(tracker):
    tracker.consume("search", count=1)
    tracker.mark_exhausted()
    assert tracker.is_exhausted() is True
    assert tracker.has_budget(1) is False
    assert tracker.consume("search", count=1) is False


def test_exhausted_flag_is_shared_through_the_storage_file(tmp_path):
    path = str(tmp_path / "quota.json")
    YouTubeQuotaTracker(storage_path=path).mark_exhausted()
    # e.g. the Celery worker sees what the API process learned from Google
    assert YouTubeQuotaTracker(storage_path=path).has_budget(1) is False


def test_exhausted_flag_clears_when_the_quota_day_rolls_over(tracker):
    tracker.mark_exhausted()
    with patch.object(
        YouTubeQuotaTracker, "_quota_day", return_value="2999-01-01", create=True
    ):
        assert tracker.is_exhausted() is False
        assert tracker.has_budget(100) is True


def test_stats_report_exhausted(tracker):
    assert tracker.get_stats()["exhausted"] is False
    tracker.mark_exhausted()
    assert tracker.get_stats()["exhausted"] is True


def test_quota_day_follows_pacific_time_not_local_time():
    # 2026-09-29 08:30 UTC is 2026-09-29 01:30 PDT; 05:00 UTC is still the 28th in PDT
    from datetime import timezone

    with patch("src.utils.youtube_quota_tracker.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: datetime(
            2026, 9, 29, 5, 0, tzinfo=timezone.utc
        ).astimezone(tz)
        assert YouTubeQuotaTracker._quota_day() == "2026-09-28"


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (429, "Quota exceeded for quota metric 'Search Queries' per day", True),
        (403, '{"error":{"errors":[{"reason":"quotaExceeded"}]}}', True),
        (403, "dailyLimitExceeded", True),
        (429, "Rate limit exceeded, per minute", False),
        (403, "forbidden: API key restricted", False),
        (500, "quotaExceeded", False),
        (200, "", False),
    ],
)
def test_is_daily_quota_error(status, body, expected):
    from src.utils.youtube_quota_tracker import is_daily_quota_error

    assert is_daily_quota_error(status, body) is expected


def test_note_http_error_marks_exhausted_on_daily_quota_response(tracker):
    from types import SimpleNamespace

    exc = Exception("429")
    exc.response = SimpleNamespace(
        status_code=429, text="Quota exceeded ... Search Queries per day"
    )
    assert tracker.note_http_error(exc) is True
    assert tracker.is_exhausted() is True


def test_note_http_error_ignores_other_errors(tracker):
    from types import SimpleNamespace

    assert tracker.note_http_error(Exception("no response attr")) is False
    exc = Exception("500")
    exc.response = SimpleNamespace(status_code=500, text="oops")
    assert tracker.note_http_error(exc) is False
    assert tracker.is_exhausted() is False
