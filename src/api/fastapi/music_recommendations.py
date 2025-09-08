"""
MVidarr Music Recommendations API - FastAPI Implementation
FastAPI endpoints for music video recommendations matching existing Flask functionality
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from src.services.music_recommendations import (
    get_music_recommendation_service,
    RecommendationRequest,
    RecommendationType,
    get_music_recommendations,
    get_similar_artist_videos,
    get_trending_music_videos
)
from src.services.spotify_service import get_spotify_service
from src.services.lastfm_service import get_lastfm_service
from src.services.imvdb_service import get_imvdb_service
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.music_recommendations")

# Create music recommendations router - matches Flask endpoint structure
recommendations_router = APIRouter(prefix="/api/recommendations", tags=["Music Recommendations"])


# Pydantic models for request/response schemas
class SpotifyRecommendationRequest(BaseModel):
    """Request for Spotify-based recommendations - matches Flask functionality"""
    user_id: Optional[str] = Field(default=None, description="Spotify user ID")
    seed_artists: Optional[List[str]] = Field(default=None, description="Seed artist names or IDs")
    seed_tracks: Optional[List[str]] = Field(default=None, description="Seed track names or IDs") 
    seed_genres: Optional[List[str]] = Field(default=None, description="Seed genres")
    limit: int = Field(default=20, description="Maximum number of recommendations")
    target_acousticness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    target_danceability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    target_energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    target_valence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ArtistRecommendationRequest(BaseModel):
    """Request for artist-based recommendations"""
    artist_name: str = Field(..., description="Artist name for similar recommendations")
    max_recommendations: int = Field(default=10, description="Maximum recommendations to return")
    include_videos: bool = Field(default=True, description="Include music video links")
    sources: Optional[List[str]] = Field(default=None, description="Specific sources to use (spotify, lastfm, imvdb)")


class GenreRecommendationRequest(BaseModel):
    """Request for genre-based recommendations"""
    genre: str = Field(..., description="Genre for recommendations")
    max_recommendations: int = Field(default=15, description="Maximum recommendations")
    include_trending: bool = Field(default=True, description="Include trending content")


class RecommendationResponse(BaseModel):
    """Unified recommendation response - matches Flask format"""
    recommendations: List[Dict[str, Any]]
    total_found: int
    processing_time: float
    sources_used: List[str]
    cache_hit: bool = False
    success: bool = True
    message: str = "Recommendations generated successfully"


class RecommendationStatsResponse(BaseModel):
    """Recommendation statistics response"""
    total_requests: int
    successful_recommendations: int
    cache_hits: int
    average_processing_time: float
    source_usage: Dict[str, int]
    enabled_sources: Dict[str, bool]


# Spotify Recommendations Endpoints - Match Flask /spotify/recommendations routes
@recommendations_router.get("/spotify", response_model=RecommendationResponse)
async def get_spotify_recommendations_from_history(
    user_id: Optional[str] = Query(None, description="Spotify user ID"),
    limit: int = Query(20, description="Maximum recommendations")
):
    """
    Get music video recommendations from Spotify listening history
    Matches Flask route: GET /spotify/recommendations
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Spotify recommendations request for user: {user_id}")
        
        # Get recommendations using music service with Spotify focus
        recommendations_result = await get_music_recommendations(
            user_id=user_id,
            recommendation_types=[RecommendationType.USER_BASED, RecommendationType.DISCOVER_WEEKLY],
            max_recommendations=limit
        )
        
        # Track performance
        await track_media_processing_time("spotify_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ Spotify recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Spotify recommendations failed: {str(e)}"
        )


@recommendations_router.post("/spotify/generate", response_model=RecommendationResponse)
async def generate_custom_spotify_recommendations(request: SpotifyRecommendationRequest):
    """
    Generate custom Spotify recommendations with audio feature parameters
    Matches Flask route: POST /spotify/recommendations/generate
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Custom Spotify recommendations with seeds: {request.seed_artists}")
        
        # Get Spotify service for advanced recommendation generation
        spotify_service = await get_spotify_service()
        
        # Prepare recommendation parameters
        recommendation_params = {
            "limit": request.limit,
            "seed_artists": request.seed_artists or [],
            "seed_tracks": request.seed_tracks or [],
            "seed_genres": request.seed_genres or []
        }
        
        # Add audio feature targets if provided
        if request.target_acousticness is not None:
            recommendation_params["target_acousticness"] = request.target_acousticness
        if request.target_danceability is not None:
            recommendation_params["target_danceability"] = request.target_danceability
        if request.target_energy is not None:
            recommendation_params["target_energy"] = request.target_energy
        if request.target_valence is not None:
            recommendation_params["target_valence"] = request.target_valence
        
        # Get Spotify recommendations  
        spotify_recs = await asyncio.to_thread(spotify_service.get_recommendations, **recommendation_params)
        
        # Convert to music recommendation format and find corresponding videos
        music_service = await get_music_recommendation_service()
        recommendations = []
        
        for track in spotify_recs.get('tracks', []):
            # Try to find corresponding music video
            artist_name = track['artists'][0]['name']
            track_name = track['name']
            
            # Use IMVDb to find music video
            try:
                imvdb_service = await get_imvdb_service()
                videos = await asyncio.to_thread(imvdb_service.search_videos, artist_name, track_name)
                
                video_url = videos[0].get('url') if videos else None
                thumbnail_url = videos[0].get('image', {}).get('l') if videos else None
                
                recommendations.append({
                    "video_id": videos[0].get('id', '') if videos else '',
                    "title": track_name,
                    "artist_name": artist_name,
                    "video_url": video_url,
                    "thumbnail_url": thumbnail_url,
                    "confidence": 0.9,  # High confidence from Spotify
                    "relevance_score": track.get('popularity', 50) / 100.0,
                    "recommendation_type": "spotify_custom",
                    "source": "spotify",
                    "reasons": ["Custom Spotify recommendation with audio features"],
                    "metadata": {
                        "spotify_track_id": track['id'],
                        "popularity": track.get('popularity', 0),
                        "audio_features": {
                            "danceability": track.get('audio_features', {}).get('danceability'),
                            "energy": track.get('audio_features', {}).get('energy'),
                            "valence": track.get('audio_features', {}).get('valence')
                        }
                    },
                    "timestamp": time.time()
                })
            except Exception as video_error:
                logger.warning(f"Failed to find video for {artist_name} - {track_name}: {video_error}")
        
        processing_time = time.time() - start_time
        
        # Track performance
        await track_media_processing_time("spotify_custom_recommendations_api", processing_time)
        
        return RecommendationResponse(
            recommendations=recommendations,
            total_found=len(recommendations),
            processing_time=processing_time,
            sources_used=["spotify", "imvdb"]
        )
        
    except Exception as e:
        logger.error(f"❌ Custom Spotify recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Custom recommendations failed: {str(e)}"
        )


@recommendations_router.get("/spotify/artist/{artist_id}", response_model=RecommendationResponse) 
async def get_spotify_artist_recommendations(
    artist_id: str,
    limit: int = Query(10, description="Maximum recommendations")
):
    """
    Get Spotify recommendations for specific artist
    Matches Flask route: GET /metadata-enrichment/spotify/recommendations/<artist_id>
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Spotify artist recommendations for: {artist_id}")
        
        # Get artist name from Spotify
        spotify_service = await get_spotify_service()
        artist_info = await asyncio.to_thread(spotify_service.get_artist, artist_id)
        artist_name = artist_info.get('name', '') if artist_info else artist_id
        
        # Get similar artist recommendations
        recommendations_result = await get_similar_artist_videos(artist_name, limit)
        
        # Track performance
        await track_media_processing_time("spotify_artist_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ Spotify artist recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Artist recommendations failed: {str(e)}"
        )


# Artist-Based Recommendations - Match Flask enhanced_discovery functionality
@recommendations_router.post("/artists", response_model=RecommendationResponse)
async def get_artist_recommendations(request: ArtistRecommendationRequest):
    """
    Get artist-based recommendations with multi-source support
    Matches Flask route: POST /enhanced_discovery/recommendations
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Artist recommendations for: {request.artist_name}")
        
        # Get similar artist recommendations
        recommendations_result = await get_similar_artist_videos(
            request.artist_name, 
            request.max_recommendations
        )
        
        # Track performance
        await track_media_processing_time("artist_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ Artist recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Artist recommendations failed: {str(e)}"
        )


# Genre-Based Recommendations
@recommendations_router.post("/genres", response_model=RecommendationResponse)
async def get_genre_recommendations(request: GenreRecommendationRequest):
    """
    Get genre-based music video recommendations
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Genre recommendations for: {request.genre}")
        
        # Determine recommendation types based on request
        rec_types = [RecommendationType.GENRE_BASED]
        if request.include_trending:
            rec_types.append(RecommendationType.TRENDING_VIDEOS)
        
        # Get genre-based recommendations
        recommendations_result = await get_music_recommendations(
            genre=request.genre,
            recommendation_types=rec_types,
            max_recommendations=request.max_recommendations
        )
        
        # Track performance
        await track_media_processing_time("genre_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ Genre recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Genre recommendations failed: {str(e)}"
        )


# Trending Recommendations
@recommendations_router.get("/trending", response_model=RecommendationResponse)
async def get_trending_recommendations(
    limit: int = Query(20, description="Maximum trending recommendations")
):
    """
    Get trending music video recommendations
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 Trending recommendations request")
        
        # Get trending recommendations
        recommendations_result = await get_trending_music_videos(limit)
        
        # Track performance
        await track_media_processing_time("trending_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ Trending recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"Trending recommendations failed: {str(e)}"
        )


# New Releases
@recommendations_router.get("/new-releases", response_model=RecommendationResponse)
async def get_new_release_recommendations(
    limit: int = Query(15, description="Maximum new release recommendations")
):
    """
    Get new release music video recommendations
    """
    start_time = time.time()
    
    try:
        logger.info(f"🎵 New release recommendations request")
        
        # Get new release recommendations
        recommendations_result = await get_music_recommendations(
            recommendation_types=[RecommendationType.NEW_RELEASES],
            max_recommendations=limit
        )
        
        # Track performance
        await track_media_processing_time("new_release_recommendations_api", recommendations_result.processing_time)
        
        return RecommendationResponse(
            recommendations=[rec.to_dict() for rec in recommendations_result.recommendations],
            total_found=recommendations_result.total_found,
            processing_time=recommendations_result.processing_time,
            sources_used=recommendations_result.sources_used,
            cache_hit=recommendations_result.cache_hit
        )
        
    except Exception as e:
        logger.error(f"❌ New release recommendations failed: {e}")
        return RecommendationResponse(
            recommendations=[],
            total_found=0,
            processing_time=time.time() - start_time,
            sources_used=[],
            success=False,
            message=f"New release recommendations failed: {str(e)}"
        )


# Statistics and Health Endpoints
@recommendations_router.get("/statistics", response_model=RecommendationStatsResponse)
async def get_recommendation_statistics():
    """
    Get recommendation service performance statistics
    """
    try:
        music_service = await get_music_recommendation_service()
        stats = await music_service.get_recommendation_statistics()
        
        return RecommendationStatsResponse(
            total_requests=stats["recommendation_stats"]["total_requests"],
            successful_recommendations=stats["recommendation_stats"]["successful_recommendations"],
            cache_hits=stats["recommendation_stats"]["cache_hits"],
            average_processing_time=stats["recommendation_stats"]["average_processing_time"],
            source_usage=dict(stats["recommendation_stats"]["source_usage"]),
            enabled_sources=stats["enabled_sources"]
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get recommendation statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@recommendations_router.get("/health")
async def recommendation_health_check():
    """
    Music recommendation service health check endpoint
    """
    try:
        health_status = {
            "status": "healthy",
            "services": {},
            "timestamp": time.time()
        }
        
        # Check music recommendation service
        try:
            music_service = await get_music_recommendation_service()
            stats = await music_service.get_recommendation_statistics()
            health_status["services"]["music_recommendations"] = {
                "status": "healthy",
                "total_requests": stats["recommendation_stats"]["total_requests"],
                "enabled_sources": stats["enabled_sources"]
            }
        except Exception as e:
            health_status["services"]["music_recommendations"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check external services
        for service_name, service_getter in [
            ("spotify", get_spotify_service),
            ("lastfm", get_lastfm_service),
            ("imvdb", get_imvdb_service)
        ]:
            try:
                service = await service_getter()
                health_status["services"][service_name] = {"status": "healthy"}
            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        # Determine overall health
        unhealthy_services = [
            service for service, status in health_status["services"].items()
            if status.get("status") == "unhealthy"
        ]
        
        if unhealthy_services:
            health_status["status"] = "degraded"
            health_status["unhealthy_services"] = unhealthy_services
        
        return health_status
        
    except Exception as e:
        logger.error(f"❌ Recommendation health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }


# Export the router
__all__ = ["recommendations_router"]