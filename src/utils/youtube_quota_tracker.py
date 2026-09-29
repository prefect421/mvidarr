"""
YouTube API Quota Tracker

Tracks YouTube API quota usage to help monitor and optimize API calls.
File-locking ensures multi-process safety across Celery workers.

YouTube Data API v3 Quota Costs:
- search: 100 units
- videos.list: 1 unit (per request, batches up to 50 IDs)
- playlistItems.list: 1 unit (per page, max 50 items)
- channels.list: 1 unit
- playlists.list: 1 unit

Daily quota limit: 10,000 units (free tier). Google resets it at midnight
Pacific time, so the tracker's day follows Pacific time, not the server's.

The local count is only an estimate: it misses spend by other processes/apps
sharing the API key. When Google itself reports the daily quota exceeded,
callers must call mark_exhausted() so every process stops calling until the
next Pacific-time day.
"""

import fcntl
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")

# Substrings in a YouTube API error body that mean the *daily* quota is gone
# (as opposed to a transient per-minute rate limit or a bad/restricted key)
_DAILY_QUOTA_MARKERS = ("quotaexceeded", "dailylimitexceeded", "per day")


def is_daily_quota_error(status_code: int, body: str) -> bool:
    """True if a YouTube API response says the daily quota is exhausted."""
    if status_code not in (403, 429):
        return False
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _DAILY_QUOTA_MARKERS)


class YouTubeQuotaTracker:
    """Track YouTube API quota usage with multi-process file locking"""

    QUOTA_COSTS = {
        "search": 100,
        "video_details": 1,
        "playlist": 1,
        "playlist_info": 1,
        "channel": 100,
        "default": 1,
    }

    DAILY_QUOTA_LIMIT = 10000

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or "/tmp/youtube_quota_tracker.json"
        # Ensure file exists so locking works
        if not Path(self.storage_path).exists():
            self._write_data(self._create_fresh_data())

    @staticmethod
    def _quota_day() -> str:
        return datetime.now(QUOTA_TIMEZONE).strftime("%Y-%m-%d")

    def _create_fresh_data(self) -> Dict:
        return {
            "date": self._quota_day(),
            "exhausted": False,
            "total_used": 0,
            "operations": {},
            "timestamps": [],
        }

    def _read_data(self) -> Dict:
        """Read quota data from disk, reset if stale."""
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
            if data.get("date") != self._quota_day():
                logger.info("Resetting quota tracker for new day")
                return self._create_fresh_data()
            return data
        except Exception:
            return self._create_fresh_data()

    def _write_data(self, data: Dict) -> None:
        try:
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save quota data: {e}")

    def has_budget(self, units: int) -> bool:
        """Return True if `units` can be spent without exceeding the daily limit."""
        data = self._read_data()
        if data.get("exhausted"):
            return False
        return (data.get("total_used", 0) + units) <= self.DAILY_QUOTA_LIMIT

    def note_http_error(self, exc: Exception) -> bool:
        """Call from an API error handler: if `exc` carries a response saying the
        daily quota is exceeded, mark the quota exhausted. Returns True if so."""
        response = getattr(exc, "response", None)
        if response is None:
            return False
        try:
            body = response.text
        except Exception:
            body = ""
        if is_daily_quota_error(getattr(response, "status_code", 0), body):
            self.mark_exhausted()
            return True
        return False

    def is_exhausted(self) -> bool:
        """True if Google has reported today's quota exhausted."""
        return bool(self._read_data().get("exhausted"))

    def mark_exhausted(self) -> None:
        """Record that Google reported the daily quota exceeded.

        Blocks all further calls (in every process sharing the storage file)
        until the quota day rolls over, regardless of the local count.
        """
        try:
            with open(self.storage_path, "a+") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    data = self._read_data()
                    if not data.get("exhausted"):
                        data["exhausted"] = True
                        self._write_data(data)
                        logger.warning(
                            "YouTube API reported the daily quota exceeded — "
                            "blocking YouTube calls until it resets (midnight Pacific)"
                        )
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to mark quota exhausted: {e}")

    def consume(self, operation: str, count: int = 1) -> bool:
        """
        Atomically check budget and record usage.

        Returns True if the call was allowed, False if quota is exhausted.
        Uses an exclusive file lock so Celery workers don't race.
        """
        cost = self.QUOTA_COSTS.get(operation, self.QUOTA_COSTS["default"]) * count

        try:
            # Open for append+read so we can lock before reading
            with open(self.storage_path, "a+") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    data = self._read_data()

                    if data.get("exhausted"):
                        return False

                    if data.get("total_used", 0) + cost > self.DAILY_QUOTA_LIMIT:
                        logger.warning(
                            f"YouTube API quota exhausted — blocking {operation} "
                            f"({cost} units requested, "
                            f"{self.DAILY_QUOTA_LIMIT - data['total_used']} remaining)"
                        )
                        return False

                    data["total_used"] = data.get("total_used", 0) + cost

                    if operation not in data["operations"]:
                        data["operations"][operation] = {"count": 0, "quota_used": 0}
                    data["operations"][operation]["count"] += count
                    data["operations"][operation]["quota_used"] += cost

                    ts = data.setdefault("timestamps", [])
                    ts.append(
                        {
                            "time": datetime.now().isoformat(),
                            "operation": operation,
                            "cost": cost,
                        }
                    )
                    if len(ts) > 1000:
                        data["timestamps"] = ts[-1000:]

                    self._write_data(data)

                    usage_pct = (data["total_used"] / self.DAILY_QUOTA_LIMIT) * 100
                    if usage_pct >= 90:
                        logger.warning(
                            f"YouTube API quota at {usage_pct:.1f}% "
                            f"({data['total_used']}/{self.DAILY_QUOTA_LIMIT} units)"
                        )
                    elif usage_pct >= 75:
                        logger.info(
                            f"YouTube API quota at {usage_pct:.1f}% "
                            f"({data['total_used']}/{self.DAILY_QUOTA_LIMIT} units)"
                        )
                    return True
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"Quota consume error: {e}")
            # Fail open — don't block API calls if tracker is broken
            return True

    # Keep backward-compatible track_operation as an alias
    def track_operation(self, operation: str, count: int = 1) -> None:
        """Legacy alias — prefer consume() for enforcement."""
        self.consume(operation, count)

    def get_stats(self) -> Dict:
        data = self._read_data()
        total_used = data.get("total_used", 0)
        remaining = self.DAILY_QUOTA_LIMIT - total_used
        return {
            "date": data.get("date"),
            "total_used": total_used,
            "total_remaining": remaining,
            "daily_limit": self.DAILY_QUOTA_LIMIT,
            "exhausted": bool(data.get("exhausted")),
            "usage_percent": round((total_used / self.DAILY_QUOTA_LIMIT) * 100, 2),
            "operations": data.get("operations", {}),
            "operation_count": len(data.get("timestamps", [])),
        }

    def reset(self) -> None:
        self._write_data(self._create_fresh_data())
        logger.info("Quota tracker reset")


_quota_tracker = None


def get_quota_tracker() -> YouTubeQuotaTracker:
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = YouTubeQuotaTracker()
        logger.info("Initialized YouTube API quota tracker")
    return _quota_tracker


def track_youtube_api_call(operation: str, count: int = 1) -> None:
    """Legacy convenience function — does NOT enforce quota. Use consume() directly."""
    get_quota_tracker().track_operation(operation, count)
