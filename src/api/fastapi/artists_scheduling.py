"""
Artists Scheduling API - Scheduler V2 Integration
Version: v0.10.1
Phase 4: API Layer

REST API endpoints for per-artist scheduling configuration and control.

Endpoints:
- GET /api/artists/{artist_id}/scheduling - Get artist scheduling config
- PUT /api/artists/{artist_id}/scheduling - Update scheduling config
- POST /api/artists/{artist_id}/trigger-discovery - Trigger discovery for artist
- GET /api/artists/{artist_id}/scheduling/status - Get scheduling status
- GET /api/artists/{artist_id}/scheduling/history - Get job history for artist
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.database.connection import get_db
from src.database.models import Artist, ScheduledJob
from src.services.scheduler_service_v2 import scheduler_v2
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.artists_scheduling")

router = APIRouter()


# Pydantic Models


class ArtistSchedulingConfig(BaseModel):
    """Artist scheduling configuration"""

    discovery_enabled: bool = Field(
        default=True, description="Enable scheduled discovery"
    )
    download_enabled: bool = Field(default=True, description="Enable auto-downloads")
    discovery_interval_hours: Optional[int] = Field(
        None, description="Custom discovery interval (null = use global)"
    )
    max_videos_per_discovery: Optional[int] = Field(
        None, description="Max videos per discovery run (null = unlimited)"
    )
    schedule_priority: str = Field(
        default="medium", description="Priority: high, medium, low"
    )


class ArtistSchedulingStatusResponse(BaseModel):
    """Artist scheduling status"""

    artist_id: int
    artist_name: str
    discovery_enabled: bool
    download_enabled: bool
    discovery_interval_hours: Optional[int]
    last_discovery: Optional[str]
    last_download: Optional[str]
    next_discovery: Optional[str]
    schedule_priority: str
    recent_jobs: int
    failed_jobs: int
    success_rate: float


# API Endpoints


@router.get("/{artist_id}/scheduling", response_model=ArtistSchedulingConfig)
async def get_artist_scheduling(artist_id: int) -> Dict[str, Any]:
    """
    Get artist scheduling configuration

    Returns current scheduling settings for the artist.
    """
    try:
        with get_db() as db:
            artist = db.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                raise HTTPException(status_code=404, detail="Artist not found")

            return {
                "discovery_enabled": (
                    artist.discovery_enabled
                    if hasattr(artist, "discovery_enabled")
                    else True
                ),
                "download_enabled": (
                    artist.download_enabled
                    if hasattr(artist, "download_enabled")
                    else True
                ),
                "discovery_interval_hours": (
                    artist.discovery_interval_hours
                    if hasattr(artist, "discovery_interval_hours")
                    else None
                ),
                "max_videos_per_discovery": (
                    artist.max_videos_per_discovery
                    if hasattr(artist, "max_videos_per_discovery")
                    else None
                ),
                "schedule_priority": (
                    artist.schedule_priority
                    if hasattr(artist, "schedule_priority")
                    else "medium"
                ),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduling for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{artist_id}/scheduling", response_model=ArtistSchedulingConfig)
async def update_artist_scheduling(
    artist_id: int, config: ArtistSchedulingConfig
) -> Dict[str, Any]:
    """
    Update artist scheduling configuration

    Updates scheduling settings for the artist.
    """
    try:
        with get_db() as db:
            artist = db.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                raise HTTPException(status_code=404, detail="Artist not found")

            # Update scheduling fields if they exist
            if hasattr(artist, "discovery_enabled"):
                artist.discovery_enabled = config.discovery_enabled
            if hasattr(artist, "download_enabled"):
                artist.download_enabled = config.download_enabled
            if hasattr(artist, "discovery_interval_hours"):
                artist.discovery_interval_hours = config.discovery_interval_hours
            if hasattr(artist, "max_videos_per_discovery"):
                artist.max_videos_per_discovery = config.max_videos_per_discovery
            if hasattr(artist, "schedule_priority"):
                artist.schedule_priority = config.schedule_priority

            db.commit()
            db.refresh(artist)

            logger.info(f"Updated scheduling for artist {artist_id} ({artist.name})")

            return {
                "discovery_enabled": config.discovery_enabled,
                "download_enabled": config.download_enabled,
                "discovery_interval_hours": config.discovery_interval_hours,
                "max_videos_per_discovery": config.max_videos_per_discovery,
                "schedule_priority": config.schedule_priority,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update scheduling for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{artist_id}/trigger-discovery")
async def trigger_artist_discovery(artist_id: int) -> Dict[str, Any]:
    """
    Manually trigger discovery for specific artist

    Triggers immediate video discovery for the artist.
    """
    try:
        with get_db() as db:
            artist = db.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                raise HTTPException(status_code=404, detail="Artist not found")

            # Trigger discovery via scheduler service
            result = scheduler_v2.trigger_discovery_now(artist_id=artist_id)

            if result.get("status") == "error":
                raise HTTPException(status_code=500, detail=result.get("message"))

            return {
                "status": "triggered",
                "artist_id": artist_id,
                "artist_name": artist.name,
                "task_id": result.get("task_id"),
                "message": f"Discovery triggered for {artist.name}",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger discovery for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{artist_id}/scheduling/status", response_model=ArtistSchedulingStatusResponse
)
async def get_artist_scheduling_status(artist_id: int) -> Dict[str, Any]:
    """
    Get artist scheduling status

    Returns current scheduling status and recent job statistics.
    """
    try:
        with get_db() as db:
            artist = db.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                raise HTTPException(status_code=404, detail="Artist not found")

            # Get recent jobs for this artist (last 7 days)
            since = datetime.utcnow() - timedelta(days=7)
            recent_jobs = (
                db.query(ScheduledJob)
                .filter(
                    ScheduledJob.artist_id == artist_id,
                    ScheduledJob.created_at >= since,
                )
                .all()
            )

            total_jobs = len(recent_jobs)
            failed_jobs = len([j for j in recent_jobs if j.status == "failed"])
            success_rate = (
                ((total_jobs - failed_jobs) / total_jobs * 100)
                if total_jobs > 0
                else 0.0
            )

            # Calculate next discovery time
            next_discovery = None
            if hasattr(artist, "last_discovery") and artist.last_discovery:
                interval_hours = (
                    artist.discovery_interval_hours
                    if hasattr(artist, "discovery_interval_hours")
                    and artist.discovery_interval_hours
                    else 24
                )
                next_discovery = (
                    artist.last_discovery + timedelta(hours=interval_hours)
                ).isoformat()

            return {
                "artist_id": artist_id,
                "artist_name": artist.name,
                "discovery_enabled": (
                    artist.discovery_enabled
                    if hasattr(artist, "discovery_enabled")
                    else True
                ),
                "download_enabled": (
                    artist.download_enabled
                    if hasattr(artist, "download_enabled")
                    else True
                ),
                "discovery_interval_hours": (
                    artist.discovery_interval_hours
                    if hasattr(artist, "discovery_interval_hours")
                    else None
                ),
                "last_discovery": (
                    artist.last_discovery.isoformat()
                    if hasattr(artist, "last_discovery") and artist.last_discovery
                    else None
                ),
                "last_download": (
                    artist.last_download.isoformat()
                    if hasattr(artist, "last_download") and artist.last_download
                    else None
                ),
                "next_discovery": next_discovery,
                "schedule_priority": (
                    artist.schedule_priority
                    if hasattr(artist, "schedule_priority")
                    else "medium"
                ),
                "recent_jobs": total_jobs,
                "failed_jobs": failed_jobs,
                "success_rate": round(success_rate, 2),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduling status for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{artist_id}/scheduling/history")
async def get_artist_scheduling_history(
    artist_id: int, limit: int = 50
) -> Dict[str, Any]:
    """
    Get scheduling job history for artist

    Returns recent scheduled jobs for this artist.
    """
    try:
        with get_db() as db:
            artist = db.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                raise HTTPException(status_code=404, detail="Artist not found")

            # Get job history
            jobs = (
                db.query(ScheduledJob)
                .filter(ScheduledJob.artist_id == artist_id)
                .order_by(ScheduledJob.created_at.desc())
                .limit(limit)
                .all()
            )

            jobs_list = [job.to_dict() for job in jobs]

            return {
                "artist_id": artist_id,
                "artist_name": artist.name,
                "jobs": jobs_list,
                "total": len(jobs_list),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduling history for artist {artist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
