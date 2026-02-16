"""
FastAPI Metadata Enrichment - Analytics Module
Analytics and statistics endpoints (stats, services status, candidates, validation, duplicates)
"""

import asyncio
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.metadata_enrichment.analytics")

# Create router for analytics endpoints
router = APIRouter()

# Import services with error handling (for services status endpoint)
try:
    from src.services.lastfm_service import lastfm_service
except ImportError:
    logger.warning("LastFM service not available")
    lastfm_service = None

try:
    from src.services.async_spotify_service import get_async_spotify_service

    spotify_service = None  # Will be instantiated when needed
except ImportError:
    logger.warning("Spotify service not available")
    get_async_spotify_service = None

try:
    from src.services.musicbrainz_service import musicbrainz_service
except ImportError:
    logger.warning("MusicBrainz service not available")
    musicbrainz_service = None

try:
    from src.services.allmusic_service import allmusic_service
except ImportError:
    logger.warning("AllMusic service not available")
    allmusic_service = None

try:
    from src.services.wikipedia_service import wikipedia_service
except ImportError:
    logger.warning("Wikipedia service not available")
    wikipedia_service = None

try:
    from src.services.imvdb_service import imvdb_service
except ImportError:
    logger.warning("IMVDb service not available")
    imvdb_service = None


@router.get("/stats")
async def get_enrichment_stats(current_user: dict = Depends(require_authentication)):
    """Get metadata enrichment statistics"""
    try:
        from src.services.metadata_enrichment_service import metadata_enrichment_service

        stats = metadata_enrichment_service.get_enrichment_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get enrichment stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/services/status")
async def get_services_status(current_user: dict = Depends(require_authentication)):
    """Get status of all metadata enrichment services"""
    services = {
        "lastfm": lastfm_service is not None,
        "spotify": spotify_service is not None,
        "musicbrainz": musicbrainz_service is not None,
        "allmusic": allmusic_service is not None,
        "wikipedia": wikipedia_service is not None,
        "imvdb": imvdb_service is not None,
    }

    return {
        "services": services,
        "available_services": [
            name for name, available in services.items() if available
        ],
        "unavailable_services": [
            name for name, available in services.items() if not available
        ],
        "total_services": len(services),
        "available_count": sum(services.values()),
    }


@router.get("/candidates")
async def get_enrichment_candidates(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    missing_external_ids: bool = Query(True),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get artists that are candidates for metadata enrichment"""
    try:
        from src.database.models import Artist

        # Build query for candidates
        query = session.query(Artist)

        if missing_external_ids:
            query = query.filter(
                (Artist.spotify_id.is_(None))
                | (Artist.spotify_id == "")
                | (Artist.lastfm_name.is_(None))
                | (Artist.lastfm_name == "")
                | (Artist.imvdb_id.is_(None))
                | (Artist.imvdb_id == "")
            )

        # Get total count
        total = query.count()

        # Get artists with pagination
        artists = query.offset(offset).limit(limit).all()

        candidates = []
        for artist in artists:
            # Determine what's missing
            missing_ids = []
            if not artist.spotify_id or (
                isinstance(artist.spotify_id, str) and not artist.spotify_id.strip()
            ):
                missing_ids.append("spotify_id")
            if not artist.lastfm_name or (
                isinstance(artist.lastfm_name, str) and not artist.lastfm_name.strip()
            ):
                missing_ids.append("lastfm_name")
            if not artist.imvdb_id or (
                isinstance(artist.imvdb_id, str) and not artist.imvdb_id.strip()
            ):
                missing_ids.append("imvdb_id")

            # Check for musicbrainz_id in imvdb_metadata
            musicbrainz_id = None
            if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
                musicbrainz_id = artist.imvdb_metadata.get("musicbrainz_id")
            if not musicbrainz_id or (
                isinstance(musicbrainz_id, str) and not musicbrainz_id.strip()
            ):
                missing_ids.append("musicbrainz_id")

            # Calculate metadata age
            metadata_age = None
            if artist.updated_at:
                metadata_age = (datetime.utcnow() - artist.updated_at).days

            candidates.append(
                {
                    "id": artist.id,
                    "name": artist.name,
                    "missing_external_ids": missing_ids,
                    "metadata_age_days": metadata_age,
                    "video_count": (
                        len(artist.videos) if hasattr(artist, "videos") else 0
                    ),
                }
            )

        return {
            "candidates": candidates,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get enrichment candidates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/validation/report")
async def get_validation_report(
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(require_authentication),
):
    """Get a comprehensive validation report"""
    try:
        from src.services.metadata_validation_service import metadata_validation_service

        report = metadata_validation_service.get_validation_report(limit)
        return report
    except Exception as e:
        logger.error(f"Failed to generate validation report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/duplicates/candidates")
async def get_duplicate_candidates(
    limit: int = Query(50, ge=1, le=500),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    current_user: dict = Depends(require_authentication),
):
    """Get potential duplicate artist candidates"""
    try:
        from src.services.duplicate_detection_service import duplicate_detection_service

        candidates = duplicate_detection_service.find_duplicate_candidates(limit)

        # Filter by minimum confidence
        filtered_candidates = [
            c for c in candidates if c.match_confidence >= min_confidence
        ]

        results = []
        for candidate in filtered_candidates:
            results.append(
                {
                    "artist1_id": candidate.artist1_id,
                    "artist2_id": candidate.artist2_id,
                    "artist1_name": candidate.artist1_name,
                    "artist2_name": candidate.artist2_name,
                    "match_confidence": candidate.match_confidence,
                    "match_reason": candidate.match_reason,
                }
            )

        return {
            "candidates": results,
            "total_found": len(filtered_candidates),
            "min_confidence": min_confidence,
        }

    except Exception as e:
        logger.error(f"Failed to get duplicate candidates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/enrich/{artist_id}")
async def enrich_single_artist(
    artist_id: int,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enrich metadata for a single artist"""
    try:
        from src.database.models import Artist

        # Get the artist
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        if not artist:
            raise HTTPException(
                status_code=404, detail=f"Artist with ID {artist_id} not found"
            )

        logger.info(f"Starting enrichment for artist: {artist.name} (ID: {artist_id})")

        # Track what was updated
        updated_fields = []
        matches_found = {
            "spotify": False,
            "lastfm": False,
            "musicbrainz": False,
            "imvdb": False,
        }

        # Spotify enrichment
        if not artist.spotify_id or (
            isinstance(artist.spotify_id, str) and not artist.spotify_id.strip()
        ):
            try:
                if spotify_service:
                    spotify_result = await asyncio.to_thread(
                        spotify_service.search_artist, artist.name
                    )
                    if spotify_result and isinstance(spotify_result, dict):
                        spotify_id = spotify_result.get("id")
                        if spotify_id:
                            artist.spotify_id = spotify_id
                            matches_found["spotify"] = True
                            updated_fields.append("spotify_id")
                            logger.info(
                                f"Found Spotify match for {artist.name}: {spotify_id}"
                            )
            except Exception as e:
                logger.warning(f"Spotify enrichment failed for {artist.name}: {e}")

        # Last.fm enrichment
        if not artist.lastfm_name or (
            isinstance(artist.lastfm_name, str) and not artist.lastfm_name.strip()
        ):
            try:
                if lastfm_service:
                    lastfm_result = await asyncio.to_thread(
                        lastfm_service.search_artist, artist.name
                    )
                    if lastfm_result and isinstance(lastfm_result, dict):
                        lastfm_name = lastfm_result.get("name")
                        if lastfm_name:
                            artist.lastfm_name = lastfm_name
                            matches_found["lastfm"] = True
                            updated_fields.append("lastfm_name")
                            logger.info(
                                f"Found Last.fm match for {artist.name}: {lastfm_name}"
                            )
            except Exception as e:
                logger.warning(f"Last.fm enrichment failed for {artist.name}: {e}")

        # MusicBrainz enrichment
        existing_mbid = None
        if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
            existing_mbid = artist.imvdb_metadata.get("musicbrainz_id")

        if not existing_mbid:
            try:
                if musicbrainz_service:
                    mb_result = await asyncio.to_thread(
                        musicbrainz_service.search_artist, artist.name
                    )
                    if mb_result and isinstance(mb_result, dict):
                        mb_id = (
                            mb_result.get("mbid")
                            or mb_result.get("id")
                            or mb_result.get("musicbrainz_id")
                        )
                        if mb_id:
                            if not artist.imvdb_metadata:
                                artist.imvdb_metadata = {}
                            artist.imvdb_metadata["musicbrainz_id"] = mb_id
                            matches_found["musicbrainz"] = True
                            updated_fields.append("musicbrainz_id")
                            logger.info(
                                f"Found MusicBrainz match for {artist.name}: {mb_id}"
                            )
            except Exception as e:
                logger.warning(f"MusicBrainz enrichment failed for {artist.name}: {e}")

        # IMVDb enrichment
        if not artist.imvdb_id or (
            isinstance(artist.imvdb_id, str) and not artist.imvdb_id.strip()
        ):
            try:
                if imvdb_service:
                    imvdb_result = await asyncio.to_thread(
                        imvdb_service.search_artist, artist.name
                    )
                    if imvdb_result and isinstance(imvdb_result, dict):
                        imvdb_id = imvdb_result.get("id") or imvdb_result.get(
                            "imvdb_id"
                        )
                        if imvdb_id:
                            artist.imvdb_id = str(imvdb_id)
                            matches_found["imvdb"] = True
                            updated_fields.append("imvdb_id")
                            logger.info(
                                f"Found IMVDb match for {artist.name}: {imvdb_id}"
                            )
            except Exception as e:
                logger.warning(f"IMVDb enrichment failed for {artist.name}: {e}")

        # Update the artist record if any fields were updated
        if updated_fields:
            artist.updated_at = datetime.utcnow()
            session.commit()
            logger.info(
                f"Successfully enriched {artist.name} with fields: {', '.join(updated_fields)}"
            )
        else:
            logger.info(f"No new enrichment data found for {artist.name}")

        return {
            "success": True,
            "artist_id": artist_id,
            "artist_name": artist.name,
            "updated_fields": updated_fields,
            "matches_found": matches_found,
            "message": f"Enrichment completed for {artist.name}. Updated {len(updated_fields)} field(s).",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enrich artist {artist_id}: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {str(e)}")
