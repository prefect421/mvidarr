"""
FastAPI Video Quality API Router
Native asyncio support for video quality analysis and upgrades
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.services.job_queue import BackgroundJob, JobPriority, JobType, get_job_queue
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.video_quality")

router = APIRouter(prefix="/api/video-quality", tags=["Video Quality"])


# Pydantic models
class VideoUpgradeRequest(BaseModel):
    user_id: Optional[str] = None


class VideoUpgradeResponse(BaseModel):
    success: bool
    job_id: str
    message: str


class UpgradeableVideo(BaseModel):
    video_id: int
    title: str
    artist_name: str
    current_quality: str
    current_height: int
    recommended_quality: str
    upgrade_priority: int
    quality_score: int
    file_size_mb: float


class UpgradeableVideosResponse(BaseModel):
    success: bool
    count: int
    upgradeable_videos: List[UpgradeableVideo]


# Dependency for current user
async def get_current_user():
    """Get current user - simplified implementation"""
    # TODO: Implement proper authentication
    return "admin"


@router.post("/upgrade/{video_id}")
async def upgrade_video_quality(
    video_id: int,
    request: VideoUpgradeRequest,
    current_user: str = Depends(get_current_user),
):
    """Upgrade a video to higher quality (background job)"""
    try:
        # Create background job for video quality upgrade
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_UPGRADE,
            priority=JobPriority.HIGH,  # Quality upgrades are high priority
            payload={"video_id": video_id, "user_id": request.user_id},
            created_by=current_user,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(f"Enqueued video quality upgrade job {job_id} for video {video_id}")

        return VideoUpgradeResponse(
            success=True,
            job_id=job_id,
            message=f"Video quality upgrade job queued for video {video_id}",
        )

    except Exception as e:
        logger.error(f"Error queueing video quality upgrade for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/analyze/{video_id}")
async def analyze_video_quality(
    video_id: int, current_user: str = Depends(get_current_user)
):
    """Analyze the quality of a specific video (background job)"""
    try:
        # Create background job for video quality analysis
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_ANALYZE,
            priority=JobPriority.NORMAL,
            payload={"video_id": video_id},
            created_by=current_user,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(
            f"Enqueued video quality analysis job {job_id} for video {video_id}"
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Video quality analysis job queued for video {video_id}",
        }

    except Exception as e:
        logger.error(f"Error queueing video quality analysis for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/upgradeable")
async def find_upgradeable_videos() -> UpgradeableVideosResponse:
    """Find videos that could benefit from quality upgrades"""
    try:
        # Import here to avoid circular imports
        from src.services.video_quality_service import VideoQualityService

        # Get upgradeable videos
        videos = await VideoQualityService.find_upgradeable_videos()

        # Convert to response format
        upgradeable_videos = []
        for video in videos:
            upgradeable_videos.append(
                UpgradeableVideo(
                    video_id=video.get("video_id"),
                    title=video.get("title", "Unknown"),
                    artist_name=video.get("artist_name", "Unknown"),
                    current_quality=video.get("current_quality", "Unknown"),
                    current_height=video.get("current_height", 0),
                    recommended_quality=video.get("recommended_quality", "best"),
                    upgrade_priority=video.get("upgrade_priority", 50),
                    quality_score=video.get("quality_score", 0),
                    file_size_mb=video.get("file_size_mb", 0.0),
                )
            )

        return UpgradeableVideosResponse(
            success=True,
            count=len(upgradeable_videos),
            upgradeable_videos=upgradeable_videos,
        )

    except Exception as e:
        logger.error(f"Error finding upgradeable videos: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/bulk-upgrade")
async def bulk_upgrade_videos(
    video_ids: List[int], current_user: str = Depends(get_current_user)
):
    """Upgrade multiple videos to higher quality (background job)"""
    try:
        if not video_ids:
            raise HTTPException(
                status_code=400, detail={"error": "video_ids must be a non-empty array"}
            )

        # Create background job for bulk video quality upgrade
        job = BackgroundJob(
            type=JobType.VIDEO_QUALITY_BULK_UPGRADE,
            priority=JobPriority.HIGH,  # Bulk upgrades are high priority
            payload={"video_ids": video_ids, "user_id": None},  # Can be extended later
            created_by=current_user,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(
            f"Enqueued bulk video quality upgrade job {job_id} for {len(video_ids)} videos"
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Bulk video quality upgrade job queued for {len(video_ids)} videos",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing bulk video quality upgrade: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/preferences")
async def get_quality_preferences():
    """Get quality preferences for user or system defaults"""
    try:
        # Import here to avoid circular imports
        from src.services.video_quality_service import VideoQualityService

        preferences = await VideoQualityService.get_quality_preferences()
        return {"success": True, "preferences": preferences}

    except Exception as e:
        logger.error(f"Error getting quality preferences: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/statistics")
async def get_quality_statistics():
    """Get system-wide video quality statistics"""
    try:
        # Import here to avoid circular imports
        from src.services.video_quality_service import VideoQualityService

        stats = await VideoQualityService.get_quality_statistics()
        return {"success": True, "statistics": stats}

    except Exception as e:
        logger.error(f"Error getting quality statistics: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})
