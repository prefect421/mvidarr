"""
FastAPI IMVDb Router - Migrated from Flask Blueprint
IMVDb API endpoints for video discovery and management
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.services.imvdb_analytics_service import imvdb_analytics_service
from src.services.imvdb_discovery_service import imvdb_discovery_service
from src.services.imvdb_service import imvdb_service
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/imvdb",
    tags=["imvdb"],
    responses={
        404: {"description": "Resource not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.imvdb")
# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================


class SearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    count: int


class ArtistDetailResponse(BaseModel):
    success: bool
    artist: Dict[str, Any]


class VideoDetailResponse(BaseModel):
    success: bool
    video: Dict[str, Any]


class AdvancedSearchRequest(BaseModel):
    query: Optional[str] = None
    genre: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    directors: Optional[List[str]] = None
    artists: Optional[List[str]] = None


class AdvancedSearchResponse(BaseModel):
    success: bool
    results: Dict[str, Any]


class GenreSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    count: int
    genre: str


class YearSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    count: int
    year_range: Dict[str, Optional[int]]


class DirectorSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    count: int
    director: str


class TrendingResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    count: int
    parameters: Dict[str, int]


class DiscoveryRequest(BaseModel):
    artist_ids: Optional[List[int]] = None
    force: bool = False


class DiscoveryResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    discovered_videos: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class TrendingDiscoveryResponse(BaseModel):
    success: bool
    trending_videos: Optional[List[Dict[str, Any]]] = None
    suggested_artists: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class SimilarArtistsResponse(BaseModel):
    success: bool
    similar_artists: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class DiscoveryStatsResponse(BaseModel):
    success: bool
    statistics: Dict[str, Any]


class QualityAnalysisRequest(BaseModel):
    video_data: Dict[str, Any]


class QualityAnalysisResponse(BaseModel):
    success: bool
    quality_analysis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class VideoRankingRequest(BaseModel):
    videos: List[Dict[str, Any]]
    user_id: Optional[int] = None


class VideoRankingResponse(BaseModel):
    success: bool
    ranked_videos: Optional[List[Dict[str, Any]]] = None
    total_videos: Optional[int] = None
    error: Optional[str] = None


class QualityStatsRequest(BaseModel):
    videos: List[Dict[str, Any]]


class QualityStatsResponse(BaseModel):
    success: bool
    statistics: Optional[Dict[str, Any]] = None


class UserPreferencesResponse(BaseModel):
    success: bool
    preferences: Optional[Dict[str, Any]] = None


class QualityDiscoveryResponse(BaseModel):
    success: bool
    trending_videos: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class QualityPatternsResponse(BaseModel):
    success: bool
    patterns: Dict[str, Any]


class AnalyticsResponse(BaseModel):
    success: bool
    analysis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ComprehensiveReportResponse(BaseModel):
    success: bool
    report: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ========================================================================================
# SEARCH ENDPOINTS
# ========================================================================================


@router.get("/search-artist", response_model=SearchResponse)
async def search_artist(
    q: str = Query(..., description="Search query"),
    current_user: dict = Depends(require_authentication),
):
    """Search for artists in IMVDb"""
    try:
        if not q.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'q' is required",
            )

        # Search for multiple artists
        artists = imvdb_service.search_artists(q, limit=10)

        return SearchResponse(success=True, results=artists, count=len(artists))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching IMVDb artists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/search-videos", response_model=SearchResponse)
async def search_videos(
    q: str = Query(..., description="Search query"),
    artist_id: Optional[str] = Query(None, description="Filter by artist ID"),
    current_user: dict = Depends(require_authentication),
):
    """Search for videos in IMVDb"""
    try:
        if not q.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'q' is required",
            )

        if artist_id:
            # Get videos for specific artist
            result = imvdb_service.search_artist_videos(q, limit=25)
            videos = result.get("videos", []) if result else []
        else:
            # General video search
            videos = imvdb_service.search_videos(q)

        return SearchResponse(success=True, results=videos, count=len(videos))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching IMVDb videos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/artist/{artist_id}", response_model=ArtistDetailResponse)
async def get_artist_details(
    artist_id: int, current_user: dict = Depends(require_authentication)
):
    """Get detailed artist information from IMVDb"""
    try:
        artist = imvdb_service.get_artist_by_id(artist_id)

        if not artist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Artist not found"
            )

        return ArtistDetailResponse(success=True, artist=artist)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting IMVDb artist details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/video/{video_id}", response_model=VideoDetailResponse)
async def get_video_details(
    video_id: int, current_user: dict = Depends(require_authentication)
):
    """Get detailed video information from IMVDb"""
    try:
        video = imvdb_service.get_video_by_id(video_id)

        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
            )

        return VideoDetailResponse(success=True, video=video)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting IMVDb video details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/advanced-search", response_model=AdvancedSearchResponse)
async def advanced_search(
    filters: AdvancedSearchRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Advanced video search with filtering"""
    try:
        # Validate required parameters
        filters_dict = filters.dict(exclude_none=True)
        if not filters_dict.get("query") and not any(
            [
                filters_dict.get("genre"),
                filters_dict.get("year_min"),
                filters_dict.get("year_max"),
                filters_dict.get("directors"),
                filters_dict.get("artists"),
            ]
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one search criteria is required",
            )

        result = imvdb_service.advanced_search_videos(filters_dict)

        return AdvancedSearchResponse(success=True, results=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in advanced search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/search-by-genre", response_model=GenreSearchResponse)
async def search_by_genre(
    genre: str = Query(..., description="Genre to search for"),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Search videos by genre"""
    try:
        if not genre.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Genre parameter is required",
            )

        videos = imvdb_service.search_videos_by_genre(genre, limit)

        return GenreSearchResponse(
            success=True, results=videos, count=len(videos), genre=genre
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching by genre: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/search-by-year", response_model=YearSearchResponse)
async def search_by_year(
    year_min: Optional[int] = Query(None, description="Minimum year"),
    year_max: Optional[int] = Query(None, description="Maximum year"),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Search videos by year range"""
    try:
        if not year_min and not year_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least year_min or year_max is required",
            )

        videos = imvdb_service.search_videos_by_year_range(
            year_min or 1900, year_max or 2030, limit
        )

        return YearSearchResponse(
            success=True,
            results=videos,
            count=len(videos),
            year_range={"min": year_min, "max": year_max},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching by year: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/search-by-director", response_model=DirectorSearchResponse)
async def search_by_director(
    director: str = Query(..., description="Director name"),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Search videos by director"""
    try:
        if not director.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Director parameter is required",
            )

        videos = imvdb_service.search_videos_by_director(director, limit)

        return DirectorSearchResponse(
            success=True,
            results=videos,
            count=len(videos),
            director=director,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching by director: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/trending", response_model=TrendingResponse)
async def get_trending(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Get trending/popular videos"""
    try:
        videos = imvdb_service.get_trending_videos(days, limit)

        return TrendingResponse(
            success=True,
            results=videos,
            count=len(videos),
            parameters={"days": days, "limit": limit},
        )

    except Exception as e:
        logger.error(f"Error getting trending videos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# DISCOVERY ENDPOINTS
# ========================================================================================


@router.post("/discovery/run", response_model=DiscoveryResponse)
async def run_discovery(
    request: DiscoveryRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Run automated video discovery"""
    try:
        result = imvdb_discovery_service.discover_new_videos(
            request.artist_ids, request.force
        )

        return DiscoveryResponse(**result)

    except Exception as e:
        logger.error(f"Error running discovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/discovery/trending", response_model=TrendingDiscoveryResponse)
async def discover_trending(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Discover trending videos and suggest new artists"""
    try:
        result = imvdb_discovery_service.discover_trending_videos(limit)

        return TrendingDiscoveryResponse(**result)

    except Exception as e:
        logger.error(f"Error discovering trending: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/discovery/similar-artists/{artist_id}", response_model=SimilarArtistsResponse
)
async def discover_similar_artists(
    artist_id: int,
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_authentication),
):
    """Discover artists similar to a given artist"""
    try:
        result = imvdb_discovery_service.discover_similar_artists(artist_id, limit)

        return SimilarArtistsResponse(**result)

    except Exception as e:
        logger.error(f"Error discovering similar artists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/discovery/stats", response_model=DiscoveryStatsResponse)
async def get_discovery_stats(current_user: dict = Depends(require_authentication)):
    """Get discovery statistics"""
    try:
        stats = imvdb_discovery_service.get_discovery_statistics()

        return DiscoveryStatsResponse(success=True, statistics=stats)

    except Exception as e:
        logger.error(f"Error getting discovery stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# QUALITY TRACKING ENDPOINTS
# ========================================================================================


@router.post("/quality/analyze", response_model=QualityAnalysisResponse)
async def analyze_video_quality(
    request: QualityAnalysisRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Analyze quality of IMVDb video data"""
    try:
        analysis = imvdb_service.analyze_video_quality(request.video_data)

        return QualityAnalysisResponse(success=True, quality_analysis=analysis)

    except Exception as e:
        logger.error(f"Error analyzing video quality: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/quality/rank-videos", response_model=VideoRankingResponse)
async def rank_videos_by_quality(
    request: VideoRankingRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Rank videos by quality and user preferences"""
    try:
        ranked_videos = imvdb_service.rank_videos_by_preferences(
            request.videos, request.user_id
        )

        return VideoRankingResponse(
            success=True,
            ranked_videos=ranked_videos,
            total_videos=len(ranked_videos),
        )

    except Exception as e:
        logger.error(f"Error ranking videos by quality: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/quality/statistics", response_model=QualityStatsResponse)
async def get_quality_statistics(
    request: QualityStatsRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Get quality statistics for a list of videos"""
    try:
        statistics = imvdb_service.get_quality_statistics(request.videos)

        return QualityStatsResponse(success=True, statistics=statistics)

    except Exception as e:
        logger.error(f"Error getting quality statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/quality/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    user_id: Optional[int] = Query(None, description="User ID"),
    current_user: dict = Depends(require_authentication),
):
    """Get user preferences for video quality and sources"""
    try:
        preferences = imvdb_service.get_user_preferences(user_id)

        return UserPreferencesResponse(success=True, preferences=preferences)

    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/discovery/trending-quality", response_model=QualityDiscoveryResponse)
async def discover_trending_with_quality(
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="User ID"),
    current_user: dict = Depends(require_authentication),
):
    """Discover trending videos with quality filtering"""
    try:
        result = imvdb_discovery_service.discover_trending_videos(limit, user_id)

        return QualityDiscoveryResponse(**result)

    except Exception as e:
        logger.error(f"Error discovering trending videos with quality: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/discovery/quality-patterns", response_model=QualityPatternsResponse)
async def get_quality_discovery_patterns(
    current_user: dict = Depends(require_authentication),
):
    """Get quality patterns in discovery history"""
    try:
        patterns = imvdb_discovery_service.get_quality_discovery_patterns()

        return QualityPatternsResponse(success=True, patterns=patterns)

    except Exception as e:
        logger.error(f"Error getting quality discovery patterns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# ANALYTICS ENDPOINTS
# ========================================================================================


@router.get("/analytics/discovery-performance", response_model=AnalyticsResponse)
async def analyze_discovery_performance(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_authentication),
):
    """Analyze discovery performance over time"""
    try:
        analysis = imvdb_analytics_service.analyze_discovery_performance(days)

        return AnalyticsResponse(success=True, analysis=analysis)

    except Exception as e:
        logger.error(f"Error analyzing discovery performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/analytics/comprehensive-report", response_model=ComprehensiveReportResponse
)
async def generate_comprehensive_report(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_authentication),
):
    """Generate comprehensive discovery analysis report"""
    try:
        report = imvdb_analytics_service.generate_comprehensive_discovery_report(days)

        return ComprehensiveReportResponse(success=True, report=report)

    except Exception as e:
        logger.error(f"Error generating comprehensive report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
