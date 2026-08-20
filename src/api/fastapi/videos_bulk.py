"""
FastAPI Videos Bulk Operations API Module

This module contains bulk management operations for videos.
These endpoints handle batch video operations:
- Bulk delete videos
- Bulk status updates (with debug variant)
- Bulk edit/update video metadata
- Bulk organize video files into directory structure

Extracted from videos.py as part of the API modularization effort.
Uses Pydantic models from videos_models.py for request/response validation.

Authentication: All endpoints require session-based authentication via the require_authentication dependency.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from src.api.fastapi.auth_dependencies import require_authentication
from src.api.fastapi.videos_models import (
    BulkDeleteRequest,
    BulkEditRequest,
    BulkOrganizeRequest,
)
from src.database.connection import get_db_session
from src.database.models import Video, VideoStatus
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger("mvidarr.api.fastapi.videos_bulk")
# ========================================================================================
# BULK OPERATIONS
# ========================================================================================


@router.post("/bulk/delete")
async def bulk_delete_videos(
    request: BulkDeleteRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk delete videos"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to delete
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        deleted_count = 0
        errors = []

        for video in videos:
            try:
                video_id = video.id  # Store ID before delete operation
                # Delete associated files if they exist
                if (
                    getattr(video, "file_path", video.local_path)
                    and Path(getattr(video, "file_path", video.local_path)).exists()
                ):
                    Path(getattr(video, "file_path", video.local_path)).unlink()

                session.delete(video)
                deleted_count += 1

            except Exception as e:
                video_id = getattr(video, "id", "unknown")  # Safe ID retrieval
                errors.append(f"Video {video_id}: {str(e)}")
                logger.error(f"Error deleting video {video_id}: {e}")

        session.commit()

        logger.info(f"Bulk deleted {deleted_count} videos")

        result = {
            "message": f"Bulk delete completed",
            "deleted_count": deleted_count,
            "total_requested": len(request.video_ids),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/status")
async def bulk_update_status(
    request: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk update video status"""
    try:
        logger.info(f"Raw bulk status update request: {request}")

        # Manual validation with better error messages
        if "video_ids" not in request or not request["video_ids"]:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        if "status" not in request:
            raise HTTPException(status_code=400, detail="Status is required")

        # Validate video_ids are integers
        try:
            video_ids = [int(vid) for vid in request["video_ids"]]
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid video ID format: {e}")

        # Validate status value
        status_str = request["status"]
        try:
            status = VideoStatus(status_str)
        except ValueError:
            valid_statuses = [s.value for s in VideoStatus]
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status_str}'. Valid statuses: {valid_statuses}",
            )

        logger.info(
            f"Validated bulk status update: video_ids={video_ids}, status={status}"
        )

        if not video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Update video statuses
        updated_count = (
            session.query(Video)
            .filter(Video.id.in_(video_ids))
            .update(
                {Video.status: status, Video.updated_at: datetime.utcnow()},
                synchronize_session=False,
            )
        )

        session.commit()

        logger.info(f"Bulk updated {updated_count} video statuses to {status}")

        return {
            "success": True,
            "message": f"Bulk status update completed",
            "updated_count": updated_count,
            "new_status": status.value,
            "total_requested": len(video_ids),
        }

    except Exception as e:
        logger.error(f"Error in bulk status update: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/status-debug")
async def bulk_update_status_debug(
    request: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Working bulk status update bypassing validation issues"""
    try:
        logger.info(f"DEBUG: Raw request received: {request}")

        # Validate and extract data manually
        if "video_ids" not in request or not request["video_ids"]:
            return {"success": False, "error": "No video IDs provided"}

        if "status" not in request:
            return {"success": False, "error": "Status is required"}

        # Convert video_ids to integers
        try:
            video_ids = [int(vid) for vid in request["video_ids"]]
        except (ValueError, TypeError) as e:
            return {"success": False, "error": f"Invalid video ID format: {e}"}

        # Validate status value
        status_str = request["status"]
        valid_statuses = [
            "WANTED",
            "DOWNLOADING",
            "DOWNLOADED",
            "IGNORED",
            "FAILED",
            "MONITORED",
        ]
        if status_str not in valid_statuses:
            return {
                "success": False,
                "error": f"Invalid status '{status_str}'. Valid: {valid_statuses}",
            }

        # Convert string to VideoStatus enum
        status = VideoStatus(status_str)

        logger.info(f"DEBUG: Validated - video_ids={video_ids}, status={status}")

        # Perform the actual status update
        updated_count = (
            session.query(Video)
            .filter(Video.id.in_(video_ids))
            .update(
                {Video.status: status, Video.updated_at: datetime.utcnow()},
                synchronize_session=False,
            )
        )

        session.commit()

        logger.info(
            f"DEBUG: Successfully updated {updated_count} video statuses to {status}"
        )

        return {
            "success": True,
            "message": f"Successfully updated {updated_count} videos to {status_str}",
            "updated_count": updated_count,
            "new_status": status_str,
            "total_requested": len(video_ids),
        }

    except Exception as e:
        logger.error(f"Error in debug bulk status update: {e}")
        session.rollback()
        return {"success": False, "error": str(e), "error_type": type(e).__name__}


@router.post("/bulk/edit")
async def bulk_edit_videos(
    request: BulkEditRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk edit videos with specified updates"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to edit
        videos = session.query(Video).filter(Video.id.in_(request.video_ids)).all()

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        # Build update dictionary from request (excluding video_ids and None values)
        update_fields = request.dict(
            exclude={"video_ids"}, exclude_unset=True, exclude_none=True
        )

        if not update_fields:
            return {
                "message": "No fields provided for update",
                "updated_count": 0,
                "total_requested": len(request.video_ids),
            }

        # Handle special field processing
        if "genres" in update_fields and update_fields["genres"]:
            # Convert genres list to JSON string for database storage
            update_fields["genres"] = json.dumps(update_fields["genres"])

        # Add updated timestamp
        update_fields["updated_at"] = datetime.utcnow()

        updated_count = 0
        errors = []

        for video in videos:
            try:
                video_id = video.id  # Store ID before any operations
                # Apply updates to each video
                for field, value in update_fields.items():
                    if hasattr(video, field):
                        setattr(video, field, value)

                updated_count += 1

            except Exception as e:
                video_id = getattr(video, "id", "unknown")  # Safe ID retrieval
                errors.append(f"Video {video_id}: {str(e)}")
                logger.error(f"Error updating video {video_id}: {e}")

        session.commit()

        logger.info(
            f"Bulk updated {updated_count} videos with fields: {list(update_fields.keys())}"
        )

        result = {
            "message": "Bulk edit completed",
            "updated_count": updated_count,
            "total_requested": len(request.video_ids),
            "updated_fields": list(update_fields.keys()),
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk edit: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/organize")
async def bulk_organize_videos(
    request: BulkOrganizeRequest = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Bulk organize video files into proper directory structure"""
    try:
        if not request.video_ids:
            raise HTTPException(status_code=400, detail="No video IDs provided")

        # Get videos to organize with artist information
        videos = (
            session.query(Video)
            .options(joinedload(Video.artist))
            .filter(Video.id.in_(request.video_ids))
            .all()
        )

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found")

        # Determine base directory for organization
        base_directory = request.target_directory or "/data/musicvideos"
        base_path = Path(base_directory)

        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Cannot create target directory: {e}"
                )

        organized_count = 0
        errors = []
        moves = []

        def sanitize_filename(name: str) -> str:
            """Sanitize filename/directory name for filesystem compatibility"""
            # Replace problematic characters
            sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
            # Remove leading/trailing dots and spaces
            sanitized = sanitized.strip(". ")
            return sanitized or "Unknown"

        for video in videos:
            try:
                # Get current file path
                current_path = getattr(video, "file_path", video.local_path)
                if not current_path or not Path(current_path).exists():
                    errors.append(f"Video {video.id}: File not found at {current_path}")
                    continue

                current_file = Path(current_path)

                # Determine artist folder name
                if video.artist and video.artist.name:
                    artist_folder = sanitize_filename(video.artist.name)
                else:
                    artist_folder = "Unknown Artist"

                # Create target directory structure
                if request.create_artist_folders:
                    target_dir = base_path / artist_folder
                else:
                    target_dir = base_path

                target_dir.mkdir(parents=True, exist_ok=True)

                # Determine target file path
                target_file = target_dir / current_file.name

                # Handle file name conflicts
                counter = 1
                original_target = target_file
                while target_file.exists() and target_file != current_file:
                    stem = original_target.stem
                    suffix = original_target.suffix
                    target_file = target_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                # Only move if source and target are different
                if current_file.resolve() != target_file.resolve():
                    # Move the file
                    shutil.move(str(current_file), str(target_file))

                    # Update database if requested
                    if request.update_database_paths:
                        if hasattr(video, "file_path"):
                            video.file_path = str(target_file)
                        else:
                            video.local_path = str(target_file)
                        video.updated_at = datetime.utcnow()

                    moves.append(
                        {
                            "video_id": video.id,
                            "from": str(current_file),
                            "to": str(target_file),
                        }
                    )

                organized_count += 1

            except Exception as e:
                errors.append(f"Video {video.id}: {str(e)}")
                logger.error(f"Error organizing video {video.id}: {e}")

        # Commit database changes if requested
        if request.update_database_paths:
            session.commit()

        logger.info(f"Bulk organized {organized_count} videos into {base_directory}")

        result = {
            "message": "Bulk organization completed",
            "organized_count": organized_count,
            "total_requested": len(request.video_ids),
            "target_directory": str(base_path),
            "moves": moves,
        }

        if errors:
            result["errors"] = errors

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk organize: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh-thumbnails")
async def refresh_video_thumbnails(
    body: Optional[dict] = Body(None),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Refresh thumbnails for videos by downloading from source URLs with progress tracking"""
    try:
        video_ids = None
        if body and "video_ids" in body:
            video_ids = body["video_ids"]

        if video_ids is None:
            # Refresh all videos that don't have local thumbnails
            videos = (
                session.query(Video)
                .filter(
                    or_(
                        Video.thumbnail_path.is_(None),
                        Video.thumbnail_path == "",
                        and_(
                            Video.thumbnail_url.isnot(None),
                            Video.thumbnail_url != "",
                            Video.thumbnail_path.is_(None),
                        ),
                    )
                )
                .all()
            )
        else:
            # Refresh specific videos
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()

        if not videos:
            return {
                "message": "No videos found for thumbnail refresh",
                "total_videos": 0,
                "job_id": None,
            }

        # Separate videos into those with thumbnail URLs vs those needing FFmpeg
        url_videos = []
        ffmpeg_videos = []
        video_paths = []

        for video in videos:
            if video.thumbnail_url and video.thumbnail_url.strip():
                # Has source thumbnail URL - prioritize downloading from source
                url_videos.append(video)
            elif video.local_path and Path(video.local_path).exists():
                # No thumbnail URL but has local file - use FFmpeg as fallback
                ffmpeg_videos.append(video)
                video_paths.append(str(video.local_path))

        total_processable = len(url_videos) + len(ffmpeg_videos)

        if total_processable == 0:
            return {
                "message": "No videos found with thumbnail URLs or local files",
                "total_videos": len(videos),
                "valid_videos": 0,  # Frontend expects this field name
                "url_videos": 0,
                "ffmpeg_videos": 0,
                "job_id": None,
            }

        logger.info(
            f"Starting thumbnail refresh: {len(url_videos)} from URLs, {len(ffmpeg_videos)} from FFmpeg"
        )

        # Submit background job for mixed thumbnail processing
        from src.jobs.metadata_tasks import submit_bulk_thumbnail_url_download_task

        job_id = submit_bulk_thumbnail_url_download_task(
            url_video_ids=[v.id for v in url_videos],
            ffmpeg_video_paths=video_paths,
            priority="normal",
            user_id=current_user.get("user_id", "anonymous"),
        )

        return {
            "message": f"Thumbnail refresh job started for {total_processable} videos ({len(url_videos)} from URLs, {len(ffmpeg_videos)} from FFmpeg)",
            "total_videos": len(videos),
            "valid_videos": total_processable,  # Frontend expects this field name
            "url_videos": len(url_videos),
            "ffmpeg_videos": len(ffmpeg_videos),
            "job_id": job_id,
            "status": "started",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/refresh-all-thumbnails")
async def bulk_refresh_all_thumbnails(
    request: dict = Body(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Refresh thumbnails for all videos of an artist"""
    try:
        artist_id = request.get("artist_id")
        if not artist_id:
            raise HTTPException(status_code=400, detail="artist_id is required")

        # Get all videos for the artist
        videos = session.query(Video).filter(Video.artist_id == artist_id).all()

        if not videos:
            return {
                "success": True,
                "message": "No videos found for this artist",
                "artist_id": artist_id,
                "videos_processed": 0,
                "thumbnails_updated": 0,
            }

        logger.info(
            f"Starting bulk thumbnail refresh for {len(videos)} videos of artist {artist_id}"
        )

        # Use the real metadata enrichment service
        from src.services.metadata_enrichment_service import MetadataEnrichmentService

        enrichment_service = MetadataEnrichmentService()

        videos_processed = 0
        thumbnails_updated = 0
        errors = []

        for video in videos:
            try:
                # Call video metadata enrichment with force refresh to update thumbnails
                enrichment_result = await enrichment_service.enrich_video_metadata(
                    video.id, force_refresh=True
                )

                videos_processed += 1

                if enrichment_result.success and enrichment_result.enriched_fields:
                    if "thumbnail_url" in enrichment_result.enriched_fields:
                        thumbnails_updated += 1
                        logger.info(
                            f"Updated thumbnail for video {video.id}: {video.title}"
                        )

            except Exception as e:
                errors.append(f"Video {video.id} ({video.title}): {str(e)}")
                logger.error(f"Error refreshing thumbnail for video {video.id}: {e}")

        session.commit()

        result = {
            "success": True,
            "message": f"Processed {videos_processed} videos, updated {thumbnails_updated} thumbnails",
            "artist_id": artist_id,
            "videos_processed": videos_processed,
            "thumbnails_updated": thumbnails_updated,
        }

        if errors:
            result["errors"] = errors

        logger.info(
            f"Bulk thumbnail refresh complete: {videos_processed} processed, {thumbnails_updated} updated"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk refresh all thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
