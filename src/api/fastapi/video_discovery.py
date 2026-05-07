"""
FastAPI Video Discovery Router
Migrated from Flask src/api/video_discovery.py - Video discovery system
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.database.models import Artist
from src.services.video_discovery_service import video_discovery_service

logger = logging.getLogger("mvidarr.fastapi.video_discovery")

router = APIRouter(
    prefix="/api/discovery",
    tags=["video-discovery"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class DiscoveryRequest(BaseModel):
    """Video discovery request"""

    limit: int = Field(
        default=10, ge=1, le=50, description="Maximum videos to discover"
    )


class BulkDiscoveryRequest(BaseModel):
    """Bulk video discovery request"""

    limit_per_artist: int = Field(
        default=5, ge=1, le=20, description="Maximum videos per artist"
    )


class DiscoveryResponse(BaseModel):
    """Video discovery response"""

    success: bool
    message: Optional[str] = None
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    discovered_videos: int = 0
    videos: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class BulkDiscoveryResponse(BaseModel):
    """Bulk discovery response"""

    success: bool
    message: Optional[str] = None
    processed_artists: int = 0
    total_discovered: int = 0
    artist_results: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class DiscoveryStatsResponse(BaseModel):
    """Discovery statistics response"""

    success: bool
    stats: Dict[str, Any]


class DiscoveryPreviewResponse(BaseModel):
    """Discovery preview response"""

    success: bool
    preview: bool = True
    note: str = "This is a preview - videos were not stored"
    artist_id: int
    artist_name: Optional[str] = None
    discovered_videos: int = 0
    videos: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


# ========================================================================================
# VIDEO DISCOVERY ENDPOINTS
# ========================================================================================


@router.post("/artist/{artist_id}", response_model=DiscoveryResponse)
async def discover_for_artist(
    artist_id: int = Path(..., description="Artist ID to discover videos for"),
    discovery_request: DiscoveryRequest = DiscoveryRequest(),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Discover new videos for a specific artist"""
    try:
        user_id = current_user.get("user_id", 1)

        # Verify artist exists
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        logger.info(
            f"Discovering videos for artist '{artist.name}' (ID: {artist_id}) with limit {discovery_request.limit} for user {current_user.get('username')}"
        )

        result = video_discovery_service.discover_videos_for_artist(
            artist_id, discovery_request.limit
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Discovery failed")
            )

        return DiscoveryResponse(
            success=result["success"],
            message=result.get("message"),
            artist_id=artist_id,
            artist_name=artist.name,
            discovered_videos=result.get("discovered_videos", 0),
            videos=result.get("videos", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Artist discovery failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/all", response_model=BulkDiscoveryResponse)
async def discover_for_all_artists(
    bulk_request: BulkDiscoveryRequest = BulkDiscoveryRequest(),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Discover new videos for all monitored artists"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Discovering videos for all artists with limit {bulk_request.limit_per_artist} per artist for user {current_user.get('username')}"
        )

        result = video_discovery_service.discover_videos_for_all_artists(
            bulk_request.limit_per_artist
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Bulk discovery failed")
            )

        return BulkDiscoveryResponse(
            success=result["success"],
            message=result.get("message"),
            processed_artists=result.get("processed_artists", 0),
            total_discovered=result.get("total_discovered", 0),
            artist_results=result.get("artist_results", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk discovery failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats", response_model=DiscoveryStatsResponse)
async def get_discovery_stats(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get video discovery statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting discovery statistics for user {current_user.get('username')}"
        )

        stats = video_discovery_service.get_discovery_stats()

        return DiscoveryStatsResponse(success=True, stats=stats)

    except Exception as e:
        logger.error(f"Failed to get discovery stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test/{artist_id}", response_model=DiscoveryPreviewResponse)
async def test_discovery_for_artist(
    artist_id: int = Path(..., description="Artist ID to test discovery for"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Test video discovery for an artist (returns preview without storing)"""
    try:
        user_id = current_user.get("user_id", 1)

        # Verify artist exists
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        logger.info(
            f"Testing video discovery for artist '{artist.name}' (ID: {artist_id}) for user {current_user.get('username')}"
        )

        # This would be a dry-run version that doesn't store results
        result = video_discovery_service.discover_videos_for_artist(artist_id, limit=3)

        if not result.get("success"):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Discovery test failed")
            )

        # Remove stored videos from response for preview
        return DiscoveryPreviewResponse(
            success=result["success"],
            preview=True,
            note="This is a preview - videos were not stored",
            artist_id=artist_id,
            artist_name=artist.name,
            discovered_videos=result.get("discovered_videos", 0),
            videos=result.get("videos", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discovery test failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# HELPER FUNCTIONS FOR SCHEDULER INTEGRATION
# ========================================================================================


async def discover_videos_for_artists(
    limit_artists: int = 5,
    limit_videos_per_artist: int = 3,
    max_artists: Optional[int] = None,
    max_videos_per_artist: Optional[int] = None,
    scheduled: bool = False,
) -> Dict[str, Any]:
    """
    Discover videos for multiple artists (helper function for scheduler)

    Args:
        limit_artists: Maximum number of artists to process (for backward compatibility)
        limit_videos_per_artist: Maximum videos to discover per artist (for backward compatibility)
        max_artists: Alternative name for limit_artists
        max_videos_per_artist: Alternative name for limit_videos_per_artist
        scheduled: Whether this is a scheduled discovery operation

    Returns:
        dict: Discovery results with artists_processed and videos_discovered counts
    """
    try:
        # Support both parameter naming conventions
        artists_limit = max_artists or limit_artists
        videos_limit = max_videos_per_artist or limit_videos_per_artist

        logger.info(
            f"Starting scheduled video discovery for {artists_limit} artists, {videos_limit} videos per artist (scheduled={scheduled})"
        )

        # Use the existing discovery service
        result = video_discovery_service.discover_videos_for_all_artists(
            limit_per_artist=videos_limit, max_artists=artists_limit
        )

        if result.get("success"):
            # Standardize return format for scheduler
            return {
                "success": True,
                "artists_processed": result.get("processed_artists", 0),
                "videos_discovered": result.get("total_discovered", 0),
                "scheduled": scheduled,
                "details": result,
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Discovery failed"),
                "artists_processed": 0,
                "videos_discovered": 0,
            }

    except Exception as e:
        logger.error(f"Error in discover_videos_for_artists: {e}")
        return {
            "success": False,
            "error": str(e),
            "artists_processed": 0,
            "videos_discovered": 0,
        }
