"""
FastAPI MeTube/yt-dlp Integration Router
Migrated from Flask src/api/metube.py - yt-dlp CLI API endpoints for video downloading
"""

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.services.ytdlp_service import ytdlp_service

logger = logging.getLogger("mvidarr.fastapi.metube")

router = APIRouter(
    prefix="/api/metube",
    tags=["metube"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

COOKIE_FOLDER = "data/cookies"
ALLOWED_EXTENSIONS = {"txt", "cookies"}

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class MusicVideoDownloadRequest(BaseModel):
    """Music video download request"""

    artist: str = Field(..., min_length=1, description="Artist name")
    title: str = Field(..., min_length=1, description="Video title")
    url: str = Field(..., min_length=1, description="Video URL")
    quality: str = Field(default="best", description="Download quality")
    video_id: Optional[int] = Field(None, description="Optional video ID")
    download_subtitles: bool = Field(default=False, description="Download subtitles")
    subtitle_languages: Optional[str] = Field(
        None, description="Subtitle languages (comma-separated)"
    )


class ClearStuckRequest(BaseModel):
    """Clear stuck downloads request"""

    minutes: int = Field(
        default=10, ge=1, le=60, description="Minutes threshold for stuck downloads"
    )


class DownloadResponse(BaseModel):
    """Download operation response"""

    success: bool
    message: Optional[str] = None
    download_id: Optional[int] = None
    error: Optional[str] = None


class QueueResponse(BaseModel):
    """Download queue response"""

    queue: List[Dict[str, Any]]
    total: int


class HistoryResponse(BaseModel):
    """Download history response"""

    history: List[Dict[str, Any]]
    total: int


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    version: Optional[str] = None
    error: Optional[str] = None


class CookieUploadResponse(BaseModel):
    """Cookie upload response"""

    success: bool
    message: str
    filename: Optional[str] = None
    error: Optional[str] = None


class CookieStatusResponse(BaseModel):
    """Cookie status response"""

    success: bool
    cookies_available: bool
    file_size: Optional[int] = None
    modified_time: Optional[float] = None
    path: Optional[str] = None
    message: Optional[str] = None


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================================================================================
# METUBE DOWNLOAD MANAGEMENT ENDPOINTS
# ========================================================================================


@router.get("/test", response_model=HealthResponse)
async def test_connection(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Test yt-dlp availability"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Testing yt-dlp connection for user {current_user.get('username')}"
        )

        result = ytdlp_service.health_check()

        if result["status"] != "healthy":
            raise HTTPException(status_code=503, detail=result)

        return HealthResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"yt-dlp health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "error", "error": str(e)}
        )


@router.get("/queue", response_model=QueueResponse)
async def get_download_queue(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get current download queue including active Celery tasks"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Getting download queue for user {current_user.get('username')}")

        # Get queue from ytdlp service (in-memory downloads)
        legacy_result = ytdlp_service.get_queue()
        queue_items = legacy_result.get("queue", [])

        # Track database download IDs already in the in-memory queue to avoid duplicates
        existing_db_ids = set()
        for item in queue_items:
            db_download_id = item.get("db_download_id")
            if db_download_id:
                existing_db_ids.add(db_download_id)

        # Also check for recent downloads that might be processing but not in memory
        try:
            from datetime import datetime, timedelta

            from ...database.models import Artist, Download

            # Get recent downloads that are still in queue/downloading status
            recent_cutoff = datetime.utcnow() - timedelta(hours=2)  # Last 2 hours

            recent_downloads = (
                session.query(Download, Artist.name)
                .join(Artist, Download.artist_id == Artist.id)
                .filter(
                    Download.status.in_(["queued", "downloading"]),
                    Download.created_at >= recent_cutoff,
                )
                .order_by(Download.created_at.desc())
                .limit(20)
                .all()
            )

            # Only add downloads that aren't already in the in-memory queue
            for download, artist_name in recent_downloads:
                if download.id not in existing_db_ids:
                    queue_entry = {
                        "id": f"db_{download.id}",
                        "title": download.title,
                        "artist": artist_name,
                        "url": download.original_url,
                        "status": download.status,
                        "progress": download.progress or 0,
                        "quality": download.quality or "best",
                        "created_at": (
                            download.created_at.isoformat()
                            if download.created_at
                            else None
                        ),
                        "task_type": "database",
                        "db_download_id": download.id,
                    }
                    queue_items.append(queue_entry)

        except Exception as db_error:
            logger.warning(f"Failed to get recent database downloads: {db_error}")

        return QueueResponse(queue=queue_items, total=len(queue_items))

    except Exception as e:
        logger.error(f"Failed to get download queue: {e}")
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

        result = ytdlp_service.get_history(limit=limit)

        return HistoryResponse(
            history=result.get("history", []), total=result.get("total", 0)
        )

    except Exception as e:
        logger.error(f"Failed to get download history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/music-video", response_model=DownloadResponse)
async def add_music_video_download(
    download_request: MusicVideoDownloadRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Add a music video download with MVidarr formatting"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Adding music video download '{download_request.artist} - {download_request.title}' for user {current_user.get('username')}"
        )

        # Read subtitle settings from database if not provided in request
        from src.services.settings_service import settings

        # Use global setting for subtitles if not explicitly set in request
        download_subtitles = download_request.download_subtitles
        if not download_subtitles:
            download_subtitles = settings.get_bool("download_subtitles", False)

        subtitle_languages = download_request.subtitle_languages
        if not subtitle_languages:
            subtitle_languages = settings.get("subtitle_languages", "en,en-US")

        logger.info(
            f"Download settings: subtitles={download_subtitles}, languages={subtitle_languages}"
        )

        result = ytdlp_service.add_music_video_download(
            artist=download_request.artist,
            title=download_request.title,
            url=download_request.url,
            quality=download_request.quality,
            video_id=download_request.video_id,
            download_subtitles=download_subtitles,
            subtitle_languages=subtitle_languages,
        )

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add music video download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/{download_id}/stop", response_model=DownloadResponse)
async def stop_download(
    download_id: str,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Stop a specific download"""
    try:
        user_id = current_user.get("user_id", 1)

        # Parse download_id (handle both integer and "db_123" format)
        try:
            if download_id.startswith("db_"):
                actual_id = int(download_id[3:])  # Remove "db_" prefix
            else:
                actual_id = int(download_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid download ID format")

        logger.info(
            f"Stopping download {actual_id} for user {current_user.get('username')}"
        )

        result = ytdlp_service.stop_download(actual_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/{download_id}/retry", response_model=DownloadResponse)
async def retry_download(
    download_id: str,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Retry a failed download"""
    try:
        user_id = current_user.get("user_id", 1)

        # Parse download_id (handle both integer and "db_123" format)
        try:
            if download_id.startswith("db_"):
                actual_id = int(download_id[3:])  # Remove "db_" prefix
            else:
                actual_id = int(download_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid download ID format")

        logger.info(
            f"Retrying download {actual_id} for user {current_user.get('username')}"
        )

        result = ytdlp_service.retry_download(actual_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/clear", response_model=DownloadResponse)
async def clear_history(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Clear download history"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Clearing download history for user {current_user.get('username')}"
        )

        result = ytdlp_service.clear_history()

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-stuck", response_model=DownloadResponse)
async def clear_stuck_downloads(
    clear_request: ClearStuckRequest = ClearStuckRequest(),
    force: bool = Query(
        default=False, description="Force clear all downloads regardless of time"
    ),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Clear downloads stuck at 0% progress"""
    try:
        user_id = current_user.get("user_id", 1)

        if force:
            logger.info(
                f"Force clearing ALL downloads for user {current_user.get('username')}"
            )
        else:
            logger.info(
                f"Clearing stuck downloads (minutes={clear_request.minutes}) for user {current_user.get('username')}"
            )

        # Clear stuck downloads from database (not just in-memory ytdlp service)
        from datetime import datetime, timedelta

        from ...database.models import Download, Video, VideoStatus

        if force:
            # Force clear ALL downloads regardless of time
            stuck_downloads = (
                session.query(Download)
                .filter(Download.status.in_(["queued", "downloading"]))
                .all()
            )
        else:
            # Clear only downloads stuck longer than specified time
            cutoff_time = datetime.utcnow() - timedelta(minutes=clear_request.minutes)
            stuck_downloads = (
                session.query(Download)
                .filter(
                    Download.status.in_(["queued", "downloading"]),
                    Download.created_at < cutoff_time,
                )
                .all()
            )

        cleared_count = 0
        for download in stuck_downloads:
            logger.info(f"Clearing stuck download {download.id}: {download.title}")

            # Update download status
            if force:
                download.status = "cancelled"
                download.error_message = "Force cleared by user"
            else:
                download.status = "failed"
                download.error_message = (
                    f"Cleared as stuck after {clear_request.minutes} minutes"
                )
            download.completed_at = datetime.utcnow()

            # Reset associated video status back to WANTED
            if download.video_id:
                video = (
                    session.query(Video).filter(Video.id == download.video_id).first()
                )
                if video and video.status == VideoStatus.DOWNLOADING:
                    video.status = VideoStatus.WANTED

            cleared_count += 1

        session.commit()

        if force:
            message = f"Force cleared {cleared_count} downloads"
        else:
            message = f"Cleared {cleared_count} stuck downloads"

        result = {
            "success": True,
            "message": message,
            "download_id": None,
            "error": None,
        }

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear stuck downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-clear-all", response_model=DownloadResponse)
async def force_clear_all_downloads(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Force clear ALL queued/downloading downloads"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Force clearing all downloads for user {current_user.get('username')}"
        )

        # Clear ALL downloads from database
        from datetime import datetime

        from ...database.models import Download, Video, VideoStatus

        # Find ALL queued/downloading downloads
        all_downloads = (
            session.query(Download)
            .filter(Download.status.in_(["queued", "downloading"]))
            .all()
        )

        cleared_count = 0
        for download in all_downloads:
            logger.info(f"Force clearing download {download.id}: {download.title}")

            # Update download status to cancelled
            download.status = "cancelled"
            download.error_message = "Force cleared by user"
            download.completed_at = datetime.utcnow()

            # Reset associated video status back to WANTED
            if download.video_id:
                video = (
                    session.query(Video).filter(Video.id == download.video_id).first()
                )
                if video and video.status == VideoStatus.DOWNLOADING:
                    video.status = VideoStatus.WANTED

            cleared_count += 1

        session.commit()

        result = {
            "success": True,
            "message": f"Force cleared {cleared_count} downloads",
            "download_id": None,
            "error": None,
        }

        return DownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force clear downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get yt-dlp service health status"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Checking yt-dlp health for user {current_user.get('username')}")

        result = ytdlp_service.health_check()

        if result["status"] != "healthy":
            raise HTTPException(status_code=503, detail=result)

        return HealthResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503, detail={"status": "unhealthy", "error": str(e)}
        )


# ========================================================================================
# COOKIE MANAGEMENT ENDPOINTS
# ========================================================================================


@router.post("/cookies/upload", response_model=CookieUploadResponse)
async def upload_cookies(
    file: UploadFile = File(..., description="YouTube cookies file (.txt or .cookies)"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Upload YouTube cookies file for age-restricted video downloads"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Uploading cookies file '{file.filename}' for user {current_user.get('username')}"
        )

        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")

        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail="File type not allowed. Please upload a .txt or .cookies file",
            )

        # Ensure upload directory exists
        os.makedirs(COOKIE_FOLDER, exist_ok=True)

        # Save as youtube_cookies.txt for yt-dlp
        cookie_filename = "youtube_cookies.txt"
        cookie_path = os.path.join(COOKIE_FOLDER, cookie_filename)

        # Read and save the file
        content = await file.read()

        with open(cookie_path, "wb") as f:
            f.write(content)

        # Validate cookie file format
        try:
            with open(cookie_path, "r") as f:
                content_str = f.read().strip()
                if not content_str:
                    os.remove(cookie_path)
                    raise HTTPException(status_code=400, detail="Cookie file is empty")

                # Basic validation - check if it looks like cookies
                if not (
                    "youtube.com" in content_str.lower()
                    or "session_token" in content_str.lower()
                    or "\t" in content_str
                ):
                    os.remove(cookie_path)
                    raise HTTPException(
                        status_code=400,
                        detail="File does not appear to contain valid cookies",
                    )

        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(cookie_path):
                os.remove(cookie_path)
            raise HTTPException(
                status_code=400, detail=f"Failed to validate cookie file: {e}"
            )

        # Update ytdlp service to use the uploaded cookies
        ytdlp_service.set_cookie_file(cookie_path)

        logger.info(f"Cookies uploaded successfully: {file.filename}")

        return CookieUploadResponse(
            success=True,
            message="Cookies uploaded successfully",
            filename=cookie_filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cookies/status", response_model=CookieStatusResponse)
async def cookies_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Check if cookies are uploaded and available"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Checking cookie status for user {current_user.get('username')}")

        cookie_path = os.path.join(COOKIE_FOLDER, "youtube_cookies.txt")

        if os.path.exists(cookie_path):
            # Get file info
            stat = os.stat(cookie_path)
            file_size = stat.st_size
            modified_time = stat.st_mtime

            return CookieStatusResponse(
                success=True,
                cookies_available=True,
                file_size=file_size,
                modified_time=modified_time,
                path=cookie_path,
            )
        else:
            return CookieStatusResponse(
                success=True,
                cookies_available=False,
                message="No cookies file uploaded",
            )

    except Exception as e:
        logger.error(f"Failed to check cookie status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cookies/delete", response_model=CookieUploadResponse)
async def delete_cookies(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Delete uploaded cookies file"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Deleting cookies file for user {current_user.get('username')}")

        cookie_path = os.path.join(COOKIE_FOLDER, "youtube_cookies.txt")

        if os.path.exists(cookie_path):
            os.remove(cookie_path)
            ytdlp_service.clear_cookie_file()

            logger.info("Cookies deleted successfully")
            return CookieUploadResponse(
                success=True, message="Cookies deleted successfully"
            )
        else:
            return CookieUploadResponse(
                success=True, message="No cookies file to delete"
            )

    except Exception as e:
        logger.error(f"Failed to delete cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-pending", response_model=DownloadResponse)
async def process_pending_downloads(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Process pending downloads from database"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Processing pending downloads for user {current_user.get('username')}"
        )

        result = ytdlp_service.process_pending_downloads()

        if result.get("success"):
            return DownloadResponse(
                success=True,
                message=result.get("message", "Pending downloads processed"),
                download_id=None,
                error=None,
            )
        else:
            raise HTTPException(status_code=400, detail=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process pending downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))
