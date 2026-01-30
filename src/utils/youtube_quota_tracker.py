"""
YouTube API Quota Tracker

Tracks YouTube API quota usage to help monitor and optimize API calls.

YouTube Data API v3 Quota Costs:
- search: 100 units
- videos.list: 1 unit (per request, batches up to 50 IDs)
- playlistItems.list: 1 unit (per page, max 50 items)
- channels.list: 1 unit
- playlists.list: 1 unit

Daily quota limit: 10,000 units (free tier)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class YouTubeQuotaTracker:
    """Track YouTube API quota usage"""

    # Quota costs for different API operations
    QUOTA_COSTS = {
        "search": 100,  # Search API is expensive
        "video_details": 1,  # Videos.list API
        "playlist": 1,  # PlaylistItems.list API (per page)
        "playlist_info": 1,  # Playlists.list API
        "channel": 100,  # Search for channels
        "default": 1,
    }

    DAILY_QUOTA_LIMIT = 10000  # Free tier limit

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize quota tracker with optional persistent storage"""
        self.storage_path = storage_path or "/tmp/youtube_quota_tracker.json"
        self._quota_data = self._load_quota_data()

    def _load_quota_data(self) -> Dict:
        """Load quota data from storage"""
        try:
            if Path(self.storage_path).exists():
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    # Reset if data is from previous day
                    if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                        logger.info("Resetting quota tracker for new day")
                        return self._create_fresh_data()
                    return data
        except Exception as e:
            logger.error(f"Failed to load quota data: {e}")

        return self._create_fresh_data()

    def _create_fresh_data(self) -> Dict:
        """Create fresh quota tracking data"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_used": 0,
            "operations": {},
            "timestamps": [],
        }

    def _save_quota_data(self):
        """Save quota data to storage"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self._quota_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save quota data: {e}")

    def track_operation(self, operation: str, count: int = 1):
        """
        Track an API operation and its quota cost

        Args:
            operation: Type of operation (search, video_details, playlist, etc.)
            count: Number of times this operation was performed (default: 1)
        """
        # Reset data if it's a new day
        if self._quota_data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            self._quota_data = self._create_fresh_data()

        # Get quota cost for this operation
        quota_cost = self.QUOTA_COSTS.get(operation, self.QUOTA_COSTS["default"])
        total_cost = quota_cost * count

        # Update tracking data
        self._quota_data["total_used"] += total_cost

        if operation not in self._quota_data["operations"]:
            self._quota_data["operations"][operation] = {
                "count": 0,
                "quota_used": 0,
            }

        self._quota_data["operations"][operation]["count"] += count
        self._quota_data["operations"][operation]["quota_used"] += total_cost

        # Add timestamp
        self._quota_data["timestamps"].append(
            {
                "time": datetime.now().isoformat(),
                "operation": operation,
                "cost": total_cost,
            }
        )

        # Keep only last 1000 timestamps to avoid file bloat
        if len(self._quota_data["timestamps"]) > 1000:
            self._quota_data["timestamps"] = self._quota_data["timestamps"][-1000:]

        # Save to disk
        self._save_quota_data()

        # Log warning if approaching limit
        usage_percent = (self._quota_data["total_used"] / self.DAILY_QUOTA_LIMIT) * 100
        if usage_percent >= 90:
            logger.warning(
                f"YouTube API quota usage at {usage_percent:.1f}% "
                f"({self._quota_data['total_used']}/{self.DAILY_QUOTA_LIMIT} units)"
            )
        elif usage_percent >= 75:
            logger.info(
                f"YouTube API quota usage at {usage_percent:.1f}% "
                f"({self._quota_data['total_used']}/{self.DAILY_QUOTA_LIMIT} units)"
            )

    def get_stats(self) -> Dict:
        """Get current quota usage statistics"""
        total_used = self._quota_data.get("total_used", 0)
        remaining = self.DAILY_QUOTA_LIMIT - total_used
        usage_percent = (total_used / self.DAILY_QUOTA_LIMIT) * 100

        return {
            "date": self._quota_data.get("date"),
            "total_used": total_used,
            "total_remaining": remaining,
            "daily_limit": self.DAILY_QUOTA_LIMIT,
            "usage_percent": round(usage_percent, 2),
            "operations": self._quota_data.get("operations", {}),
            "operation_count": len(self._quota_data.get("timestamps", [])),
        }

    def reset(self):
        """Manually reset quota tracking (useful for testing)"""
        self._quota_data = self._create_fresh_data()
        self._save_quota_data()
        logger.info("Quota tracker reset")


# Global quota tracker instance
_quota_tracker = None


def get_quota_tracker() -> YouTubeQuotaTracker:
    """Get or create the global quota tracker instance"""
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = YouTubeQuotaTracker()
        logger.info("Initialized YouTube API quota tracker")
    return _quota_tracker


def track_youtube_api_call(operation: str, count: int = 1):
    """
    Convenience function to track a YouTube API call

    Args:
        operation: Type of operation (search, video_details, playlist, etc.)
        count: Number of times this operation was performed
    """
    tracker = get_quota_tracker()
    tracker.track_operation(operation, count)
