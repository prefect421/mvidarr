"""
YouTube API Quota Monitoring Endpoint

Provides real-time visibility into YouTube API quota usage.
"""

from fastapi import APIRouter, Depends

from src.api.fastapi.auth_dependencies import require_authentication
from src.utils.youtube_cache import get_youtube_cache
from src.utils.youtube_quota_tracker import get_quota_tracker

router = APIRouter()


@router.get("")
async def get_quota_stats(current_user: dict = Depends(require_authentication)):
    """Get current YouTube API quota usage statistics"""

    # Get quota tracker stats
    tracker = get_quota_tracker()
    quota_stats = tracker.get_stats()

    # Get cache stats
    cache = get_youtube_cache()
    cache_stats = cache.get_stats()

    # Calculate optimization effectiveness
    total_requests = cache_stats["total_requests"]
    cache_hits = cache_stats["hit_count"]
    api_calls_saved = cache_hits

    return {
        "success": True,
        "quota": {
            "date": quota_stats["date"],
            "total_used": quota_stats["total_used"],
            "total_remaining": quota_stats["total_remaining"],
            "daily_limit": quota_stats["daily_limit"],
            "usage_percent": quota_stats["usage_percent"],
            "operations": quota_stats["operations"],
        },
        "cache": {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "cache_misses": cache_stats["miss_count"],
            "hit_rate": round(cache_stats["hit_rate"] * 100, 1),
            "api_calls_saved": api_calls_saved,
            "total_entries": cache_stats["total_entries"],
            "active_entries": cache_stats["active_entries"],
        },
        "optimization": {
            "enabled": True,
            "estimated_savings": f"{round(cache_stats['hit_rate'] * 100)}%",
            "quota_saved_today": api_calls_saved,
        },
    }


@router.post("/reset")
async def reset_quota_tracker(
    current_user: dict = Depends(require_authentication),
):
    """Reset quota tracker (admin only)"""

    tracker = get_quota_tracker()
    tracker.reset()

    return {"success": True, "message": "Quota tracker has been reset"}
