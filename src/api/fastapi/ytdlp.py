"""
FastAPI YouTube-DL Python Integration Router
Migrated from Flask src/api/ytdlp.py - yt-dlp API endpoints for download management and status
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.services.ytdlp_service import ytdlp_service

logger = logging.getLogger("mvidarr.fastapi.ytdlp")

router = APIRouter(
    prefix="/api/ytdlp",
    tags=["ytdlp"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class CookieStatusResponse(BaseModel):
    """Cookie status response"""

    cookies_available: bool
    error: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    modified_time: Optional[float] = None


class HealthStatusResponse(BaseModel):
    """Health status response"""

    status: str
    version: Optional[str] = None
    error: Optional[str] = None


class QueueStatusResponse(BaseModel):
    """Queue status response"""

    queue: List[Dict[str, Any]]
    total: int
    active_downloads: int = 0


class HistoryResponse(BaseModel):
    """Download history response"""

    history: List[Dict[str, Any]]
    total: int


# ========================================================================================
# YTDLP SERVICE STATUS ENDPOINTS
# ========================================================================================


@router.get("/cookie-status", response_model=CookieStatusResponse)
async def get_cookie_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get current cookie file status for SABR workarounds"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Getting cookie status for user {current_user.get('username')}")

        status = ytdlp_service.get_cookie_status()
        logger.debug(f"Cookie status result: {status}")

        # Ensure we always return a valid response
        if not isinstance(status, dict):
            status = {"cookies_available": False, "error": "Invalid status response"}

        return CookieStatusResponse(
            cookies_available=status.get("cookies_available", False),
            error=status.get("error"),
            file_path=status.get("file_path"),
            file_size=status.get("file_size"),
            modified_time=status.get("modified_time"),
        )

    except Exception as e:
        logger.error(f"Error getting cookie status: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")

        return CookieStatusResponse(cookies_available=False, error=str(e))


@router.get("/health", response_model=HealthStatusResponse)
async def health_check(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Check yt-dlp service health and version"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Checking yt-dlp health for user {current_user.get('username')}")

        health_status = ytdlp_service.health_check()

        return HealthStatusResponse(
            status=health_status.get("status", "unknown"),
            version=health_status.get("version"),
            error=health_status.get("error"),
        )

    except Exception as e:
        logger.error(f"Error checking yt-dlp health: {e}")
        return HealthStatusResponse(status="unhealthy", error=str(e))


@router.get("/queue", response_model=QueueStatusResponse)
async def get_download_queue(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get current download queue status"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting download queue status for user {current_user.get('username')}"
        )

        queue_status = ytdlp_service.get_queue()

        return QueueStatusResponse(
            queue=queue_status.get("queue", []),
            total=queue_status.get("total", 0),
            active_downloads=queue_status.get("active_downloads", 0),
        )

    except Exception as e:
        logger.error(f"Error getting download queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=HistoryResponse)
async def get_download_history(
    limit: int = Query(
        default=50, ge=1, le=500, description="Maximum number of history items"
    ),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get download history"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting download history (limit={limit}) for user {current_user.get('username')}"
        )

        history = ytdlp_service.get_history(limit=limit)

        return HistoryResponse(
            history=history.get("history", []), total=history.get("total", 0)
        )

    except Exception as e:
        logger.error(f"Error getting download history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
