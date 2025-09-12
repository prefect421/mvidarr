"""
FastAPI Jobs API Router
Native asyncio support for background job management
"""

import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from src.services.job_queue import JobType, JobPriority, BackgroundJob, get_job_queue
from src.services.fastapi_job_integration import (
    get_fastapi_job_system_status, 
    get_fastapi_job_system_health, 
    is_fastapi_job_system_enabled,
    get_fastapi_job_queue
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.fastapi.jobs")

router = APIRouter(prefix="/api/jobs", tags=["Background Jobs"])


# Pydantic models for request/response
class JobCreateRequest(BaseModel):
    type: str = Field(..., description="Job type")
    priority: str = Field(default="normal", description="Job priority (low, normal, high, urgent)")
    payload: dict = Field(..., description="Job payload data")
    max_retries: Optional[int] = Field(default=3, ge=0, le=10)
    retry_delay: Optional[int] = Field(default=30, ge=5, le=3600)


class JobResponse(BaseModel):
    job_id: str
    type: str
    status: str
    priority: str
    progress: int
    message: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_seconds: float
    retry_count: int
    max_retries: int
    error_message: Optional[str] = None
    result: Optional[dict] = None


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    filters: dict


# Dependency for current user (simplified for now)
async def get_current_user():
    """Get current user - simplified implementation"""
    # TODO: Implement proper authentication
    return "admin"


@router.get("/health")
async def health_check():
    """Get job system health status"""
    try:
        if not is_fastapi_job_system_enabled():
            return {
                'status': 'starting',
                'message': 'Job system is starting up',
                'details': {
                    'workers': 'initializing',
                    'queue': 'initializing',
                    'ready': False
                }
            }
        
        # Get detailed health data
        health_data = await get_fastapi_job_system_health()
        return health_data
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Health check failed'
        }


@router.get("/status")
async def system_status():
    """Get job system status and statistics"""
    try:
        status = get_fastapi_job_system_status()
        return status
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        return {
            'status': 'partial',
            'message': 'Basic job system operational',
            'error': str(e),
            'queue_size': 0,
            'active_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0
        }


@router.post("/enqueue")
async def enqueue_job(
    job_request: JobCreateRequest,
    current_user: str = Depends(get_current_user)
):
    """Enqueue a new background job"""
    try:
        # Validate job type
        try:
            job_type = JobType(job_request.type)
        except ValueError:
            valid_types = [t.value for t in JobType]
            raise HTTPException(
                status_code=400,
                detail={
                    'error': f'Invalid job type. Valid types: {valid_types}'
                }
            )
        
        # Validate priority
        try:
            if isinstance(job_request.priority, int):
                priority = JobPriority(job_request.priority)
            else:
                priority = JobPriority[job_request.priority.upper()]
        except (ValueError, KeyError):
            valid_priorities = [p.name.lower() for p in JobPriority]
            raise HTTPException(
                status_code=400,
                detail={
                    'error': f'Invalid priority. Valid priorities: {valid_priorities}'
                }
            )
        
        # Create job
        job = BackgroundJob(
            type=job_type,
            priority=priority,
            payload=job_request.payload,
            created_by=current_user,
            max_retries=job_request.max_retries,
            retry_delay=job_request.retry_delay
        )
        
        # Enqueue job
        job_queue = await get_fastapi_job_queue()
        if not job_queue:
            job_queue = await get_job_queue()
        job_id = await job_queue.enqueue(job)
        
        logger.info(f"Enqueued job {job_id} ({job_type.value}) for user {current_user}")
        
        return {
            'success': True,
            'job_id': job_id,
            'message': f'{job_type.value} job queued successfully',
            'estimated_wait_time': 30  # TODO: Calculate based on queue size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job enqueue error: {e}")
        raise HTTPException(status_code=500, detail={'error': f'Failed to enqueue job: {str(e)}'})


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get status and progress of a specific job"""
    try:
        job_queue = await get_fastapi_job_queue()
        if not job_queue:
            job_queue = await get_job_queue()
        job = job_queue.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail={'error': 'Job not found'})
        
        # Check if user has permission to view this job
        if job.created_by and job.created_by != current_user:
            # TODO: Add admin role check
            raise HTTPException(status_code=403, detail={'error': 'Access denied'})
        
        # Return job status
        response_data = JobResponse(
            job_id=job.id,
            type=job.type.value,
            status=job.status.value,
            priority=job.priority.name.lower(),
            progress=job.progress,
            message=job.message or "",
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            elapsed_seconds=job.total_time().total_seconds()
        )
        
        # Add error message if job failed
        if job.status.value == 'failed' and job.error_message:
            response_data.error_message = job.error_message
        
        # Add result if job completed successfully
        if job.status.value == 'completed' and job.result:
            response_data.result = job.result
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job status error: {e}")
        raise HTTPException(status_code=500, detail={'error': f'Failed to get job status: {str(e)}'})


@router.get("")
async def list_user_jobs(
    current_user: str = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None, alias="type")
):
    """List recent jobs for current user"""
    try:        
        job_queue = await get_fastapi_job_queue()
        if not job_queue:
            job_queue = await get_job_queue()
        user_jobs = job_queue.get_user_jobs(current_user, limit)
        
        # Apply filters
        if status:
            user_jobs = [job for job in user_jobs if job.status.value == status]
        
        if job_type:
            user_jobs = [job for job in user_jobs if job.type.value == job_type]
        
        # Format response
        jobs_data = []
        for job in user_jobs:
            job_data = JobResponse(
                job_id=job.id,
                type=job.type.value,
                status=job.status.value,
                priority=job.priority.name.lower(),
                progress=job.progress,
                message=job.message or "",
                created_at=job.created_at.isoformat(),
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                elapsed_seconds=job.elapsed_time().total_seconds() if job.elapsed_time() else 0,
                retry_count=job.retry_count,
                max_retries=job.max_retries
            )
            jobs_data.append(job_data)
        
        return JobListResponse(
            jobs=jobs_data,
            total=len(jobs_data),
            filters={
                'status': status,
                'type': job_type,
                'limit': limit
            }
        )
        
    except Exception as e:
        logger.error(f"List jobs error: {e}")
        raise HTTPException(status_code=500, detail={'error': f'Failed to list jobs: {str(e)}'})


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: str = Depends(get_current_user)
):
    """Cancel a queued job"""
    try:
        job_queue = await get_fastapi_job_queue()
        if not job_queue:
            job_queue = await get_job_queue()
        job = job_queue.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail={'error': 'Job not found'})
        
        # Check permission
        if job.created_by and job.created_by != current_user:
            raise HTTPException(status_code=403, detail={'error': 'Access denied'})
        
        # Try to cancel job
        cancelled = await job_queue.cancel_job(job_id)
        
        if cancelled:
            logger.info(f"Job {job_id} cancelled by user {current_user}")
            return {
                'success': True,
                'message': 'Job cancelled successfully'
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail={'error': 'Job cannot be cancelled (may already be processing or completed)'}
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel job error: {e}")
        raise HTTPException(status_code=500, detail={'error': f'Failed to cancel job: {str(e)}'})


@router.get("/types")
async def get_job_types():
    """Get available job types and priorities"""
    job_types = [
        {
            'value': job_type.value,
            'name': job_type.value.replace('_', ' ').title(),
            'description': _get_job_type_description(job_type)
        }
        for job_type in JobType
    ]
    
    priorities = [
        {
            'value': priority.value,
            'name': priority.name.lower(),
            'description': _get_priority_description(priority)
        }
        for priority in JobPriority
    ]
    
    return {
        'job_types': job_types,
        'priorities': priorities
    }


def _get_job_type_description(job_type: JobType) -> str:
    """Get human-readable description for job type"""
    descriptions = {
        JobType.METADATA_ENRICHMENT: "Enrich artist metadata from external sources",
        JobType.VIDEO_DOWNLOAD: "Download music videos from external sources", 
        JobType.BULK_ARTIST_IMPORT: "Import multiple artists from playlists or sources",
        JobType.THUMBNAIL_GENERATION: "Generate thumbnails for videos",
        JobType.PLAYLIST_SYNC: "Synchronize playlists with external services",
        JobType.BULK_VIDEO_DELETE: "Delete multiple videos in batch",
        JobType.DATABASE_CLEANUP: "Clean up old data and optimize database",
        JobType.VIDEO_QUALITY_ANALYZE: "Analyze video quality and properties",
        JobType.VIDEO_QUALITY_UPGRADE: "Upgrade single video to higher quality",
        JobType.VIDEO_QUALITY_BULK_UPGRADE: "Upgrade multiple videos to higher quality",
        JobType.VIDEO_QUALITY_CHECK_ALL: "Check and verify quality for all videos",
        JobType.VIDEO_INDEX_ALL: "Index all videos in the music directory",
        JobType.VIDEO_INDEX_SINGLE: "Index a specific video file",
        JobType.VIDEO_ORGANIZE_ALL: "Organize all videos from downloads directory",
        JobType.VIDEO_ORGANIZE_SINGLE: "Organize a specific video file",
        JobType.VIDEO_REORGANIZE_EXISTING: "Reorganize existing videos in music directory",
        JobType.SCHEDULED_DOWNLOAD: "Scheduled download of wanted videos",
        JobType.SCHEDULED_DISCOVERY: "Scheduled discovery of new videos for artists"
    }
    return descriptions.get(job_type, "Background task")


def _get_priority_description(priority: JobPriority) -> str:
    """Get human-readable description for priority level"""
    descriptions = {
        JobPriority.LOW: "Background maintenance tasks",
        JobPriority.NORMAL: "Regular user-initiated tasks",
        JobPriority.HIGH: "Important user tasks requiring quick processing", 
        JobPriority.URGENT: "Critical tasks that should be processed immediately"
    }
    return descriptions.get(priority, "Standard priority")