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
from src.utils.logger import get_logger

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
    subtitle_languages: Optional[str] = Field(None, description="Subtitle languages (comma-separated)")


class ClearStuckRequest(BaseModel):
    """Clear stuck downloads request"""
    minutes: int = Field(default=10, ge=1, le=60, description="Minutes threshold for stuck downloads")


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
    session: Session = Depends(get_db_session)
):
    """Test yt-dlp availability"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Testing yt-dlp connection for user {current_user.get('username')}")
        
        result = ytdlp_service.health_check()
        
        if result["status"] != "healthy":
            raise HTTPException(status_code=503, detail=result)
        
        return HealthResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"yt-dlp health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "error": str(e)}
        )


@router.get("/queue", response_model=QueueResponse)
async def get_download_queue(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Get current download queue"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Getting download queue for user {current_user.get('username')}")
        
        result = ytdlp_service.get_queue()
        
        return QueueResponse(
            queue=result.get("queue", []),
            total=result.get("total", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to get download queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=HistoryResponse)
async def get_download_history(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum number of history items"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Get download history"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Getting download history (limit={limit}) for user {current_user.get('username')}")
        
        result = ytdlp_service.get_history(limit=limit)
        
        return HistoryResponse(
            history=result.get("history", []),
            total=result.get("total", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to get download history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/music-video", response_model=DownloadResponse)
async def add_music_video_download(
    download_request: MusicVideoDownloadRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Add a music video download with MVidarr formatting"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Adding music video download '{download_request.artist} - {download_request.title}' for user {current_user.get('username')}")
        
        # Read subtitle language settings if not provided in request
        subtitle_languages = download_request.subtitle_languages
        if not subtitle_languages:
            from src.services.settings_service import settings
            subtitle_languages = settings.get("subtitle_languages", "en,en-US")
        
        result = ytdlp_service.add_music_video_download(
            artist=download_request.artist,
            title=download_request.title,
            url=download_request.url,
            quality=download_request.quality,
            video_id=download_request.video_id,
            download_subtitles=download_request.download_subtitles,
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
    download_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Stop a specific download"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Stopping download {download_id} for user {current_user.get('username')}")
        
        result = ytdlp_service.stop_download(download_id)
        
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
    download_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Retry a failed download"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Retrying download {download_id} for user {current_user.get('username')}")
        
        result = ytdlp_service.retry_download(download_id)
        
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
    session: Session = Depends(get_db_session)
):
    """Clear download history"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Clearing download history for user {current_user.get('username')}")
        
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
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Clear downloads stuck at 0% progress"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Clearing stuck downloads (minutes={clear_request.minutes}) for user {current_user.get('username')}")
        
        result = ytdlp_service.clear_stuck_downloads(minutes=clear_request.minutes)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)
        
        return DownloadResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear stuck downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
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
            status_code=503,
            detail={"status": "unhealthy", "error": str(e)}
        )


# ========================================================================================
# COOKIE MANAGEMENT ENDPOINTS
# ========================================================================================


@router.post("/cookies/upload", response_model=CookieUploadResponse)
async def upload_cookies(
    file: UploadFile = File(..., description="YouTube cookies file (.txt or .cookies)"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
):
    """Upload YouTube cookies file for age-restricted video downloads"""
    try:
        user_id = current_user.get("user_id", 1)
        
        logger.info(f"Uploading cookies file '{file.filename}' for user {current_user.get('username')}")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")
        
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail="File type not allowed. Please upload a .txt or .cookies file"
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
                    raise HTTPException(
                        status_code=400,
                        detail="Cookie file is empty"
                    )
                
                # Basic validation - check if it looks like cookies
                if not (
                    "youtube.com" in content_str.lower()
                    or "session_token" in content_str.lower()
                    or "\t" in content_str
                ):
                    os.remove(cookie_path)
                    raise HTTPException(
                        status_code=400,
                        detail="File does not appear to contain valid cookies"
                    )
                    
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(cookie_path):
                os.remove(cookie_path)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to validate cookie file: {e}"
            )
        
        # Update ytdlp service to use the uploaded cookies
        ytdlp_service.set_cookie_file(cookie_path)
        
        logger.info(f"Cookies uploaded successfully: {file.filename}")
        
        return CookieUploadResponse(
            success=True,
            message="Cookies uploaded successfully",
            filename=cookie_filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cookies/status", response_model=CookieStatusResponse)
async def cookies_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
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
                path=cookie_path
            )
        else:
            return CookieStatusResponse(
                success=True,
                cookies_available=False,
                message="No cookies file uploaded"
            )
        
    except Exception as e:
        logger.error(f"Failed to check cookie status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cookies/delete", response_model=CookieUploadResponse)
async def delete_cookies(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session)
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
                success=True,
                message="Cookies deleted successfully"
            )
        else:
            return CookieUploadResponse(
                success=True,
                message="No cookies file to delete"
            )
        
    except Exception as e:
        logger.error(f"Failed to delete cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))