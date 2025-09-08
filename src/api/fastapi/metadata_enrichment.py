"""
FastAPI Metadata Enrichment Router
Exposes metadata enrichment services through REST API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
import asyncio
import logging

from src.database.connection import get_db_session
from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.metadata_enrichment")

# Create router
router = APIRouter(prefix="/api/metadata-enrichment", tags=["metadata-enrichment"])

# Import services with error handling
try:
    from src.services.lastfm_service import lastfm_service
except ImportError:
    logger.warning("LastFM service not available")
    lastfm_service = None

try:
    from src.services.async_spotify_service import spotify_service
except ImportError:
    logger.warning("Spotify service not available")
    spotify_service = None

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


@router.get("/search/lastfm")
async def search_lastfm(
    artist: str = Query(..., description="Artist name to search"),
    current_user: dict = Depends(require_authentication)
):
    """Search Last.fm for artist information"""
    try:
        if not lastfm_service:
            raise HTTPException(status_code=503, detail="Last.fm service not available")
        
        logger.info(f"Searching Last.fm for artist: {artist}")
        result = await asyncio.to_thread(lastfm_service.search_artist, artist)
        
        if not result:
            return {"results": [], "total": 0}
            
        return {
            "results": result if isinstance(result, list) else [result],
            "total": len(result) if isinstance(result, list) else 1,
            "service": "lastfm"
        }
        
    except Exception as e:
        logger.error(f"Last.fm search error for '{artist}': {e}")
        raise HTTPException(status_code=500, detail=f"Last.fm search failed: {str(e)}")


@router.get("/search/spotify")
async def search_spotify(
    artist: str = Query(..., description="Artist name to search"),
    limit: int = Query(10, description="Number of results to return"),
    current_user: dict = Depends(require_authentication)
):
    """Search Spotify for artist information"""
    try:
        if not spotify_service:
            raise HTTPException(status_code=503, detail="Spotify service not available")
            
        logger.info(f"Searching Spotify for artist: {artist}")
        result = await spotify_service.search_artists(artist, limit=limit)
        
        if not result or not result.get('artists', {}).get('items'):
            return {"results": [], "total": 0}
            
        artists = result['artists']['items']
        return {
            "results": artists,
            "total": len(artists),
            "service": "spotify"
        }
        
    except Exception as e:
        logger.error(f"Spotify search error for '{artist}': {e}")
        raise HTTPException(status_code=500, detail=f"Spotify search failed: {str(e)}")


@router.post("/search/musicbrainz")
async def search_musicbrainz(
    data: Dict[str, Any],
    current_user: dict = Depends(require_authentication)
):
    """Search MusicBrainz for artist information"""
    try:
        if not musicbrainz_service:
            raise HTTPException(status_code=503, detail="MusicBrainz service not available")
            
        artist = data.get('artist')
        if not artist:
            raise HTTPException(status_code=400, detail="Artist name required")
            
        logger.info(f"Searching MusicBrainz for artist: {artist}")
        result = await asyncio.to_thread(musicbrainz_service.search_artist, artist)
        
        if not result:
            return {"results": [], "total": 0}
            
        return {
            "results": result if isinstance(result, list) else [result],
            "total": len(result) if isinstance(result, list) else 1,
            "service": "musicbrainz"
        }
        
    except Exception as e:
        logger.error(f"MusicBrainz search error for '{data.get('artist', 'unknown')}': {e}")
        raise HTTPException(status_code=500, detail=f"MusicBrainz search failed: {str(e)}")


@router.get("/search/allmusic")
async def search_allmusic(
    artist: str = Query(..., description="Artist name to search"),
    current_user: dict = Depends(require_authentication)
):
    """Search AllMusic for artist information"""
    try:
        if not allmusic_service:
            raise HTTPException(status_code=503, detail="AllMusic service not available")
            
        logger.info(f"Searching AllMusic for artist: {artist}")
        result = await asyncio.to_thread(allmusic_service.search_artist, artist)
        
        if not result:
            return {"results": [], "total": 0}
            
        return {
            "results": result if isinstance(result, list) else [result],
            "total": len(result) if isinstance(result, list) else 1,
            "service": "allmusic"
        }
        
    except Exception as e:
        logger.error(f"AllMusic search error for '{artist}': {e}")
        raise HTTPException(status_code=500, detail=f"AllMusic search failed: {str(e)}")


@router.get("/search/wikipedia")
async def search_wikipedia(
    artist: str = Query(..., description="Artist name to search"),
    current_user: dict = Depends(require_authentication)
):
    """Search Wikipedia for artist information"""
    try:
        if not wikipedia_service:
            raise HTTPException(status_code=503, detail="Wikipedia service not available")
            
        logger.info(f"Searching Wikipedia for artist: {artist}")
        result = await asyncio.to_thread(wikipedia_service.search_artist, artist)
        
        if not result:
            return {"results": [], "total": 0}
            
        return {
            "results": result if isinstance(result, list) else [result],
            "total": len(result) if isinstance(result, list) else 1,
            "service": "wikipedia"
        }
        
    except Exception as e:
        logger.error(f"Wikipedia search error for '{artist}': {e}")
        raise HTTPException(status_code=500, detail=f"Wikipedia search failed: {str(e)}")


@router.get("/search/imvdb")
async def search_imvdb(
    artist: str = Query(..., description="Artist name to search"),
    current_user: dict = Depends(require_authentication)
):
    """Search IMVDb for artist information"""
    try:
        if not imvdb_service:
            raise HTTPException(status_code=503, detail="IMVDb service not available")
            
        logger.info(f"Searching IMVDb for artist: {artist}")
        result = await asyncio.to_thread(imvdb_service.search_artist, artist)
        
        if not result:
            return {"results": [], "total": 0}
            
        return {
            "results": result if isinstance(result, list) else [result],
            "total": len(result) if isinstance(result, list) else 1,
            "service": "imvdb"
        }
        
    except Exception as e:
        logger.error(f"IMVDb search error for '{artist}': {e}")
        raise HTTPException(status_code=500, detail=f"IMVDb search failed: {str(e)}")


@router.post("/enrich/artist/{artist_id}")
async def enrich_artist_metadata(
    artist_id: int,
    data: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session)
):
    """Enrich metadata for a specific artist"""
    try:
        # Import metadata enrichment service
        from src.services.metadata_enrichment_service import metadata_enrichment_service
        
        # Get artist from database
        from src.database.models import Artist
        artist = session.query(Artist).filter(Artist.id == artist_id).first()
        
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")
        
        force_refresh = data.get("force_refresh", False) if data else False
        enrich_videos = data.get("enrich_videos", True) if data else True
        
        logger.info(f"Enriching metadata for artist {artist_id}: {artist.name}")
        
        # Run enrichment in background thread
        result = await asyncio.to_thread(
            metadata_enrichment_service.enrich_artist_metadata,
            artist,
            session,
            force_refresh=force_refresh
        )
        
        return {
            "message": f"Metadata enrichment completed for {artist.name}",
            "artist_id": artist_id,
            "result": result,
            "force_refresh": force_refresh,
            "enrich_videos": enrich_videos
        }
        
    except Exception as e:
        logger.error(f"Artist metadata enrichment error for ID {artist_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Metadata enrichment failed: {str(e)}")


@router.get("/services/status")
async def get_services_status(
    current_user: dict = Depends(require_authentication)
):
    """Get status of all metadata enrichment services"""
    services = {
        "lastfm": lastfm_service is not None,
        "spotify": spotify_service is not None,
        "musicbrainz": musicbrainz_service is not None,
        "allmusic": allmusic_service is not None,
        "wikipedia": wikipedia_service is not None,
        "imvdb": imvdb_service is not None
    }
    
    return {
        "services": services,
        "available_services": [name for name, available in services.items() if available],
        "unavailable_services": [name for name, available in services.items() if not available],
        "total_services": len(services),
        "available_count": sum(services.values())
    }