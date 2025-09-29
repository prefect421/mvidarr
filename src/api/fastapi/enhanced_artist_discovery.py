"""
FastAPI Enhanced Artist Discovery Router
Migrated from Flask src/api/enhanced_artist_discovery.py - Multi-source artist discovery
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.database.models import Artist
from src.services.enhanced_artist_discovery_service import (
    enhanced_artist_discovery_service,
)
from src.utils.logger import get_logger

logger = logging.getLogger("mvidarr.fastapi.enhanced_discovery")

router = APIRouter(
    prefix="/api/enhanced_discovery",
    tags=["enhanced-discovery"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class DiscoverySearchRequest(BaseModel):
    """Artist discovery search request"""

    query: str = Field(..., min_length=2, max_length=200)
    max_results: int = Field(default=50, ge=1, le=100)


class EnrichmentRequest(BaseModel):
    """Artist enrichment request"""

    artist_ids: List[int] = Field(..., min_items=1, max_items=50)


class RecommendationRequest(BaseModel):
    """Artist recommendation request"""

    artist_id: int = Field(..., ge=1)
    limit: int = Field(default=20, ge=1, le=50)


class ArtistDiscoveryResult(BaseModel):
    """Artist discovery result"""

    name: str
    source: str
    confidence: float
    genres: List[str]
    biography: Optional[str] = None
    formed_year: Optional[int] = None
    location: Optional[str] = None
    website: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    spotify_id: Optional[str] = None
    lastfm_url: Optional[str] = None
    imvdb_id: Optional[int] = None
    is_duplicate: bool = False
    existing_artist_id: Optional[int] = None


class EnrichmentResult(BaseModel):
    """Artist enrichment result"""

    artist_id: int
    name: str
    enriched_fields: List[str]
    metadata: Dict
    success: bool
    error_message: Optional[str] = None


class DiscoveryStats(BaseModel):
    """Discovery statistics"""

    total_discoveries: int
    successful_enrichments: int
    duplicate_detections: int
    sources_used: List[str]
    top_genres: List[Dict[str, int]]
    avg_confidence: float


# ========================================================================================
# ENHANCED ARTIST DISCOVERY ENDPOINTS
# ========================================================================================


@router.post("/search", response_model=List[ArtistDiscoveryResult])
async def discover_artists_multi_source(
    search_request: DiscoverySearchRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Discover artists from multiple sources with intelligent ranking

    Searches across multiple data sources (MusicBrainz, Spotify, Last.fm, etc.)
    and provides ranked results with confidence scores and duplicate detection.
    """
    try:
        user_id = current_user.get("user_id", 1)
        query = search_request.query
        max_results = search_request.max_results

        logger.info(
            f"Enhanced discovery search for '{query}' by user {current_user.get('username')}"
        )

        # Perform multi-source discovery
        discovered_artists = (
            enhanced_artist_discovery_service.discover_artists_multi_source(
                search_query=query, max_results=max_results
            )
        )

        # Convert to response format
        results = []
        for artist_metadata in discovered_artists:
            result = ArtistDiscoveryResult(
                name=artist_metadata.name,
                source=artist_metadata.source.value,
                confidence=round(artist_metadata.confidence, 3),
                genres=artist_metadata.genres or [],
                biography=(
                    artist_metadata.biography[:500] + "..."
                    if len(artist_metadata.biography or "") > 500
                    else artist_metadata.biography
                ),
                formed_year=artist_metadata.formed_year,
                location=artist_metadata.location,
                website=artist_metadata.website,
                musicbrainz_id=artist_metadata.musicbrainz_id,
                spotify_id=artist_metadata.spotify_id,
                lastfm_url=artist_metadata.lastfm_url,
                imvdb_id=artist_metadata.imvdb_id,
                is_duplicate=artist_metadata.is_duplicate,
                existing_artist_id=artist_metadata.existing_artist_id,
            )
            results.append(result)

        logger.info(f"Discovery found {len(results)} artists for query '{query}'")

        return results

    except Exception as e:
        logger.error(f"Error in multi-source artist discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrich", response_model=List[EnrichmentResult])
async def enrich_artists_metadata(
    enrichment_request: EnrichmentRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Enrich existing artists with additional metadata from external sources

    Takes a list of artist IDs and attempts to enhance their metadata
    using various external APIs and services.
    """
    try:
        user_id = current_user.get("user_id", 1)
        artist_ids = enrichment_request.artist_ids

        logger.info(
            f"Artist enrichment requested for {len(artist_ids)} artists by user {current_user.get('username')}"
        )

        # Validate that all artist IDs exist
        existing_artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
        existing_ids = {artist.id for artist in existing_artists}

        missing_ids = set(artist_ids) - existing_ids
        if missing_ids:
            raise HTTPException(
                status_code=400, detail=f"Artists not found: {list(missing_ids)}"
            )

        # Perform enrichment
        enrichment_results = enhanced_artist_discovery_service.enrich_artists_bulk(
            artist_ids=artist_ids, user_id=user_id
        )

        # Convert to response format
        results = []
        for enrichment_data in enrichment_results:
            result = EnrichmentResult(
                artist_id=enrichment_data.artist_id,
                name=enrichment_data.artist_name,
                enriched_fields=enrichment_data.enriched_fields or [],
                metadata=enrichment_data.metadata or {},
                success=enrichment_data.success,
                error_message=enrichment_data.error_message,
            )
            results.append(result)

        successful_count = sum(1 for r in results if r.success)
        logger.info(
            f"Enrichment completed: {successful_count}/{len(results)} successful"
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in artist enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates")
async def detect_duplicate_artists(
    threshold: float = Query(default=0.8, ge=0.0, le=1.0),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Detect potential duplicate artists in the database

    Uses fuzzy matching and metadata comparison to identify
    artists that might be duplicates of each other.
    """
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Duplicate detection requested with threshold {threshold} by user {current_user.get('username')}"
        )

        # Detect duplicates using service
        duplicate_groups = enhanced_artist_discovery_service.detect_duplicate_artists(
            similarity_threshold=threshold
        )

        # Format response
        results = []
        total_duplicates = 0

        for group in duplicate_groups:
            duplicate_info = {
                "primary_artist": {
                    "id": group.primary_artist.id,
                    "name": group.primary_artist.name,
                    "video_count": group.primary_artist_video_count,
                },
                "duplicates": [],
                "similarity_scores": group.similarity_scores,
                "merge_recommendation": group.merge_recommendation,
            }

            for duplicate_artist in group.duplicate_artists:
                duplicate_info["duplicates"].append(
                    {
                        "id": duplicate_artist.id,
                        "name": duplicate_artist.name,
                        "video_count": getattr(duplicate_artist, "video_count", 0),
                    }
                )

            results.append(duplicate_info)
            total_duplicates += len(group.duplicate_artists)

        logger.info(
            f"Duplicate detection found {len(results)} groups with {total_duplicates} potential duplicates"
        )

        return {
            "duplicate_groups": results,
            "summary": {
                "total_groups": len(results),
                "total_potential_duplicates": total_duplicates,
                "threshold_used": threshold,
            },
        }

    except Exception as e:
        logger.error(f"Error in duplicate detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations", response_model=List[ArtistDiscoveryResult])
async def get_artist_recommendations(
    recommendation_request: RecommendationRequest,
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Get artist recommendations based on an existing artist

    Uses similarity analysis and external APIs to suggest
    related artists that the user might be interested in.
    """
    try:
        user_id = current_user.get("user_id", 1)
        artist_id = recommendation_request.artist_id
        limit = recommendation_request.limit

        # Verify artist exists
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        logger.info(
            f"Recommendations requested for artist '{artist.name}' (ID: {artist_id}) by user {current_user.get('username')}"
        )

        # Get recommendations using service
        recommended_artists = (
            enhanced_artist_discovery_service.get_artist_recommendations(
                artist_id=artist_id, limit=limit, user_id=user_id
            )
        )

        # Convert to response format
        results = []
        for artist_metadata in recommended_artists:
            result = ArtistDiscoveryResult(
                name=artist_metadata.name,
                source=artist_metadata.source.value,
                confidence=round(artist_metadata.confidence, 3),
                genres=artist_metadata.genres or [],
                biography=(
                    artist_metadata.biography[:300] + "..."
                    if len(artist_metadata.biography or "") > 300
                    else artist_metadata.biography
                ),
                formed_year=artist_metadata.formed_year,
                location=artist_metadata.location,
                website=artist_metadata.website,
                musicbrainz_id=artist_metadata.musicbrainz_id,
                spotify_id=artist_metadata.spotify_id,
                lastfm_url=artist_metadata.lastfm_url,
                imvdb_id=artist_metadata.imvdb_id,
                is_duplicate=False,  # Recommendations are filtered for duplicates
                existing_artist_id=artist_metadata.existing_artist_id,
            )
            results.append(result)

        logger.info(
            f"Generated {len(results)} recommendations for artist '{artist.name}'"
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting artist recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=DiscoveryStats)
async def get_discovery_statistics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """
    Get enhanced artist discovery statistics

    Provides insights into discovery performance, source usage,
    and enrichment success rates over the specified time period.
    """
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Discovery statistics requested for {days} days by user {current_user.get('username')}"
        )

        # Get statistics using service
        stats_data = enhanced_artist_discovery_service.get_discovery_statistics(
            days=days, user_id=user_id
        )

        return DiscoveryStats(
            total_discoveries=stats_data.get("total_discoveries", 0),
            successful_enrichments=stats_data.get("successful_enrichments", 0),
            duplicate_detections=stats_data.get("duplicate_detections", 0),
            sources_used=stats_data.get("sources_used", []),
            top_genres=stats_data.get("top_genres", []),
            avg_confidence=stats_data.get("avg_confidence", 0.0),
        )

    except Exception as e:
        logger.error(f"Error getting discovery statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
