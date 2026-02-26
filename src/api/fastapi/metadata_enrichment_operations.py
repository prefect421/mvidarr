"""
FastAPI Metadata Enrichment - Operations Module
Enrichment operation endpoints (enrich artist, auto-match, enrich video, batch enrich)
"""

import asyncio
import base64
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, attributes

from src.database.connection import get_db_session
from src.middleware.fastapi_auth_middleware import require_authentication
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.metadata_enrichment.operations")

# Create router for operation endpoints
router = APIRouter()

# Import services with error handling
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


@router.post("/enrich/artist/{artist_id}")
async def enrich_artist_metadata(
    artist_id: int,
    background_tasks: BackgroundTasks,
    data: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enrich metadata for a specific artist using Celery background jobs"""
    try:
        # Get artist from database
        from src.database.models import Artist

        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        force_refresh = data.get("force_refresh", False) if data else False
        enrich_videos = data.get("enrich_videos", True) if data else True
        artist_name = artist.name

        logger.info(f"Enriching metadata for artist {artist_id}: {artist_name}")

        # Import Celery task
        from src.jobs.metadata_tasks import enrich_artist_metadata_task

        try:
            # Wrap synchronous .delay() in thread to avoid blocking the event loop
            task_result = await asyncio.to_thread(
                enrich_artist_metadata_task.delay,
                artist_id=artist_id,
                force_refresh=force_refresh,
                enrich_videos=enrich_videos,
            )

            logger.info(
                f"Started Celery metadata enrichment task {task_result.id} for {artist_name}"
            )

            return {
                "job_id": task_result.id,
                "message": f"Metadata enrichment job started for {artist_name}",
                "artist_id": artist_id,
                "status": "queued",
                "force_refresh": force_refresh,
                "enrich_videos": enrich_videos,
                "note": "Background processing initiated with Celery + Redis",
                "task_name": "metadata.enrich_artist",
            }

        except Exception as celery_error:
            # Celery unavailable — run enrichment directly in background
            logger.warning(
                f"Celery unavailable for enrichment, running directly: {celery_error}"
            )
            task_id = str(uuid.uuid4())
            background_tasks.add_task(
                _enrich_artist_direct, artist_id, force_refresh, task_id
            )
            return {
                "job_id": task_id,
                "message": f"Metadata enrichment started for {artist_name} (direct mode)",
                "artist_id": artist_id,
                "status": "queued",
                "force_refresh": force_refresh,
                "enrich_videos": enrich_videos,
                "note": "Running directly — Celery unavailable",
                "task_name": "metadata.enrich_artist",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Artist metadata enrichment error for ID {artist_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Metadata enrichment failed: {str(e)}"
        )


def _write_direct_job_progress(
    task_id: str, progress: int, message: str, status: str = "PROGRESS"
) -> None:
    """Write progress to Redis so /api/jobs/{job_id} can surface it for direct-run jobs"""
    try:
        import json
        from datetime import datetime

        from src.jobs.redis_manager import redis_manager

        if not redis_manager.ensure_connection():
            return
        data = {
            "progress": progress,
            "percent": progress,
            "message": message,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        redis_manager.redis_client.setex(
            f"job_progress:{task_id}", 3600, json.dumps(data)
        )
    except Exception as e:
        logger.warning(f"Could not write direct job progress to Redis: {e}")


async def _enrich_artist_direct(
    artist_id: int, force_refresh: bool, task_id: str = ""
) -> None:
    """Fallback: run metadata enrichment directly without Celery"""
    _write_direct_job_progress(task_id, 5, "Initializing enrichment...")
    try:
        from src.services.metadata_enrichment_service import MetadataEnrichmentService

        logger.info(f"Direct metadata enrichment started for artist {artist_id}")
        _write_direct_job_progress(
            task_id, 25, "Gathering metadata from external sources..."
        )
        service = MetadataEnrichmentService()
        await service.enrich_artist_metadata(artist_id, force_refresh=force_refresh)
        _write_direct_job_progress(
            task_id, 100, "Enrichment completed", status="SUCCESS"
        )
        logger.info(f"Direct metadata enrichment completed for artist {artist_id}")
    except Exception as e:
        logger.error(f"Direct metadata enrichment failed for artist {artist_id}: {e}")
        _write_direct_job_progress(
            task_id, 0, f"Enrichment failed: {e}", status="FAILURE"
        )


async def _enrich_video_direct(
    video_id: int, force_refresh: bool, task_id: str = ""
) -> None:
    """Fallback: run video metadata enrichment directly without Celery"""
    _write_direct_job_progress(task_id, 5, "Initializing video enrichment...")
    try:
        from src.services.metadata_enrichment_service import MetadataEnrichmentService

        logger.info(f"Direct video metadata enrichment started for video {video_id}")
        _write_direct_job_progress(task_id, 25, "Gathering video metadata...")
        service = MetadataEnrichmentService()
        await service.enrich_video_metadata(video_id, force_refresh=force_refresh)
        _write_direct_job_progress(
            task_id, 100, "Video enrichment completed", status="SUCCESS"
        )
        logger.info(f"Direct video metadata enrichment completed for video {video_id}")
    except Exception as e:
        logger.error(
            f"Direct video metadata enrichment failed for video {video_id}: {e}"
        )
        _write_direct_job_progress(
            task_id, 0, f"Video enrichment failed: {e}", status="FAILURE"
        )


@router.get("/auto-match/{artist_id}")
async def auto_match_services(
    artist_id: int,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Auto-match artist with external services as background job"""
    try:
        from src.database.models import Artist

        artist = session.query(Artist).filter(Artist.id == artist_id).first()

        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        # Generate a job ID for tracking
        job_id = str(uuid.uuid4())
        logger.info(
            f"Starting auto-match job {job_id} for artist {artist_id}: {artist.name}"
        )

        matches_found = {
            "spotify": False,
            "lastfm": False,
            "musicbrainz": False,
            "imvdb": False,
            "allmusic": False,
            "wikipedia": False,
        }

        # Try to match with available services and save results
        updated_fields = []

        logger.info(f"🔍 Checking artist current service IDs:")
        logger.info(f"  - Spotify ID: {artist.spotify_id}")
        logger.info(f"  - Last.fm name: {artist.lastfm_name}")
        logger.info(f"  - IMVDb ID: {artist.imvdb_id}")
        logger.info(f"  - imvdb_metadata: {artist.imvdb_metadata}")

        # Spotify auto-match
        if get_async_spotify_service and not artist.spotify_id:
            try:
                logger.info(f"🎵 Attempting Spotify search for: {artist.name}")

                # Use direct HTTP request instead of the complex service for auto-match
                from src.services.settings_service import settings
                from src.utils.async_http_client import get_global_http_client

                # Get credentials directly
                client_id = settings.get("spotify_client_id")
                client_secret = settings.get("spotify_client_secret")

                if not client_id or not client_secret:
                    logger.warning(f"🎵 ❌ Spotify credentials not configured")
                    raise ValueError("Spotify client credentials not configured")

                logger.info(f"🎵 Getting Spotify access token...")

                # Get access token using client credentials flow
                credentials = f"{client_id}:{client_secret}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()

                http_client = await get_global_http_client()

                # Get access token
                token_response = await asyncio.wait_for(
                    http_client.post(
                        "https://accounts.spotify.com/api/token",
                        headers={
                            "Authorization": f"Basic {encoded_credentials}",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={"grant_type": "client_credentials"},
                    ),
                    timeout=15.0,
                )

                access_token = token_response.get("access_token")
                if not access_token:
                    logger.warning(f"🎵 ❌ Failed to get Spotify access token")
                    raise ValueError("Failed to get Spotify access token")

                logger.info(f"🎵 Got access token, searching for artist...")

                # Search for artist
                search_response = await asyncio.wait_for(
                    http_client.get(
                        "https://api.spotify.com/v1/search",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"q": artist.name, "type": "artist", "limit": 1},
                    ),
                    timeout=15.0,
                )

                logger.info(f"🎵 Search completed successfully")

                if search_response and search_response.get("artists", {}).get("items"):
                    spotify_artist = search_response["artists"]["items"][0]
                    logger.info(
                        f"🎵 Found Spotify artist: {spotify_artist.get('name')} (ID: {spotify_artist.get('id')})"
                    )
                    artist.spotify_id = spotify_artist["id"]
                    matches_found["spotify"] = True
                    updated_fields.append("spotify_id")
                    logger.info(
                        f"🎵 ✅ Found and saved Spotify match for {artist.name}: {spotify_artist['id']}"
                    )
                else:
                    logger.info(f"🎵 ❌ No Spotify results found for {artist.name}")

            except asyncio.TimeoutError:
                logger.warning(
                    f"🎵 ⏰ Spotify auto-match timed out for {artist.name} (API request timeout)"
                )
            except ValueError as e:
                if "client credentials" in str(e).lower():
                    logger.warning(
                        f"🎵 ❌ Spotify auto-match failed for {artist.name}: Missing API credentials. Please configure spotify_client_id and spotify_client_secret in settings."
                    )
                else:
                    logger.warning(
                        f"🎵 ❌ Spotify auto-match failed for {artist.name}: {e}"
                    )
            except Exception as e:
                logger.warning(
                    f"🎵 ❌ Spotify auto-match failed for {artist.name}: {e}"
                )
                import traceback

                traceback.print_exc()

        # Last.fm auto-match
        if lastfm_service and not artist.lastfm_name:
            try:
                lastfm_result = await asyncio.to_thread(
                    lastfm_service.search_artist, artist.name
                )
                if lastfm_result and isinstance(lastfm_result, dict):
                    # Extract Last.fm artist name from result
                    lastfm_name = lastfm_result.get("name") or lastfm_result.get(
                        "artist_name"
                    )
                    if lastfm_name:
                        artist.lastfm_name = lastfm_name
                        matches_found["lastfm"] = True
                        updated_fields.append("lastfm_name")
                        logger.info(
                            f"Found and saved Last.fm match for {artist.name}: {lastfm_name}"
                        )
                elif (
                    lastfm_result and isinstance(lastfm_result, list) and lastfm_result
                ):
                    # Handle list result
                    lastfm_name = (
                        lastfm_result[0].get("name")
                        if isinstance(lastfm_result[0], dict)
                        else str(lastfm_result[0])
                    )
                    if lastfm_name:
                        artist.lastfm_name = lastfm_name
                        matches_found["lastfm"] = True
                        updated_fields.append("lastfm_name")
                        logger.info(
                            f"Found and saved Last.fm match for {artist.name}: {lastfm_name}"
                        )
            except Exception as e:
                logger.warning(f"Last.fm auto-match failed for {artist.name}: {e}")

        # MusicBrainz auto-match
        if musicbrainz_service:
            try:
                mb_result = await asyncio.to_thread(
                    musicbrainz_service.search_artist, artist.name
                )

                # Check if MusicBrainz ID already exists
                existing_mbid = None
                if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
                    existing_mbid = artist.imvdb_metadata.get("musicbrainz_id")

                if mb_result and isinstance(mb_result, dict):
                    mb_id = (
                        mb_result.get("mbid")
                        or mb_result.get("id")
                        or mb_result.get("musicbrainz_id")
                    )
                    if mb_id and not existing_mbid:
                        # Initialize imvdb_metadata if it doesn't exist
                        if not artist.imvdb_metadata:
                            artist.imvdb_metadata = {}
                        artist.imvdb_metadata["musicbrainz_id"] = mb_id
                        matches_found["musicbrainz"] = True
                        updated_fields.append("musicbrainz_id")
                        logger.info(
                            f"Found and saved MusicBrainz match for {artist.name}: {mb_id}"
                        )
                elif mb_result and isinstance(mb_result, list) and mb_result:
                    # Handle list result - get first match with highest confidence
                    best_match = None
                    for result in mb_result:
                        if isinstance(result, dict):
                            mb_id = (
                                result.get("mbid")
                                or result.get("id")
                                or result.get("musicbrainz_id")
                            )
                            confidence = result.get("confidence", 0)
                            if mb_id and (
                                not best_match
                                or confidence > best_match.get("confidence", 0)
                            ):
                                best_match = {
                                    "id": mb_id,
                                    "confidence": confidence,
                                    "name": result.get("name"),
                                }

                    if best_match and not existing_mbid:
                        mb_id = best_match["id"]
                        # Initialize imvdb_metadata if it doesn't exist
                        if not artist.imvdb_metadata:
                            artist.imvdb_metadata = {}
                        artist.imvdb_metadata["musicbrainz_id"] = mb_id
                        matches_found["musicbrainz"] = True
                        updated_fields.append("musicbrainz_id")
                        logger.info(
                            f"Found and saved MusicBrainz match for {artist.name}: {mb_id} (confidence: {best_match.get('confidence', 'unknown')})"
                        )
            except Exception as e:
                logger.warning(f"MusicBrainz auto-match failed for {artist.name}: {e}")

        # IMVDb auto-match
        if imvdb_service and not artist.imvdb_id:
            try:
                imvdb_result = await asyncio.to_thread(
                    imvdb_service.search_artist, artist.name
                )
                if imvdb_result and isinstance(imvdb_result, dict):
                    imvdb_id = imvdb_result.get("id") or imvdb_result.get("imvdb_id")
                    if imvdb_id:
                        artist.imvdb_id = imvdb_id
                        matches_found["imvdb"] = True
                        updated_fields.append("imvdb_id")
                        logger.info(
                            f"Found and saved IMVDb match for {artist.name}: {imvdb_id}"
                        )
                elif imvdb_result and isinstance(imvdb_result, list) and imvdb_result:
                    # Handle list result
                    imvdb_id = (
                        imvdb_result[0].get("id")
                        if isinstance(imvdb_result[0], dict)
                        else None
                    )
                    if imvdb_id:
                        artist.imvdb_id = imvdb_id
                        matches_found["imvdb"] = True
                        updated_fields.append("imvdb_id")
                        logger.info(
                            f"Found and saved IMVDb match for {artist.name}: {imvdb_id}"
                        )
            except Exception as e:
                logger.warning(f"IMVDb auto-match failed for {artist.name}: {e}")

        # AllMusic auto-match
        if allmusic_service:
            try:
                # Check if AllMusic ID already exists
                existing_allmusic_id = None
                if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
                    existing_allmusic_id = artist.imvdb_metadata.get("allmusic_id")

                if not existing_allmusic_id:
                    allmusic_result = await asyncio.to_thread(
                        allmusic_service.search_artist, artist.name
                    )
                    if allmusic_result and isinstance(allmusic_result, dict):
                        allmusic_url = allmusic_result.get("url")
                        if allmusic_url:
                            # Extract AllMusic ID from URL (format: /artist/artist-name-mn[id])
                            id_match = re.search(r"mn(\d+)", allmusic_url)
                            if id_match:
                                allmusic_id = id_match.group(1)
                                # Initialize imvdb_metadata if it doesn't exist
                                if not artist.imvdb_metadata:
                                    artist.imvdb_metadata = {}
                                artist.imvdb_metadata["allmusic_id"] = allmusic_id
                                matches_found["allmusic"] = True
                                updated_fields.append("allmusic_id")
                                logger.info(
                                    f"Found and saved AllMusic match for {artist.name}: {allmusic_id}"
                                )
            except Exception as e:
                logger.warning(f"AllMusic auto-match failed for {artist.name}: {e}")

        # Wikipedia auto-match
        if wikipedia_service:
            try:
                logger.info(f"📖 Attempting Wikipedia search for: {artist.name}")

                # Check if Wikipedia URL already exists
                existing_wikipedia_url = None
                if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
                    existing_wikipedia_url = artist.imvdb_metadata.get("wikipedia_url")

                if not existing_wikipedia_url:
                    # Use the same method as Flask implementation
                    wikipedia_result = await asyncio.to_thread(
                        wikipedia_service._search_artist_page, artist.name
                    )
                    logger.info(f"📖 Wikipedia search result: {wikipedia_result}")

                    if wikipedia_result:
                        # Construct Wikipedia URL like Flask implementation did
                        artist_name_clean = wikipedia_result.replace(" ", "_")
                        wikipedia_url = (
                            f"https://en.wikipedia.org/wiki/{artist_name_clean}"
                        )

                        # Initialize imvdb_metadata if it doesn't exist
                        if not artist.imvdb_metadata:
                            artist.imvdb_metadata = {}

                        # Store Wikipedia data like Flask implementation
                        artist.imvdb_metadata["wikipedia_url"] = wikipedia_url
                        artist.imvdb_metadata["wikipedia_page"] = wikipedia_result
                        matches_found["wikipedia"] = True
                        updated_fields.append("wikipedia_url")
                        logger.info(
                            f"📖 ✅ Found and saved Wikipedia match for {artist.name}: {wikipedia_url}"
                        )
                    else:
                        logger.info(f"📖 ❌ No Wikipedia page found for {artist.name}")
                else:
                    logger.info(
                        f"📖 Wikipedia URL already exists for {artist.name}: {existing_wikipedia_url}"
                    )

            except Exception as e:
                logger.warning(
                    f"📖 ❌ Wikipedia auto-match failed for {artist.name}: {e}"
                )
                import traceback

                traceback.print_exc()

        # Save changes to database if any matches were found
        if updated_fields:
            try:
                # Log the changes before saving
                logger.info(
                    f"About to save {len(updated_fields)} auto-match changes for {artist.name}: {updated_fields}"
                )
                logger.info(
                    f"Artist imvdb_metadata before save: {artist.imvdb_metadata}"
                )
                logger.info(
                    f"Artist spotify_id: {getattr(artist, 'spotify_id', 'N/A')}"
                )
                logger.info(
                    f"Artist lastfm_name: {getattr(artist, 'lastfm_name', 'N/A')}"
                )

                # Mark the JSON field as modified to ensure SQLAlchemy detects the change
                attributes.flag_modified(artist, "imvdb_metadata")

                artist.updated_at = datetime.utcnow()
                session.commit()

                # Verify the commit worked by refreshing from database
                session.refresh(artist)
                logger.info(
                    f"Auto-match saved {len(updated_fields)} matches for {artist.name}: {updated_fields}"
                )
                logger.info(
                    f"Artist imvdb_metadata after save: {artist.imvdb_metadata}"
                )
                logger.info(f"Artist updated_at after save: {artist.updated_at}")

                # Force a flush to ensure data is written to database
                session.flush()

            except Exception as e:
                logger.error(
                    f"Failed to save auto-match results for {artist.name}: {e}"
                )
                session.rollback()
                # Don't fail the request, just log the error
                for field in updated_fields:
                    # Map field names to service names
                    field_to_service = {
                        "spotify_id": "spotify",
                        "lastfm_name": "lastfm",
                        "musicbrainz_id": "musicbrainz",
                        "imvdb_id": "imvdb",
                        "allmusic_id": "allmusic",
                        "wikipedia_page": "wikipedia",
                        "wikipedia_url": "wikipedia",
                    }
                    service_name = field_to_service.get(field)
                    if service_name:
                        matches_found[service_name] = False

        total_matches = sum(matches_found.values())

        # Log final match results
        logger.info(f"Auto-match completed for {artist.name}:")
        logger.info(f"  Matches found: {matches_found}")
        logger.info(f"  Total matches: {total_matches}")
        logger.info(f"  Updated fields: {updated_fields}")
        if updated_fields:
            logger.info(f"  Final imvdb_metadata: {artist.imvdb_metadata}")

        # Return job-style response for background jobs system
        return {
            "success": True,
            "job_id": job_id,
            "status": "queued",  # Jobs system expects this initially
            "message": f"Auto-match job started for {artist.name}",
            "artist_id": artist_id,
            "artist_name": artist.name,
            "job_type": "auto_match",
            # Include the actual results for immediate completion
            "result": {
                "matches_found": matches_found,
                "total_matches": total_matches,
                "updated_fields": updated_fields,
                "database_updated": len(updated_fields) > 0,
                "completion_message": f"Auto-matching completed for {artist.name} - {total_matches} services matched"
                + (
                    f", {len(updated_fields)} saved to database"
                    if updated_fields
                    else ""
                ),
            },
        }

    except Exception as e:
        logger.error(f"Auto-match error for artist ID {artist_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-match failed: {str(e)}")


@router.post("/enrich/video/{video_id}")
async def enrich_video_metadata(
    video_id: int,
    background_tasks: BackgroundTasks,
    data: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enrich metadata for a specific video using Celery background jobs"""
    try:
        # Get video from database
        from src.database.models import Video

        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        force_refresh = data.get("force_refresh", False) if data else False

        logger.info(f"Enriching metadata for video {video_id}: {video.title}")

        # Import and use Celery tasks directly
        from src.jobs.metadata_tasks import enrich_video_metadata_task

        try:
            # Wrap synchronous .delay() in thread to avoid blocking the event loop
            task_result = await asyncio.to_thread(
                enrich_video_metadata_task.delay,
                video_id=video_id,
                force_refresh=force_refresh,
            )

            logger.info(
                f"Started Celery video metadata enrichment task {task_result.id} for video {video.title}"
            )

            return {
                "job_id": task_result.id,
                "message": f"Video metadata enrichment job started for {video.title}",
                "video_id": video_id,
                "status": "queued",
                "force_refresh": force_refresh,
                "note": "Background processing initiated with Celery + Redis",
                "task_name": "metadata.enrich_video",
            }

        except Exception as celery_error:
            logger.warning(
                f"Celery unavailable for video enrichment, running directly: {celery_error}"
            )
            task_id = str(uuid.uuid4())
            background_tasks.add_task(
                _enrich_video_direct, video_id, force_refresh, task_id
            )
            return {
                "job_id": task_id,
                "message": f"Video metadata enrichment started for {video.title} (direct mode)",
                "video_id": video_id,
                "status": "queued",
                "force_refresh": force_refresh,
                "note": "Running directly — Celery unavailable",
                "task_name": "metadata.enrich_video",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video metadata enrichment error for ID {video_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Video metadata enrichment failed: {str(e)}"
        )


@router.post("/enrich/batch")
async def batch_enrich_artists(
    data: Dict[str, Any],
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Batch enrich metadata for multiple artists using Celery background jobs"""
    try:
        artist_ids = data.get("artist_ids", [])
        if not artist_ids:
            raise HTTPException(status_code=400, detail="No artist IDs provided")

        force_refresh = data.get("force_refresh", False)
        enrich_videos = data.get("enrich_videos", True)

        # Validate that all artists exist
        from src.database.models import Artist

        existing_artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
        existing_ids = [artist.id for artist in existing_artists]
        missing_ids = set(artist_ids) - set(existing_ids)

        if missing_ids:
            raise HTTPException(
                status_code=404, detail=f"Artists not found: {list(missing_ids)}"
            )

        logger.info(f"Starting batch metadata enrichment for {len(artist_ids)} artists")

        # Import and use Celery tasks directly
        from src.jobs.metadata_tasks import batch_enrich_artists_task

        try:
            # Wrap synchronous .delay() in thread to avoid blocking the event loop
            task_result = await asyncio.to_thread(
                batch_enrich_artists_task.delay,
                artist_ids=artist_ids,
                force_refresh=force_refresh,
                enrich_videos=enrich_videos,
            )

            logger.info(
                f"Started Celery batch metadata enrichment task {task_result.id}"
            )

            return {
                "job_id": task_result.id,
                "message": f"Batch metadata enrichment job started for {len(artist_ids)} artists",
                "artist_ids": artist_ids,
                "total_artists": len(artist_ids),
                "status": "queued",
                "force_refresh": force_refresh,
                "enrich_videos": enrich_videos,
                "note": "Background processing initiated with Celery + Redis",
                "task_name": "metadata.batch_enrich_artists",
            }

        except Exception as celery_error:
            logger.warning(f"Celery unavailable for batch enrichment: {celery_error}")
            raise HTTPException(
                status_code=503,
                detail="Celery workers unavailable. Please ensure Celery is running for batch operations.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch metadata enrichment error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Batch metadata enrichment failed: {str(e)}"
        )


@router.post("/enrich/all")
async def enrich_all_artists(
    data: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Enrich metadata for ALL artists in the database using Celery background jobs"""
    try:
        from src.database.models import Artist

        # Get all artist IDs from database
        all_artists = session.query(Artist.id).all()
        artist_ids = [artist.id for artist in all_artists]

        if not artist_ids:
            return {
                "message": "No artists found in database",
                "total_artists": 0,
                "status": "completed",
            }

        force_refresh = data.get("force_refresh", False) if data else False
        enrich_videos = data.get("enrich_videos", True) if data else True

        logger.info(
            f"Starting bulk metadata enrichment for ALL {len(artist_ids)} artists"
        )

        # Import and use Celery tasks directly
        from src.jobs.metadata_tasks import batch_enrich_artists_task

        try:
            # Wrap synchronous .delay() in thread to avoid blocking the event loop
            task_result = await asyncio.to_thread(
                batch_enrich_artists_task.delay,
                artist_ids=artist_ids,
                force_refresh=force_refresh,
                enrich_videos=enrich_videos,
            )

            logger.info(
                f"Started Celery bulk enrichment task {task_result.id} for ALL artists"
            )

            return {
                "job_id": task_result.id,
                "message": f"Bulk metadata enrichment job started for ALL {len(artist_ids)} artists",
                "total_artists": len(artist_ids),
                "status": "queued",
                "force_refresh": force_refresh,
                "enrich_videos": enrich_videos,
                "note": "Background processing initiated with Celery + Redis",
                "task_name": "metadata.batch_enrich_all_artists",
            }

        except Exception as celery_error:
            logger.warning(f"Celery unavailable for bulk enrichment: {celery_error}")
            raise HTTPException(
                status_code=503,
                detail="Celery workers unavailable. Please ensure Celery is running for bulk operations.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk enrichment error for all artists: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk enrichment failed: {str(e)}")


@router.post("/auto-match/all")
async def auto_match_all_artists(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Auto-match ALL artists with external services as background job"""
    try:
        from src.database.models import Artist

        # Get all artists from database
        all_artists = session.query(Artist).all()

        if not all_artists:
            return {
                "message": "No artists found in database",
                "total_artists": 0,
                "status": "completed",
            }

        logger.info(f"Starting bulk auto-match for ALL {len(all_artists)} artists")

        # Process each artist's auto-match
        job_ids = []
        success_count = 0
        error_count = 0

        for artist in all_artists:
            try:
                # Call the single artist auto-match logic inline
                # (reusing the logic from auto_match_services endpoint)
                matches_found = await _auto_match_artist(artist, session)

                if any(matches_found.values()):
                    success_count += 1
                    logger.info(
                        f"✅ Auto-matched artist {artist.name}: {matches_found}"
                    )
                else:
                    logger.info(f"⚠️ No matches found for artist {artist.name}")

            except Exception as e:
                error_count += 1
                logger.error(f"❌ Auto-match failed for artist {artist.name}: {e}")

        # Commit all changes at once
        try:
            session.commit()
            logger.info(
                f"✅ Committed auto-match results for {len(all_artists)} artists"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit auto-match results: {e}")
            raise

        return {
            "message": f"Bulk auto-match completed for {len(all_artists)} artists",
            "total_artists": len(all_artists),
            "successful_matches": success_count,
            "failed_matches": error_count,
            "status": "completed",
            "note": "Auto-match process completed synchronously",
        }

    except Exception as e:
        logger.error(f"Bulk auto-match error for all artists: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk auto-match failed: {str(e)}")


async def _auto_match_artist(artist, session):
    """Helper function to auto-match a single artist with external services"""
    matches_found = {
        "spotify": False,
        "lastfm": False,
        "musicbrainz": False,
        "imvdb": False,
        "allmusic": False,
        "wikipedia": False,
    }

    updated_fields = []

    # Spotify auto-match
    if get_async_spotify_service and not artist.spotify_id:
        try:
            from src.services.settings_service import settings
            from src.utils.async_http_client import get_global_http_client

            client_id = settings.get("spotify_client_id")
            client_secret = settings.get("spotify_client_secret")

            if client_id and client_secret:
                credentials = f"{client_id}:{client_secret}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                http_client = await get_global_http_client()

                token_response = await asyncio.wait_for(
                    http_client.post(
                        "https://accounts.spotify.com/api/token",
                        headers={
                            "Authorization": f"Basic {encoded_credentials}",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={"grant_type": "client_credentials"},
                    ),
                    timeout=15.0,
                )

                if token_response and token_response.get("access_token"):
                    access_token = token_response["access_token"]

                    search_response = await asyncio.wait_for(
                        http_client.get(
                            "https://api.spotify.com/v1/search",
                            headers={"Authorization": f"Bearer {access_token}"},
                            params={"q": artist.name, "type": "artist", "limit": 1},
                        ),
                        timeout=15.0,
                    )

                    if search_response and search_response.get("artists", {}).get(
                        "items"
                    ):
                        spotify_artist = search_response["artists"]["items"][0]
                        artist.spotify_id = spotify_artist["id"]
                        matches_found["spotify"] = True
                        updated_fields.append("spotify_id")

        except Exception as e:
            logger.warning(f"Spotify auto-match failed for {artist.name}: {e}")

    # Last.fm auto-match
    if lastfm_service and not artist.lastfm_name:
        try:
            lastfm_result = await asyncio.to_thread(
                lastfm_service.search_artist, artist.name
            )
            if lastfm_result:
                lastfm_name = (
                    lastfm_result.get("name")
                    if isinstance(lastfm_result, dict)
                    else None
                )
                if lastfm_name:
                    artist.lastfm_name = lastfm_name
                    matches_found["lastfm"] = True
                    updated_fields.append("lastfm_name")
        except Exception as e:
            logger.warning(f"Last.fm auto-match failed for {artist.name}: {e}")

    # MusicBrainz auto-match
    if musicbrainz_service:
        try:
            mb_result = await asyncio.to_thread(
                musicbrainz_service.search_artist, artist.name
            )
            existing_mbid = None
            if artist.imvdb_metadata and isinstance(artist.imvdb_metadata, dict):
                existing_mbid = artist.imvdb_metadata.get("musicbrainz_id")

            if mb_result and not existing_mbid:
                mb_id = (
                    mb_result.get("mbid") or mb_result.get("id")
                    if isinstance(mb_result, dict)
                    else None
                )
                if mb_id:
                    if not artist.imvdb_metadata:
                        artist.imvdb_metadata = {}
                    artist.imvdb_metadata["musicbrainz_id"] = mb_id
                    matches_found["musicbrainz"] = True
                    updated_fields.append("musicbrainz_id")
        except Exception as e:
            logger.warning(f"MusicBrainz auto-match failed for {artist.name}: {e}")

    # IMVDb auto-match
    if imvdb_service and not artist.imvdb_id:
        try:
            imvdb_result = await asyncio.to_thread(
                imvdb_service.search_artist, artist.name
            )
            if imvdb_result:
                imvdb_id = (
                    imvdb_result.get("id") if isinstance(imvdb_result, dict) else None
                )
                if imvdb_id:
                    artist.imvdb_id = imvdb_id
                    matches_found["imvdb"] = True
                    updated_fields.append("imvdb_id")
        except Exception as e:
            logger.warning(f"IMVDb auto-match failed for {artist.name}: {e}")

    return matches_found
