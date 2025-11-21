"""
Personal Insights API endpoints for MVidarr.

Provides collection analytics and insights for home self-hosters.
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict
import logging

from src.services.personal_analytics import (
    get_collection_statistics,
    get_top_artists,
    get_top_genres,
    get_collection_health,
    get_recent_additions,
    get_analytics_summary,
    export_collection_csv,
)

logger = logging.getLogger(__name__)

# Setup templates
templates = Jinja2Templates(directory="frontend/templates")

router = APIRouter(prefix="/api/analytics", tags=["Personal Analytics"])


@router.get("/summary")
async def get_summary() -> Dict:
    """
    Get comprehensive analytics summary.

    Returns:
        Complete analytics data
    """
    try:
        return get_analytics_summary()
    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collection")
async def get_collection_stats() -> Dict:
    """
    Get collection statistics.

    Returns:
        Collection stats (videos, artists, playlists, genres)
    """
    try:
        result = get_collection_statistics()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-artists")
async def get_top_artists_list(limit: int = 10) -> Dict:
    """
    Get top artists by video count.

    Args:
        limit: Number of artists to return (default: 10, max: 50)

    Returns:
        Top artists
    """
    try:
        limit = min(limit, 50)  # Cap at 50
        result = get_top_artists(limit=limit)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting top artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-genres")
async def get_top_genres_list(limit: int = 10) -> Dict:
    """
    Get top genres by video count.

    Args:
        limit: Number of genres to return (default: 10, max: 50)

    Returns:
        Top genres
    """
    try:
        limit = min(limit, 50)  # Cap at 50
        result = get_top_genres(limit=limit)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting top genres: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_health() -> Dict:
    """
    Get collection health assessment.

    Returns:
        Health score and issues
    """
    try:
        result = get_collection_health()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting collection health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent(days: int = 30, limit: int = 10) -> Dict:
    """
    Get recently added videos.

    Args:
        days: Number of days to look back (default: 30)
        limit: Max number of videos (default: 10, max: 100)

    Returns:
        Recent videos
    """
    try:
        days = min(days, 365)  # Cap at 1 year
        limit = min(limit, 100)  # Cap at 100

        result = get_recent_additions(days=days, limit=limit)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recent additions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/csv")
async def export_csv():
    """
    Export collection as CSV file.

    Returns:
        CSV file download
    """
    try:
        csv_data = export_collection_csv()

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=mvidarr_collection_{datetime.now().strftime('%Y%m%d')}.csv"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Create a separate router for the web page (without /api prefix)
page_router = APIRouter(tags=["Analytics Pages"])


@page_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Render the personal analytics page."""
    return templates.TemplateResponse("collection_stats.html", {"request": request})


# Import datetime for CSV filename
from datetime import datetime
