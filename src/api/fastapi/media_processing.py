"""
FastAPI media processing endpoints

Provides async REST API endpoints for video processing operations using
background jobs with real-time progress tracking via WebSocket.
"""

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.jobs.ffmpeg_processing_tasks import (
    submit_bulk_metadata_task,
    submit_metadata_extraction_task,
    submit_video_conversion_task,
    submit_video_validation_task,
)
from src.jobs.redis_manager import redis_manager
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.fastapi.media_processing")

router = APIRouter(prefix="/api/media", tags=["media_processing"])


# Pydantic models for request/response validation
class VideoMetadataExtractionRequest(BaseModel):
    """Request model for video metadata extraction"""

    video_path: str = Field(..., description="Path to video file")
    priority: str = Field("normal", description="Task priority (low, normal, high)")


class VideoMetadataResponse(BaseModel):
    """Response model for video metadata"""

    success: bool
    metadata: Optional[Dict] = None
    video_path: str
    video_name: str
    file_size: Optional[int] = None
    error: Optional[str] = None


class VideoConversionRequest(BaseModel):
    """Request model for video format conversion"""

    input_path: str = Field(..., description="Input video file path")
    output_path: str = Field(..., description="Output video file path")
    format_options: Dict = Field(..., description="FFmpeg conversion options")
    priority: str = Field("normal", description="Task priority (low, normal, high)")


class VideoConversionResponse(BaseModel):
    """Response model for video conversion"""

    success: bool
    input_path: str
    output_path: str
    output_size: Optional[int] = None
    format_options: Dict
    error: Optional[str] = None


class BulkMetadataRequest(BaseModel):
    """Request model for bulk metadata extraction"""

    video_paths: List[str] = Field(..., description="List of video file paths")
    batch_size: int = Field(10, description="Number of files to process concurrently")
    priority: str = Field("low", description="Task priority (low, normal, high)")


class BulkMetadataResponse(BaseModel):
    """Response model for bulk metadata extraction"""

    success: bool
    total_files: int
    processed_files: int
    successful_extractions: int
    failed_extractions: int
    results: List[Dict]
    error: Optional[str] = None


class VideoValidationRequest(BaseModel):
    """Request model for video validation"""

    video_path: str = Field(..., description="Path to video file to validate")
    priority: str = Field("normal", description="Task priority (low, normal, high)")


class VideoValidationResponse(BaseModel):
    """Response model for video validation"""

    success: bool
    valid: bool
    validation_score: Optional[float] = None
    validation_results: Optional[Dict] = None
    metadata: Optional[Dict] = None
    video_path: str
    video_name: str
    file_size: Optional[int] = None
    error: Optional[str] = None


class TaskSubmissionResponse(BaseModel):
    """Response model for task submission"""

    success: bool
    task_id: str
    message: str
    websocket_url: Optional[str] = None


class TaskCancellationResponse(BaseModel):
    """Response model for task cancellation"""

    success: bool
    message: str
    task_id: str


# API Endpoints


@router.post(
    "/metadata/extract",
    response_model=TaskSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extract video metadata",
    description="Submit a background job to extract technical metadata from a video file",
)
async def extract_video_metadata(
    request: VideoMetadataExtractionRequest,
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
):
    """
    Extract technical metadata from video file using FFprobe

    Returns a task ID that can be used to track progress via WebSocket
    or the jobs API endpoints.
    """
    try:
        # Validate video file exists
        video_path = Path(request.video_path)
        if not video_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video file not found: {request.video_path}",
            )

        # Submit background task
        task_id = await submit_metadata_extraction_task(
            video_path=request.video_path, priority=request.priority, user_id=user_id
        )

        logger.info(
            f"Metadata extraction task submitted: {task_id} for {video_path.name}"
        )

        return TaskSubmissionResponse(
            success=True,
            task_id=task_id,
            message=f"Metadata extraction started for {video_path.name}",
            websocket_url=f"/ws/jobs/{task_id}",
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error"
        )
    except Exception as e:
        logger.error(f"Error submitting metadata extraction task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit metadata extraction task: {e}",
        )


@router.post(
    "/video/convert",
    response_model=TaskSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Convert video format",
    description="Submit a background job to convert video to different format",
)
async def convert_video_format(
    request: VideoConversionRequest,
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
):
    """
    Convert video file to different format using FFmpeg

    Returns a task ID that can be used to track progress via WebSocket
    or the jobs API endpoints.
    """
    try:
        # Validate input file exists
        input_path = Path(request.input_path)
        if not input_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Input video file not found: {request.input_path}",
            )

        # Validate output directory exists or can be created
        output_path = Path(request.output_path)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create output directory: {e}",
            )

        # Submit background task
        task_id = await submit_video_conversion_task(
            input_path=request.input_path,
            output_path=request.output_path,
            format_options=request.format_options,
            priority=request.priority,
            user_id=user_id,
        )

        logger.info(f"Video conversion task submitted: {task_id} for {input_path.name}")

        return TaskSubmissionResponse(
            success=True,
            task_id=task_id,
            message=f"Video conversion started: {input_path.name} -> {output_path.name}",
            websocket_url=f"/ws/jobs/{task_id}",
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error"
        )
    except Exception as e:
        logger.error(f"Error submitting video conversion task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit video conversion task: {e}",
        )


@router.post(
    "/metadata/bulk",
    response_model=TaskSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk metadata extraction",
    description="Submit a background job to extract metadata from multiple video files",
)
async def bulk_extract_metadata(
    request: BulkMetadataRequest,
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
):
    """
    Extract metadata from multiple video files concurrently

    Returns a task ID that can be used to track progress via WebSocket
    or the jobs API endpoints.
    """
    try:
        # Validate at least one video path provided
        if not request.video_paths:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one video path must be provided",
            )

        # Validate batch size
        if request.batch_size < 1 or request.batch_size > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size must be between 1 and 50",
            )

        # Check that at least some files exist
        existing_files = [path for path in request.video_paths if Path(path).exists()]

        if not existing_files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No video files found at the provided paths",
            )

        # Submit background task
        task_id = await submit_bulk_metadata_task(
            video_paths=request.video_paths,
            batch_size=request.batch_size,
            priority=request.priority,
            user_id=user_id,
        )

        logger.info(
            f"Bulk metadata extraction task submitted: {task_id} for {len(request.video_paths)} files"
        )

        return TaskSubmissionResponse(
            success=True,
            task_id=task_id,
            message=f"Bulk metadata extraction started for {len(request.video_paths)} videos",
            websocket_url=f"/ws/jobs/{task_id}",
        )

    except Exception as e:
        logger.error(f"Error submitting bulk metadata extraction task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit bulk metadata extraction task: {e}",
        )


@router.post(
    "/video/validate",
    response_model=TaskSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Validate video file",
    description="Submit a background job to validate video file integrity",
)
async def validate_video_file(
    request: VideoValidationRequest,
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
):
    """
    Validate video file integrity and playability

    Returns a task ID that can be used to track progress via WebSocket
    or the jobs API endpoints.
    """
    try:
        # Validate video file exists
        video_path = Path(request.video_path)
        if not video_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video file not found: {request.video_path}",
            )

        # Submit background task
        task_id = await submit_video_validation_task(
            video_path=request.video_path, priority=request.priority, user_id=user_id
        )

        logger.info(f"Video validation task submitted: {task_id} for {video_path.name}")

        return TaskSubmissionResponse(
            success=True,
            task_id=task_id,
            message=f"Video validation started for {video_path.name}",
            websocket_url=f"/ws/jobs/{task_id}",
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error"
        )
    except Exception as e:
        logger.error(f"Error submitting video validation task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit video validation task: {e}",
        )


@router.delete(
    "/processing/cancel/{task_id}",
    response_model=TaskCancellationResponse,
    summary="Cancel media processing task",
    description="Cancel an active FFmpeg processing operation",
)
async def cancel_media_processing(task_id: str):
    """
    Cancel an active FFmpeg processing operation

    This will attempt to terminate the FFmpeg subprocess gracefully,
    and force kill it if necessary.
    """
    try:
        # Attempt to cancel the FFmpeg operation
        success = await ffmpeg_stream_manager.cancel_operation(task_id)

        if success:
            logger.info(f"Successfully cancelled media processing task: {task_id}")
            return TaskCancellationResponse(
                success=True,
                message=f"Media processing task {task_id} cancelled successfully",
                task_id=task_id,
            )
        else:
            logger.warning(
                f"Could not cancel media processing task: {task_id} (may not be active)"
            )
            return TaskCancellationResponse(
                success=False,
                message=f"Could not cancel task {task_id} (may not be active or already completed)",
                task_id=task_id,
            )

    except Exception as e:
        logger.error(f"Error cancelling media processing task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel media processing task: {e}",
        )


@router.get(
    "/processing/active",
    summary="Get active media processing operations",
    description="Get list of currently active FFmpeg processing operations",
)
async def get_active_processing():
    """
    Get list of currently active FFmpeg processing operations

    Returns information about active FFmpeg subprocesses and their job IDs.
    """
    try:
        active_processes = ffmpeg_stream_manager.active_processes

        active_operations = []
        for job_id, process in active_processes.items():
            # Get job progress information
            try:
                progress_data = await redis_manager.get_json(f"job_progress:{job_id}")

                active_operations.append(
                    {
                        "job_id": job_id,
                        "process_id": process.pid,
                        "status": "running",
                        "progress": (
                            progress_data.get("progress", 0) if progress_data else 0
                        ),
                        "stage": (
                            progress_data.get("stage", "unknown")
                            if progress_data
                            else "unknown"
                        ),
                        "message": (
                            progress_data.get("message", "Processing")
                            if progress_data
                            else "Processing"
                        ),
                    }
                )
            except Exception as e:
                logger.warning(f"Could not get progress for job {job_id}: {e}")
                active_operations.append(
                    {
                        "job_id": job_id,
                        "process_id": process.pid,
                        "status": "running",
                        "progress": 0,
                        "stage": "unknown",
                        "message": "Processing",
                    }
                )

        return {
            "success": True,
            "active_operations": active_operations,
            "total_active": len(active_operations),
        }

    except Exception as e:
        logger.error(f"Error getting active processing operations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active processing operations: {e}",
        )


@router.get(
    "/formats/conversion-options",
    summary="Get available conversion options",
    description="Get common FFmpeg format conversion options and presets",
)
async def get_conversion_options():
    """
    Get available FFmpeg conversion options and presets

    Returns common format conversion options that can be used with the
    video conversion endpoint.
    """
    return {
        "success": True,
        "presets": {
            "mp4_web": {
                "description": "MP4 optimized for web streaming",
                "options": {
                    "-c:v": "libx264",
                    "-preset": "medium",
                    "-crf": "23",
                    "-c:a": "aac",
                    "-b:a": "128k",
                    "-f": "mp4",
                },
            },
            "mp4_mobile": {
                "description": "MP4 optimized for mobile devices",
                "options": {
                    "-c:v": "libx264",
                    "-preset": "fast",
                    "-crf": "28",
                    "-maxrate": "1M",
                    "-bufsize": "2M",
                    "-c:a": "aac",
                    "-b:a": "96k",
                    "-f": "mp4",
                },
            },
            "webm_web": {
                "description": "WebM optimized for web streaming",
                "options": {
                    "-c:v": "libvpx-vp9",
                    "-crf": "30",
                    "-b:v": "0",
                    "-c:a": "libopus",
                    "-b:a": "128k",
                    "-f": "webm",
                },
            },
            "thumbnail": {
                "description": "Extract thumbnail image",
                "options": {
                    "-vf": "thumbnail,scale=320:240",
                    "-frames:v": "1",
                    "-f": "image2",
                },
            },
            "audio_only": {
                "description": "Extract audio only",
                "options": {"-vn": "", "-c:a": "mp3", "-b:a": "192k", "-f": "mp3"},
            },
        },
        "common_options": {
            "video_codecs": ["libx264", "libx265", "libvpx", "libvpx-vp9"],
            "audio_codecs": ["aac", "mp3", "libopus", "libvorbis"],
            "formats": ["mp4", "webm", "mkv", "avi", "mov"],
            "presets": [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ],
            "quality_options": ["crf", "qp", "bitrate"],
        },
    }
