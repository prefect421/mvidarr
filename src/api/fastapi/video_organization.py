"""
FastAPI Video Organization Router
Migrated from Flask src/api/video_organization.py - Video organization endpoints
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.services.job_queue import (
    BackgroundJob,
    JobPriority,
    JobType,
    get_job_queue,
)
from src.services.video_organization_service import video_organizer
from src.utils.filename_cleanup import FilenameCleanup

logger = logging.getLogger("mvidarr.fastapi.video_organization")

router = APIRouter(
    prefix="/api/video-organization",
    tags=["video-organization"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class JobResponse(BaseModel):
    """Background job response"""

    success: bool
    job_id: str
    message: str


class ArtistDirectory(BaseModel):
    """Artist directory information"""

    name: str
    video_count: int
    path: str


class ArtistDirectoriesResponse(BaseModel):
    """Artist directories response"""

    artists: List[ArtistDirectory]
    count: int
    total_videos: int


class FileListResponse(BaseModel):
    """File list response"""

    files: List[str]
    count: int


class OrganizationPreview(BaseModel):
    """Organization preview response"""

    original_filename: str
    cleaned_filename: str
    artist: Optional[str] = None
    title: Optional[str] = None
    can_organize: bool
    artist_folder: Optional[str] = None
    final_filename: Optional[str] = None
    target_path: Optional[str] = None


class CleanupResponse(BaseModel):
    """Directory cleanup response"""

    success: bool
    message: str
    removed_count: int


class ExistingVideosResponse(BaseModel):
    """Existing videos scan response"""

    files: List[str]
    count: int
    music_videos_path: str


class OrganizationStatus(BaseModel):
    """Organization status response"""

    downloads_path: str
    music_videos_path: str
    pending_downloads: int
    existing_videos: int
    artist_count: int
    total_organized_videos: int
    directories_exist: bool


# ========================================================================================
# VIDEO ORGANIZATION BACKGROUND JOBS
# ========================================================================================


@router.post("/organize-all", response_model=JobResponse)
async def organize_all_videos(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Organize all videos in downloads directory (background job)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Queueing organize all videos job for user {current_user.get('username')}"
        )

        # Create background job for organizing all videos
        job = BackgroundJob(
            type=JobType.VIDEO_ORGANIZE_ALL,
            priority=JobPriority.NORMAL,
            payload={},  # No specific payload needed for organize all
            created_by=user_id,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(f"Enqueued organize all videos job {job_id}")

        return JobResponse(
            success=True,
            job_id=job_id,
            message="Video organization job queued for all downloads",
        )

    except Exception as e:
        logger.error(f"Failed to queue organize all videos job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/organize/{filename}", response_model=JobResponse)
async def organize_single_video(
    filename: str = PathParam(..., description="Filename to organize"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Organize a specific video file (background job)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Queueing organize single video job for '{filename}' for user {current_user.get('username')}"
        )

        # Create background job for organizing single video
        job = BackgroundJob(
            type=JobType.VIDEO_ORGANIZE_SINGLE,
            priority=JobPriority.HIGH,  # Single video organization is higher priority
            payload={"filename": filename},
            created_by=user_id,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(f"Enqueued organize single video job {job_id} for {filename}")

        return JobResponse(
            success=True,
            job_id=job_id,
            message=f"Video organization job queued for {filename}",
        )

    except Exception as e:
        logger.error(f"Failed to queue organize video job for {filename}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reorganize-existing", response_model=JobResponse)
async def reorganize_existing_videos(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Reorganize existing videos in the music videos directory (background job)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Queueing reorganize existing videos job for user {current_user.get('username')}"
        )

        # Create background job for reorganizing existing videos
        job = BackgroundJob(
            type=JobType.VIDEO_REORGANIZE_EXISTING,
            priority=JobPriority.NORMAL,
            payload={},  # No specific payload needed for reorganize existing
            created_by=user_id,
        )

        # Enqueue job
        job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)

        logger.info(f"Enqueued reorganize existing videos job {job_id}")

        return JobResponse(
            success=True,
            job_id=job_id,
            message="Video reorganization job queued for existing videos",
        )

    except Exception as e:
        logger.error(f"Failed to queue reorganize existing videos job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# VIDEO ORGANIZATION INFORMATION ENDPOINTS
# ========================================================================================


@router.get("/artists", response_model=ArtistDirectoriesResponse)
async def get_artist_directories(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get list of artist directories and video counts"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting artist directories for user {current_user.get('username')}"
        )

        artists = video_organizer.get_artist_directories()

        artist_dirs = [
            ArtistDirectory(
                name=artist["name"],
                video_count=artist["video_count"],
                path=artist["path"],
            )
            for artist in artists
        ]

        return ArtistDirectoriesResponse(
            artists=artist_dirs,
            count=len(artist_dirs),
            total_videos=sum(artist.video_count for artist in artist_dirs),
        )

    except Exception as e:
        logger.error(f"Failed to get artist directories: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/downloads/scan", response_model=FileListResponse)
async def scan_downloads(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Scan downloads directory for video files"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Scanning downloads directory for user {current_user.get('username')}"
        )

        video_files = video_organizer.scan_downloads_directory()

        # Convert Path objects to strings
        file_list = [str(f.name) for f in video_files]

        return FileListResponse(files=file_list, count=len(file_list))

    except Exception as e:
        logger.error(f"Failed to scan downloads directory: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/existing/scan", response_model=ExistingVideosResponse)
async def scan_existing_videos(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Scan existing music videos directory for video files"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Scanning existing videos for user {current_user.get('username')}")

        video_files = video_organizer.scan_existing_music_videos()

        # Convert Path objects to strings and get relative paths
        file_list = []
        music_videos_path = video_organizer.get_music_videos_path()

        for f in video_files:
            try:
                # Get relative path from music videos directory
                relative_path = f.relative_to(music_videos_path)
                file_list.append(str(relative_path))
            except ValueError:
                # If file is not under music videos directory, use full path
                file_list.append(str(f))

        return ExistingVideosResponse(
            files=file_list,
            count=len(file_list),
            music_videos_path=str(music_videos_path),
        )

    except Exception as e:
        logger.error(f"Failed to scan existing videos: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/preview/{filename}", response_model=OrganizationPreview)
async def preview_organization(
    filename: str = PathParam(..., description="Filename to preview organization for"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Preview how a file would be organized without actually moving it"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Previewing organization for '{filename}' for user {current_user.get('username')}"
        )

        # Clean the filename
        cleaned_filename = FilenameCleanup.clean_filename(filename)

        # Extract artist and title
        artist, title = FilenameCleanup.extract_artist_and_title(cleaned_filename)

        preview = OrganizationPreview(
            original_filename=filename,
            cleaned_filename=cleaned_filename,
            artist=artist,
            title=title,
            can_organize=bool(artist and title),
        )

        if artist and title:
            # Generate the target path
            music_videos_dir = video_organizer.get_music_videos_path()
            artist_folder = FilenameCleanup.sanitize_folder_name(artist)
            final_filename = FilenameCleanup.generate_clean_filename(
                artist, title, Path(filename).suffix
            )

            preview.artist_folder = artist_folder
            preview.final_filename = final_filename
            preview.target_path = str(music_videos_dir / artist_folder / final_filename)

        return preview

    except Exception as e:
        logger.error(f"Failed to preview organization for {filename}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# VIDEO ORGANIZATION MAINTENANCE ENDPOINTS
# ========================================================================================


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_empty_directories(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Remove empty artist directories"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Cleaning up empty directories for user {current_user.get('username')}"
        )

        removed_count = video_organizer.cleanup_empty_directories()

        return CleanupResponse(
            success=True,
            message=f"Removed {removed_count} empty directories",
            removed_count=removed_count,
        )

    except Exception as e:
        logger.error(f"Failed to cleanup directories: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status", response_model=OrganizationStatus)
async def get_organization_status(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get current organization status and statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting organization status for user {current_user.get('username')}"
        )

        # Scan downloads
        downloads = video_organizer.scan_downloads_directory()

        # Scan existing videos
        existing_videos = video_organizer.scan_existing_music_videos()

        # Get artists
        artists = video_organizer.get_artist_directories()

        # Ensure directories exist
        video_organizer.ensure_directories_exist()

        status = OrganizationStatus(
            downloads_path=str(video_organizer.get_downloads_path()),
            music_videos_path=str(video_organizer.get_music_videos_path()),
            pending_downloads=len(downloads),
            existing_videos=len(existing_videos),
            artist_count=len(artists),
            total_organized_videos=sum(artist["video_count"] for artist in artists),
            directories_exist=True,
        )

        return status

    except Exception as e:
        logger.error(f"Failed to get organization status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
