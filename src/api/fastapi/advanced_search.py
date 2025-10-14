"""
FastAPI Advanced Search API Router
Migrated from Flask src/api/advanced_search.py - Complete search functionality
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.database.search_models import SearchPresetType
from src.services.advanced_search_service import advanced_search_service
from src.services.search_presets_service import search_presets_service

logger = logging.getLogger("mvidarr.fastapi.advanced_search")

router = APIRouter(
    prefix="/api/search",
    tags=["advanced-search"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class SearchCriteriaModel(BaseModel):
    """Search criteria model"""

    text_query: Optional[str] = None
    search_fields: List[str] = Field(
        default=["title", "description", "search_keywords"]
    )
    status: Optional[List[str]] = None
    quality: Optional[List[str]] = None
    year_range: Optional[Dict[str, int]] = None
    duration_range: Optional[Dict[str, int]] = None
    genres: Optional[List[str]] = None
    has_thumbnail: Optional[bool] = None
    source: Optional[List[str]] = None
    artist_filters: Optional[Dict[str, Any]] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    discovered_after: Optional[str] = None
    discovered_before: Optional[str] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    include_relevance: bool = True


class SearchRequestModel(BaseModel):
    """Search request model"""

    search_criteria: SearchCriteriaModel
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)


class PresetCreateModel(BaseModel):
    """Create search preset model"""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    search_criteria: SearchCriteriaModel
    is_public: bool = False
    is_favorite: bool = False


class PresetUpdateModel(BaseModel):
    """Update search preset model"""

    name: Optional[str] = None
    description: Optional[str] = None
    search_criteria: Optional[SearchCriteriaModel] = None
    is_public: Optional[bool] = None
    is_favorite: Optional[bool] = None


class ExportRequestModel(BaseModel):
    """Export search results model"""

    search_criteria: SearchCriteriaModel
    export_format: str = Field(default="json", pattern="^(json|csv|xlsx)$")
    include_metadata: bool = True
    include_thumbnails: bool = False


# ========================================================================================
# ADVANCED SEARCH ENDPOINTS
# ========================================================================================


@router.post("/videos")
async def search_videos(
    search_request: SearchRequestModel,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Advanced video search with comprehensive filtering

    Supports complex search criteria including:
    - Text search across multiple fields
    - Status and quality filtering
    - Date range filtering
    - Genre and artist filtering
    - Sorting and pagination
    """
    try:
        # Extract search parameters
        criteria = search_request.search_criteria.dict()
        page = search_request.page
        per_page = search_request.per_page

        logger.info(
            f"Advanced search request from user {current_user.get('username', 'unknown')}"
        )

        # Perform search using service
        result = advanced_search_service.search_videos(
            search_criteria=criteria,
            page=page,
            per_page=per_page,
            user_id=current_user.get("user_id", 1),
        )

        return {
            "videos": result.get("videos", []),
            "pagination": result.get("pagination", {}),
            "search_info": result.get("search_info", {}),
            "filters_applied": result.get("filters_applied", {}),
            "execution_time": result.get("execution_time", 0),
        }

    except Exception as e:
        logger.error(f"Error in advanced video search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# SEARCH PRESETS MANAGEMENT
# ========================================================================================


@router.get("/presets")
async def get_search_presets(
    preset_type: Optional[str] = Query(None, pattern="^(user|public|system)$"),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get search presets for current user"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get presets based on type
        if preset_type:
            preset_filter = SearchPresetType(preset_type.upper())
            presets = search_presets_service.get_presets_by_type(
                user_id=user_id, preset_type=preset_filter
            )
        else:
            presets = search_presets_service.get_user_presets(user_id=user_id)

        return {
            "presets": [preset.to_dict() for preset in presets],
            "total": len(presets),
        }

    except Exception as e:
        logger.error(f"Error getting search presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets")
async def create_search_preset(
    preset_data: PresetCreateModel,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Create new search preset"""
    try:
        user_id = current_user.get("user_id", 1)

        # Create preset using service
        preset = search_presets_service.create_preset(
            user_id=user_id,
            name=preset_data.name,
            description=preset_data.description,
            search_criteria=preset_data.search_criteria.dict(),
            is_public=preset_data.is_public,
            is_favorite=preset_data.is_favorite,
        )

        logger.info(
            f"Created search preset '{preset_data.name}' for user {current_user.get('username')}"
        )

        return {
            "success": True,
            "preset": preset.to_dict(),
            "message": f"Search preset '{preset_data.name}' created successfully",
        }

    except Exception as e:
        logger.error(f"Error creating search preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets/{preset_id}")
async def get_search_preset(
    preset_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get specific search preset"""
    try:
        user_id = current_user.get("user_id", 1)

        preset = search_presets_service.get_preset(preset_id=preset_id, user_id=user_id)

        if not preset:
            raise HTTPException(status_code=404, detail="Search preset not found")

        return preset.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting search preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/presets/{preset_id}")
async def update_search_preset(
    preset_id: int,
    preset_update: PresetUpdateModel,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Update search preset"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get existing preset
        preset = search_presets_service.get_preset(preset_id=preset_id, user_id=user_id)

        if not preset:
            raise HTTPException(status_code=404, detail="Search preset not found")

        # Update fields
        update_data = {}
        if preset_update.name is not None:
            update_data["name"] = preset_update.name
        if preset_update.description is not None:
            update_data["description"] = preset_update.description
        if preset_update.search_criteria is not None:
            update_data["search_criteria"] = preset_update.search_criteria.dict()
        if preset_update.is_public is not None:
            update_data["is_public"] = preset_update.is_public
        if preset_update.is_favorite is not None:
            update_data["is_favorite"] = preset_update.is_favorite

        # Update preset
        updated_preset = search_presets_service.update_preset(
            preset_id=preset_id, user_id=user_id, **update_data
        )

        logger.info(
            f"Updated search preset {preset_id} for user {current_user.get('username')}"
        )

        return {
            "success": True,
            "preset": updated_preset.to_dict(),
            "message": "Search preset updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating search preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/presets/{preset_id}")
async def delete_search_preset(
    preset_id: int,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Delete search preset"""
    try:
        user_id = current_user.get("user_id", 1)

        success = search_presets_service.delete_preset(
            preset_id=preset_id, user_id=user_id
        )

        if not success:
            raise HTTPException(status_code=404, detail="Search preset not found")

        logger.info(
            f"Deleted search preset {preset_id} for user {current_user.get('username')}"
        )

        return {"success": True, "message": "Search preset deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting search preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets/{preset_id}/use")
async def use_search_preset(
    preset_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Execute search using saved preset"""
    try:
        user_id = current_user.get("user_id", 1)

        # Get preset
        preset = search_presets_service.get_preset(preset_id=preset_id, user_id=user_id)

        if not preset:
            raise HTTPException(status_code=404, detail="Search preset not found")

        # Execute search using preset criteria
        result = advanced_search_service.search_videos(
            search_criteria=preset.search_criteria,
            page=page,
            per_page=per_page,
            user_id=user_id,
        )

        # Update usage statistics
        search_presets_service.update_usage_stats(preset_id)

        return {
            "videos": result.get("videos", []),
            "pagination": result.get("pagination", {}),
            "search_info": result.get("search_info", {}),
            "preset_info": {
                "id": preset.id,
                "name": preset.name,
                "description": preset.description,
            },
            "execution_time": result.get("execution_time", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error using search preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# SEARCH UTILITIES AND ANALYTICS
# ========================================================================================


@router.get("/presets/popular")
async def get_popular_presets(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get popular public search presets"""
    try:
        presets = search_presets_service.get_popular_presets(limit=limit)

        return {
            "presets": [preset.to_dict() for preset in presets],
            "total": len(presets),
        }

    except Exception as e:
        logger.error(f"Error getting popular presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets/search")
async def search_presets(
    query: str = Query(..., min_length=1),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Search for presets by name or description"""
    try:
        user_id = current_user.get("user_id", 1)

        presets = search_presets_service.search_presets(query=query, user_id=user_id)

        return {
            "presets": [preset.to_dict() for preset in presets],
            "total": len(presets),
            "query": query,
        }

    except Exception as e:
        logger.error(f"Error searching presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
async def export_search_results(
    export_request: ExportRequestModel,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Export search results to various formats"""
    try:
        user_id = current_user.get("user_id", 1)

        # Perform search to get results
        search_result = advanced_search_service.search_videos(
            search_criteria=export_request.search_criteria.dict(),
            page=1,
            per_page=10000,  # Large number to get all results
            user_id=user_id,
        )

        # Export results using service
        export_result = advanced_search_service.export_results(
            videos=search_result.get("videos", []),
            export_format=export_request.export_format,
            include_metadata=export_request.include_metadata,
            include_thumbnails=export_request.include_thumbnails,
            user_id=user_id,
        )

        logger.info(
            f"Exported {len(search_result.get('videos', []))} search results as {export_request.export_format} for user {current_user.get('username')}"
        )

        return {
            "success": True,
            "export_url": export_result.get("url"),
            "filename": export_result.get("filename"),
            "format": export_request.export_format,
            "record_count": len(search_result.get("videos", [])),
            "message": f"Search results exported as {export_request.export_format}",
        }

    except Exception as e:
        logger.error(f"Error exporting search results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=1),
    field: str = Query(default="title", pattern="^(title|artist|genre|description)$"),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get search suggestions for autocomplete"""
    try:
        suggestions = advanced_search_service.get_search_suggestions(
            query=query, field=field, limit=limit
        )

        return {
            "suggestions": suggestions,
            "query": query,
            "field": field,
            "total": len(suggestions),
        }

    except Exception as e:
        logger.error(f"Error getting search suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_search_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get search analytics and usage statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        analytics = advanced_search_service.get_search_analytics(
            user_id=user_id, days=days
        )

        return {
            "analytics": analytics,
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting search analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
