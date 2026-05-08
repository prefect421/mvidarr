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
