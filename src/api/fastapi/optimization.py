"""
FastAPI Optimization Router
Migrated from Flask src/api/optimization.py - System optimization endpoints
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.services.search_optimization_service import search_optimization_service
from src.services.thumbnail_optimization_service import thumbnail_optimization_service

logger = logging.getLogger("mvidarr.fastapi.optimization")

router = APIRouter(
    prefix="/api/optimization",
    tags=["optimization"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class OptimizeRequest(BaseModel):
    """Optimization request"""

    dry_run: bool = Field(
        default=False, description="Run analysis without making changes"
    )


class OptimizationResults(BaseModel):
    """Optimization results"""

    analyzed: int = 0
    converted: int = 0
    space_saved: int = 0
    duplicates_found: Optional[int] = None


class OptimizationResponse(BaseModel):
    """Optimization response"""

    message: str
    results: OptimizationResults


class SearchPerformanceStats(BaseModel):
    """Search performance statistics"""

    hit_rate: float = 0.0
    total_requests: int = 0
    cache_stats: Dict[str, Any] = Field(default_factory=dict)


class ThumbnailAnalysis(BaseModel):
    """Thumbnail storage analysis"""

    total_files: int = 0
    total_size: int = 0
    by_format: Dict[str, Any] = Field(default_factory=dict)
    optimization_potential: int = 0


class OptimizationStatus(BaseModel):
    """Overall optimization status"""

    search_optimization: Dict[str, Any]
    thumbnail_optimization: Dict[str, Any]
    recommendations: List[str]
    system_health: str


# ========================================================================================
# SEARCH OPTIMIZATION ENDPOINTS
# ========================================================================================


@router.get("/search/performance", response_model=SearchPerformanceStats)
async def get_search_performance(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get search performance statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting search performance stats for user {current_user.get('username')}"
        )

        stats = search_optimization_service.get_performance_stats()

        return SearchPerformanceStats(
            hit_rate=stats.get("hit_rate", 0.0),
            total_requests=stats.get("total_requests", 0),
            cache_stats=stats.get("cache_stats", {}),
        )

    except Exception as e:
        logger.error(f"Failed to get search performance stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search/cache/clear")
async def clear_search_cache(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Clear search cache"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Clearing search cache for user {current_user.get('username')}")

        search_optimization_service.cache.clear()

        return {"message": "Search cache cleared successfully"}

    except Exception as e:
        logger.error(f"Failed to clear search cache: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search/cache/cleanup")
async def cleanup_search_cache(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Clean up expired cache entries"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Cleaning up search cache for user {current_user.get('username')}")

        search_optimization_service.cleanup_cache()

        return {"message": "Cache cleanup completed"}

    except Exception as e:
        logger.error(f"Failed to cleanup cache: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# THUMBNAIL OPTIMIZATION ENDPOINTS
# ========================================================================================


@router.get("/thumbnails/analyze", response_model=ThumbnailAnalysis)
async def analyze_thumbnail_storage(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Analyze thumbnail storage usage"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Analyzing thumbnail storage for user {current_user.get('username')}"
        )

        analysis = thumbnail_optimization_service.analyze_storage_usage()

        return ThumbnailAnalysis(
            total_files=analysis.get("total_files", 0),
            total_size=analysis.get("total_size", 0),
            by_format=analysis.get("by_format", {}),
            optimization_potential=analysis.get("optimization_potential", 0),
        )

    except Exception as e:
        logger.error(f"Failed to analyze thumbnail storage: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/thumbnails/recommendations")
async def get_optimization_recommendations(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get optimization recommendations"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting optimization recommendations for user {current_user.get('username')}"
        )

        recommendations = (
            thumbnail_optimization_service.get_optimization_recommendations()
        )

        return {"recommendations": recommendations}

    except Exception as e:
        logger.error(f"Failed to get optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/thumbnails/optimize", response_model=OptimizationResponse)
async def optimize_thumbnails(
    optimize_request: OptimizeRequest = OptimizeRequest(),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Optimize existing thumbnails by converting to WebP"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Optimizing thumbnails (dry_run={optimize_request.dry_run}) for user {current_user.get('username')}"
        )

        results = thumbnail_optimization_service.optimize_existing_thumbnails(
            dry_run=optimize_request.dry_run
        )

        message = (
            f"Thumbnail optimization {'analysis' if optimize_request.dry_run else 'completed'}: "
            f"{results['analyzed']} analyzed, {results['converted']} converted, "
            f"{results['space_saved']} bytes saved"
        )

        return OptimizationResponse(
            message=message,
            results=OptimizationResults(
                analyzed=results["analyzed"],
                converted=results["converted"],
                space_saved=results["space_saved"],
            ),
        )

    except Exception as e:
        logger.error(f"Failed to optimize thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/thumbnails/cleanup-duplicates", response_model=OptimizationResponse)
async def cleanup_duplicate_thumbnails(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Find and remove duplicate thumbnails"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Cleaning up duplicate thumbnails for user {current_user.get('username')}"
        )

        results = thumbnail_optimization_service.cleanup_duplicate_thumbnails()

        message = (
            f"Duplicate cleanup completed: {results['duplicates_found']} duplicates removed, "
            f"{results['space_saved']} bytes saved"
        )

        return OptimizationResponse(
            message=message,
            results=OptimizationResults(
                analyzed=0,
                converted=0,
                space_saved=results["space_saved"],
                duplicates_found=results["duplicates_found"],
            ),
        )

    except Exception as e:
        logger.error(f"Failed to cleanup duplicate thumbnails: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# DATABASE OPTIMIZATION ENDPOINTS
# ========================================================================================


@router.post("/database/indexes")
async def optimize_database_indexes(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Optimize database indexes for better performance"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Optimizing database indexes for user {current_user.get('username')}"
        )

        result = search_optimization_service.optimize_database_indexes()

        if result:
            return {"message": "Database indexes optimized successfully"}
        else:
            raise HTTPException(
                status_code=500, detail="Failed to optimize database indexes"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to optimize database indexes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# OPTIMIZATION STATUS ENDPOINT
# ========================================================================================


@router.get("/status", response_model=OptimizationStatus)
async def get_optimization_status(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get overall optimization status"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting optimization status for user {current_user.get('username')}"
        )

        # Get search performance stats
        search_stats = search_optimization_service.get_performance_stats()

        # Get thumbnail analysis
        thumbnail_analysis = thumbnail_optimization_service.analyze_storage_usage()

        # Get recommendations
        recommendations = (
            thumbnail_optimization_service.get_optimization_recommendations()
        )

        status = OptimizationStatus(
            search_optimization={
                "enabled": True,
                "cache_hit_rate": search_stats.get("hit_rate", 0),
                "total_requests": search_stats.get("total_requests", 0),
                "cache_entries": search_stats.get("cache_stats", {}).get(
                    "active_entries", 0
                ),
            },
            thumbnail_optimization={
                "total_files": thumbnail_analysis.get("total_files", 0),
                "total_size": thumbnail_analysis.get("total_size", 0),
                "webp_percentage": (
                    thumbnail_analysis.get("by_format", {})
                    .get(".webp", {})
                    .get("files", 0)
                    / max(thumbnail_analysis.get("total_files", 1), 1)
                    * 100
                ),
                "optimization_potential": thumbnail_analysis.get(
                    "optimization_potential", 0
                ),
            },
            recommendations=recommendations,
            system_health="optimal" if len(recommendations) == 0 else "needs_attention",
        )

        return status

    except Exception as e:
        logger.error(f"Failed to get optimization status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
