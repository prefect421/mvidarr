"""
MVidarr Image Processing FastAPI Endpoints - Phase 2 Week 20
REST API for concurrent image processing operations
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from src.jobs.image_processing_tasks import (
    BulkThumbnailGenerationTask,
    ConcurrentImageOptimizationTask,
    ImageAnalysisTask,
    ThumbnailSpec,
    submit_bulk_thumbnail_generation,
    submit_concurrent_image_optimization,
    submit_image_analysis,
)
from src.services.image_thread_pool import get_image_processing_pool
from src.services.performance_monitor import track_api_response_time
from src.services.thumbnail_generator import (
    ConcurrentThumbnailGenerator,
    ThumbnailConfig,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.image_processing")

router = APIRouter(
    prefix="/api/image-processing",
    tags=["image-processing"],
    responses={404: {"description": "Not found"}},
)


# Request/Response Models
class ThumbnailSpecModel(BaseModel):
    """Thumbnail specification model"""

    width: int = Field(..., gt=0, le=4096, description="Thumbnail width in pixels")
    height: int = Field(..., gt=0, le=4096, description="Thumbnail height in pixels")
    quality: int = Field(85, ge=1, le=100, description="JPEG quality (1-100)")
    format: str = Field("JPEG", pattern="^(JPEG|PNG)$", description="Image format")
    suffix: str = Field("", max_length=50, description="Filename suffix")


class ThumbnailGenerationRequest(BaseModel):
    """Request model for thumbnail generation"""

    source_paths: List[str] = Field(
        ..., min_items=1, max_items=1000, description="List of source image paths"
    )
    output_dir: str = Field(..., description="Output directory for thumbnails")
    specs: Optional[List[ThumbnailSpecModel]] = Field(
        None, description="Thumbnail specifications (optional)"
    )
    use_presets: Optional[List[str]] = Field(None, description="Use predefined presets")


class ImageOptimizationRequest(BaseModel):
    """Request model for image optimization"""

    source_paths: List[str] = Field(
        ..., min_items=1, max_items=1000, description="List of source image paths"
    )
    output_dir: str = Field(..., description="Output directory for optimized images")
    quality: int = Field(85, ge=1, le=100, description="Optimization quality (1-100)")
    max_dimension: Optional[int] = Field(
        None, ge=100, le=4096, description="Maximum dimension for resizing"
    )


class ImageAnalysisRequest(BaseModel):
    """Request model for image analysis"""

    source_paths: List[str] = Field(
        ..., min_items=1, max_items=1000, description="List of source image paths"
    )


class TaskStatusResponse(BaseModel):
    """Task status response model"""

    task_id: str
    status: str
    progress: float
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class ImageProcessingStatsResponse(BaseModel):
    """Image processing statistics response"""

    thread_pool: Dict[str, Any]
    jobs: Dict[str, Any]
    performance: Dict[str, Any]
    resources: Dict[str, Any]


# Endpoints
@router.post("/thumbnails/generate", response_model=Dict[str, str])
async def generate_thumbnails(
    request: ThumbnailGenerationRequest, background_tasks: BackgroundTasks
):
    """
    Generate thumbnails for multiple images concurrently

    This endpoint processes multiple images to generate thumbnails in various sizes.
    Processing is done in the background using thread pools for maximum performance.
    """
    import time

    start_time = time.time()

    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.source_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        # Convert specs or use presets
        thumbnail_specs = None
        if request.specs:
            thumbnail_specs = [
                ThumbnailSpec(
                    width=spec.width,
                    height=spec.height,
                    quality=spec.quality,
                    format=spec.format,
                    suffix=spec.suffix,
                )
                for spec in request.specs
            ]

        # Submit thumbnail generation task
        # For image processing tasks, use default user ID since these are system operations
        task_id = await submit_bulk_thumbnail_generation(
            source_paths=[str(p) for p in source_paths],
            output_dir=request.output_dir,
            specs=thumbnail_specs,
            user_id=1,  # System user for background image processing
        )

        logger.info(f"🖼️ Thumbnail generation task submitted: {task_id}")

        # Track API performance
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        await track_api_response_time(
            "/api/image-processing/thumbnails/generate", response_time, 200
        )

        return {
            "task_id": task_id,
            "status": "submitted",
            "message": f"Processing {len(source_paths)} images for thumbnail generation",
        }

    except HTTPException:
        response_time = (time.time() - start_time) * 1000
        await track_api_response_time(
            "/api/image-processing/thumbnails/generate", response_time, 400
        )
        raise
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        await track_api_response_time(
            "/api/image-processing/thumbnails/generate", response_time, 500
        )
        logger.error(f"❌ Thumbnail generation request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/images/optimize", response_model=Dict[str, str])
async def optimize_images(
    request: ImageOptimizationRequest, background_tasks: BackgroundTasks
):
    """
    Optimize multiple images concurrently

    This endpoint processes multiple images to optimize their size and quality.
    Processing is done in the background using thread pools.
    """
    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.source_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        # Submit optimization task
        task_id = await submit_concurrent_image_optimization(
            source_paths=[str(p) for p in source_paths],
            output_dir=request.output_dir,
            quality=request.quality,
            max_dimension=request.max_dimension,
            user_id=1,  # System user for background image processing
        )

        logger.info(f"⚡ Image optimization task submitted: {task_id}")

        return {
            "task_id": task_id,
            "status": "submitted",
            "message": f"Processing {len(source_paths)} images for optimization",
        }

    except Exception as e:
        logger.error(f"❌ Image optimization request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/images/analyze", response_model=Dict[str, str])
async def analyze_images(
    request: ImageAnalysisRequest, background_tasks: BackgroundTasks
):
    """
    Analyze multiple images concurrently

    This endpoint analyzes multiple images for metadata, quality metrics, and properties.
    Processing is done in the background using thread pools.
    """
    try:
        # Validate paths exist
        source_paths = [Path(p) for p in request.source_paths]
        missing_paths = [p for p in source_paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        # Submit analysis task
        task_id = await submit_image_analysis(
            source_paths=[str(p) for p in source_paths],
            user_id=1,  # System user for background image processing
        )

        logger.info(f"🔍 Image analysis task submitted: {task_id}")

        return {
            "task_id": task_id,
            "status": "submitted",
            "message": f"Analyzing {len(source_paths)} images",
        }

    except Exception as e:
        logger.error(f"❌ Image analysis request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ImageProcessingStatsResponse)
async def get_processing_stats():
    """
    Get image processing performance statistics

    Returns current performance metrics for the image processing thread pools.
    """
    try:
        pool = get_image_processing_pool()
        stats = pool.get_performance_metrics()

        return ImageProcessingStatsResponse(**stats)

    except Exception as e:
        logger.error(f"❌ Failed to get processing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets", response_model=Dict[str, Dict])
async def get_thumbnail_presets():
    """
    Get available thumbnail presets

    Returns a list of predefined thumbnail configurations.
    """
    try:
        presets = {}
        for name, config in ConcurrentThumbnailGenerator.THUMBNAIL_PRESETS.items():
            presets[name] = {
                "width": config.width,
                "height": config.height,
                "quality": config.quality,
                "format": config.format,
                "suffix": config.suffix,
                "maintain_aspect": config.maintain_aspect,
                "enhance_sharpness": config.enhance_sharpness,
                "enhance_contrast": config.enhance_contrast,
            }

        return presets

    except Exception as e:
        logger.error(f"❌ Failed to get thumbnail presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thumbnails/generate-preset")
async def generate_preset_thumbnails(
    source_paths: List[str] = Body(..., description="List of source image paths"),
    output_dir: str = Body(..., description="Output directory for thumbnails"),
    presets: List[str] = Body(
        ["small", "medium", "large"], description="Preset names to generate"
    ),
):
    """
    Generate thumbnails using predefined presets

    This endpoint generates thumbnails using predefined size/quality presets for convenience.
    """
    try:
        # Validate paths exist
        paths = [Path(p) for p in source_paths]
        missing_paths = [p for p in paths if not p.exists()]
        if missing_paths:
            raise HTTPException(
                status_code=400,
                detail=f"Source paths not found: {[str(p) for p in missing_paths]}",
            )

        # Validate presets
        available_presets = set(ConcurrentThumbnailGenerator.THUMBNAIL_PRESETS.keys())
        invalid_presets = [p for p in presets if p not in available_presets]
        if invalid_presets:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid presets: {invalid_presets}. Available: {list(available_presets)}",
            )

        # Generate thumbnails
        generator = ConcurrentThumbnailGenerator(Path(output_dir))
        results = await generator.generate_preset_thumbnails(paths, presets)

        # Format response
        successful = [r.to_dict() for r in results if r.success]
        failed = [r.to_dict() for r in results if not r.success]

        response = {
            "total_processed": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": (
                f"{(len(successful) / len(results) * 100):.1f}%" if results else "0%"
            ),
            "results": {"successful": successful, "failed": failed},
        }

        logger.info(
            f"✅ Preset thumbnail generation completed: {len(successful)}/{len(results)} successful"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Preset thumbnail generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache/thumbnails")
async def clear_thumbnail_cache(
    output_dir: str = Query(..., description="Thumbnail output directory")
):
    """
    Clear thumbnail cache

    Removes all cached thumbnails and cache index for the specified output directory.
    """
    try:
        generator = ConcurrentThumbnailGenerator(Path(output_dir))
        cleared_count = generator.clear_cache()

        return {
            "cleared_thumbnails": cleared_count,
            "message": f"Cleared {cleared_count} cached thumbnails",
        }

    except Exception as e:
        logger.error(f"❌ Failed to clear thumbnail cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def get_cache_stats(
    output_dir: str = Query(..., description="Thumbnail output directory")
):
    """
    Get thumbnail cache statistics

    Returns information about cached thumbnails for the specified output directory.
    """
    try:
        generator = ConcurrentThumbnailGenerator(Path(output_dir))
        stats = generator.get_cache_stats()

        return stats

    except Exception as e:
        logger.error(f"❌ Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
