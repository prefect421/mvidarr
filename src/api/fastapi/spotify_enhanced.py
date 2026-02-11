"""
FastAPI Spotify Enhanced Router - Migrated from Flask Blueprint
Enhanced Spotify API endpoints for Issue #79 - playlist sync, recommendations, and real-time updates
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)
from src.database.connection import get_db
from src.database.models import Artist
from src.services.spotify_service import spotify_service
from src.services.spotify_sync_service import spotify_sync_service
from src.utils.logger import get_logger

router = APIRouter(
    prefix="/api/spotify",
    tags=["spotify-enhanced"],
    responses={
        404: {"description": "Resource not found"},
        422: {"description": "Validation error"},
    },
)

logger = get_logger("mvidarr.api.fastapi.spotify_enhanced")
# ========================================================================================
# PYDANTIC MODELS
# ========================================================================================


class PlaylistSyncRequest(BaseModel):
    force_refresh: bool = False


class PlaylistSyncSummary(BaseModel):
    playlists_synced: int
    total_playlists: int
    artists_discovered: int
    videos_matched: int
    total_errors: int


class PlaylistSyncResult(BaseModel):
    success: bool
    playlist_id: Optional[str] = None
    spotify_playlist_id: Optional[str] = None
    artists_discovered: int
    videos_matched: int
    errors: List[str]
    processing_time: float


class PlaylistSyncResponse(BaseModel):
    success: bool
    message: str
    summary: PlaylistSyncSummary
    results: List[PlaylistSyncResult]


class PlaylistExportRequest(BaseModel):
    create_new: bool = True
    spotify_playlist_id: Optional[str] = None


class PlaylistExportResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    spotify_playlist_id: Optional[str] = None
    tracks_added: Optional[int] = None
    processing_time: Optional[float] = None
    errors: Optional[List[str]] = None


class RecommendationsResponse(BaseModel):
    success: bool
    recommendations: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class NewReleasesResponse(BaseModel):
    success: bool
    new_releases: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class WebhookRequest(BaseModel):
    type: str
    data: Dict[str, Any]


class WebhookResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class SyncStatusResponse(BaseModel):
    success: bool
    status: Dict[str, Any]


class TrackSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]


class AudioFeaturesResponse(BaseModel):
    success: bool
    audio_features: Optional[Dict[str, Any]] = None


class RecommendationsRequest(BaseModel):
    seed_artists: List[str] = []
    seed_tracks: List[str] = []
    seed_genres: List[str] = []
    limit: int = 20
    target_danceability: Optional[float] = None
    target_energy: Optional[float] = None
    target_valence: Optional[float] = None
    min_popularity: Optional[int] = None
    max_popularity: Optional[int] = None


class CreatePlaylistRequest(BaseModel):
    name: str
    description: str = ""
    public: bool = False
    collaborative: bool = False


class CreatePlaylistResponse(BaseModel):
    success: bool
    playlist: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    error: Optional[str] = None


class ArtistDiscoveryRequest(BaseModel):
    limit: int = 50


class ArtistDiscoveryResponse(BaseModel):
    success: bool
    message: str
    discovered_artists: List[Dict[str, Any]]
    total_discovered: int


class MetadataMatchingRequest(BaseModel):
    artist_name: str
    track_title: str


class MetadataMatchingResponse(BaseModel):
    success: bool
    query: Dict[str, str]
    matches: List[Dict[str, Any]]
    total_matches: int
    best_match_score: float


class ConnectDevicesResponse(BaseModel):
    success: bool
    devices: List[Dict[str, Any]]


class ConnectPlayRequest(BaseModel):
    device_id: Optional[str] = None
    track_uris: List[str] = []
    context_uri: Optional[str] = None


class ConnectPlayResponse(BaseModel):
    success: bool
    message: str


class ListeningAnalyticsResponse(BaseModel):
    success: bool
    analytics: Dict[str, Any]


class SimilarArtistsRequest(BaseModel):
    artist_ids: List[str]


class SimilarArtistsResponse(BaseModel):
    success: bool
    similar_artists: List[Dict[str, Any]]
    total_discovered: int
    based_on_artists: int


# ========================================================================================
# PLAYLIST SYNC ENDPOINTS
# ========================================================================================


@router.post("/playlists/sync", response_model=PlaylistSyncResponse)
async def sync_user_playlists(
    request: PlaylistSyncRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Sync all user playlists from Spotify to MVidarr"""
    try:
        logger.info("Starting Spotify playlist synchronization")

        results = spotify_sync_service.sync_user_playlists(
            force_refresh=request.force_refresh
        )

        # Calculate summary statistics
        successful_syncs = sum(1 for r in results if r.success)
        total_artists = sum(r.artists_discovered for r in results)
        total_videos = sum(r.videos_matched for r in results)
        total_errors = sum(len(r.errors) for r in results)

        summary = PlaylistSyncSummary(
            playlists_synced=successful_syncs,
            total_playlists=len(results),
            artists_discovered=total_artists,
            videos_matched=total_videos,
            total_errors=total_errors,
        )

        sync_results = [
            PlaylistSyncResult(
                success=r.success,
                playlist_id=r.playlist_id,
                spotify_playlist_id=r.spotify_playlist_id,
                artists_discovered=r.artists_discovered,
                videos_matched=r.videos_matched,
                errors=r.errors,
                processing_time=r.processing_time,
            )
            for r in results
        ]

        return PlaylistSyncResponse(
            success=successful_syncs > 0,
            message=f"Synced {successful_syncs} of {len(results)} playlists",
            summary=summary,
            results=sync_results,
        )

    except Exception as e:
        logger.error(f"Failed to sync Spotify playlists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/playlists/{playlist_id}/export", response_model=PlaylistExportResponse)
async def export_playlist_to_spotify(
    playlist_id: str,
    request: PlaylistExportRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Export MVidarr playlist to Spotify"""
    try:
        try:
            playlist_id_int = int(playlist_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid playlist ID"
            )

        logger.info(f"Exporting MVidarr playlist {playlist_id} to Spotify")

        result = spotify_sync_service.export_playlist_to_spotify(
            playlist_id_int, request.create_new, request.spotify_playlist_id
        )

        if result.success:
            return PlaylistExportResponse(
                success=True,
                message=f"Successfully exported {result.tracks_added} tracks to Spotify",
                spotify_playlist_id=result.spotify_playlist_id,
                tracks_added=result.tracks_added,
                processing_time=result.processing_time,
            )
        else:
            return PlaylistExportResponse(
                success=False,
                errors=result.errors,
                processing_time=result.processing_time,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export playlist to Spotify: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_music_video_recommendations(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_authentication),
):
    """Get music video recommendations based on Spotify listening history"""
    try:
        logger.info("Generating music video recommendations from Spotify data")

        result = spotify_sync_service.get_music_video_recommendations(limit)

        return RecommendationsResponse(**result)

    except Exception as e:
        logger.error(f"Failed to get music video recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/new-releases", response_model=NewReleasesResponse)
async def check_new_releases(current_user: dict = Depends(require_authentication)):
    """Check for new releases from followed artists"""
    try:
        logger.info("Checking for new releases from followed Spotify artists")

        result = spotify_sync_service.sync_new_releases()

        return NewReleasesResponse(**result)

    except Exception as e:
        logger.error(f"Failed to check for new releases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/webhooks", response_model=WebhookResponse)
async def handle_spotify_webhook(
    webhook_data: WebhookRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Handle incoming Spotify webhooks for real-time updates"""
    try:
        logger.info(f"Received Spotify webhook: {webhook_data.type}")

        result = spotify_sync_service.process_spotify_webhook(webhook_data.dict())

        return WebhookResponse(**result)

    except Exception as e:
        logger.error(f"Failed to process Spotify webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(current_user: dict = Depends(require_authentication)):
    """Get current Spotify synchronization status"""
    try:
        status_data = spotify_sync_service.get_sync_status()

        return SyncStatusResponse(success=True, status=status_data)

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/sync/clear-cache")
async def clear_sync_cache(current_user: dict = Depends(require_authentication)):
    """Clear Spotify synchronization cache"""
    try:
        spotify_sync_service.clear_sync_cache()

        return {"success": True, "message": "Spotify sync cache cleared successfully"}

    except Exception as e:
        logger.error(f"Failed to clear sync cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# ENHANCED SPOTIFY API METHODS
# ========================================================================================


@router.get("/tracks/search", response_model=TrackSearchResponse)
async def search_tracks(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_authentication),
):
    """Search for tracks on Spotify"""
    try:
        result = spotify_service.search_tracks(q, limit)

        return TrackSearchResponse(success=True, results=result)

    except Exception as e:
        logger.error(f"Failed to search Spotify tracks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/tracks/{track_id}/audio-features", response_model=AudioFeaturesResponse)
async def get_track_audio_features(
    track_id: str, current_user: dict = Depends(require_authentication)
):
    """Get audio features for a Spotify track"""
    try:
        result = spotify_service.get_track_audio_features(track_id)

        return AudioFeaturesResponse(success=True, audio_features=result)

    except Exception as e:
        logger.error(f"Failed to get track audio features: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/recommendations/generate")
async def generate_recommendations(
    request: RecommendationsRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Generate Spotify recommendations with custom parameters"""
    try:
        # Audio feature parameters
        audio_params = {}
        if request.target_danceability is not None:
            audio_params["target_danceability"] = request.target_danceability
        if request.target_energy is not None:
            audio_params["target_energy"] = request.target_energy
        if request.target_valence is not None:
            audio_params["target_valence"] = request.target_valence
        if request.min_popularity is not None:
            audio_params["min_popularity"] = request.min_popularity
        if request.max_popularity is not None:
            audio_params["max_popularity"] = request.max_popularity

        result = spotify_service.get_recommendations(
            seed_artists=request.seed_artists,
            seed_tracks=request.seed_tracks,
            seed_genres=request.seed_genres,
            limit=request.limit,
            **audio_params,
        )

        return {"success": True, "recommendations": result}

    except Exception as e:
        logger.error(f"Failed to generate Spotify recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/playlists/create", response_model=CreatePlaylistResponse)
async def create_spotify_playlist(
    request: CreatePlaylistRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Create a new Spotify playlist"""
    try:
        result = spotify_service.create_playlist(
            request.name, request.description, request.public, request.collaborative
        )

        if result and "id" in result:
            return CreatePlaylistResponse(
                success=True,
                playlist=result,
                message=f"Created Spotify playlist: {request.name}",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create Spotify playlist",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Spotify playlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/discovery/artist-library", response_model=ArtistDiscoveryResponse)
async def discover_artists_from_library(
    request: ArtistDiscoveryRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Discover new artists from user's Spotify library"""
    try:
        logger.info("Starting artist discovery from Spotify library")

        # Get user's saved tracks
        saved_tracks_response = spotify_service._make_request(
            "me/tracks", {"limit": request.limit}
        )
        if not saved_tracks_response or "items" not in saved_tracks_response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get saved tracks",
            )

        saved_tracks = saved_tracks_response["items"]
        discovered_artists = []

        with get_db() as session:
            for track_item in saved_tracks:
                track = track_item.get("track")
                if not track:
                    continue

                for artist_data in track.get("artists", []):
                    artist_name = artist_data.get("name")
                    spotify_id = artist_data.get("id")

                    if not artist_name:
                        continue

                    # Check if artist exists in MVidarr
                    existing_artist = (
                        session.query(Artist)
                        .filter(
                            or_(
                                Artist.spotify_id == spotify_id,
                                Artist.name.ilike(f"%{artist_name}%"),
                            )
                        )
                        .first()
                    )

                    if not existing_artist:
                        # Discover new artist
                        new_artist = Artist(
                            name=artist_name,
                            spotify_id=spotify_id,
                            status="new",
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        )

                        session.add(new_artist)
                        session.flush()

                        discovered_artists.append(
                            {
                                "id": new_artist.id,
                                "name": artist_name,
                                "spotify_id": spotify_id,
                                "external_urls": artist_data.get("external_urls", {}),
                            }
                        )

                        logger.debug(
                            f"Discovered new artist from Spotify library: {artist_name}"
                        )

            session.commit()

        return ArtistDiscoveryResponse(
            success=True,
            message=f"Discovered {len(discovered_artists)} new artists",
            discovered_artists=discovered_artists,
            total_discovered=len(discovered_artists),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to discover artists from Spotify library: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/metadata/enhanced-matching", response_model=MetadataMatchingResponse)
async def enhanced_metadata_matching(
    request: MetadataMatchingRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Perform enhanced metadata matching with Spotify catalog"""
    try:
        # Search for track on Spotify
        search_query = f"track:{request.track_title} artist:{request.artist_name}"
        track_search = spotify_service.search_tracks(search_query, limit=10)

        if not track_search or "tracks" not in track_search:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tracks found on Spotify",
            )

        tracks = track_search["tracks"]["items"]

        # Calculate metadata similarity for each result
        matches = []
        for track in tracks:
            # Calculate similarity scores
            artist_match_score = max(
                spotify_sync_service._calculate_track_similarity(
                    request.artist_name, artist.get("name", "")
                )
                for artist in track.get("artists", [])
            )

            track_match_score = spotify_sync_service._calculate_track_similarity(
                request.track_title, track.get("name", "")
            )

            overall_score = (artist_match_score + track_match_score) / 2

            # Get audio features for enhanced matching
            audio_features = spotify_service.get_track_audio_features(track["id"])

            match_data = {
                "spotify_track_id": track["id"],
                "track_name": track["name"],
                "artists": [a["name"] for a in track.get("artists", [])],
                "album": track.get("album", {}).get("name"),
                "release_date": track.get("album", {}).get("release_date"),
                "popularity": track.get("popularity"),
                "preview_url": track.get("preview_url"),
                "external_urls": track.get("external_urls", {}),
                "similarity_scores": {
                    "artist_match": artist_match_score,
                    "track_match": track_match_score,
                    "overall_match": overall_score,
                },
                "audio_features": audio_features if audio_features else None,
            }

            matches.append(match_data)

        # Sort by overall similarity
        matches.sort(
            key=lambda x: x["similarity_scores"]["overall_match"], reverse=True
        )

        return MetadataMatchingResponse(
            success=True,
            query={"artist": request.artist_name, "track": request.track_title},
            matches=matches,
            total_matches=len(matches),
            best_match_score=(
                matches[0]["similarity_scores"]["overall_match"] if matches else 0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform enhanced metadata matching: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ========================================================================================
# SPOTIFY CONNECT ENDPOINTS
# ========================================================================================


@router.get("/connect/devices", response_model=ConnectDevicesResponse)
async def get_spotify_connect_devices(
    current_user: dict = Depends(require_authentication),
):
    """Get available Spotify Connect devices"""
    try:
        from src.services.spotify_connect_service import spotify_connect_service

        devices = spotify_connect_service.get_available_devices()

        return ConnectDevicesResponse(
            success=True,
            devices=devices.get("devices", []) if devices else [],
        )

    except Exception as e:
        logger.error(f"Failed to get Spotify Connect devices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/connect/play", response_model=ConnectPlayResponse)
async def spotify_connect_play(
    request: ConnectPlayRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Control Spotify Connect playback"""
    try:
        from src.services.spotify_connect_service import spotify_connect_service

        if request.track_uris:
            result = spotify_connect_service.play_tracks(
                request.track_uris, request.device_id
            )
        elif request.context_uri:
            result = spotify_connect_service.play_context(
                request.context_uri, request.device_id
            )
        else:
            result = spotify_connect_service.resume_playback(request.device_id)

        return ConnectPlayResponse(
            success=result.get("success", False),
            message="Playback command sent to Spotify Connect",
        )

    except Exception as e:
        logger.error(f"Failed to control Spotify Connect playback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/analytics/listening-stats", response_model=ListeningAnalyticsResponse)
async def get_listening_analytics(
    time_range: str = Query(
        "medium_term", pattern="^(short_term|medium_term|long_term)$"
    ),
    current_user: dict = Depends(require_authentication),
):
    """Get analytics from Spotify listening data"""
    try:
        # Get top artists and tracks
        top_artists = spotify_service.get_user_top_artists(
            time_range=time_range, limit=20
        )
        top_tracks = spotify_service.get_user_top_tracks(
            time_range=time_range, limit=20
        )

        # Get user's music taste profile
        analytics = {
            "time_range": time_range,
            "top_artists": top_artists.get("items", []) if top_artists else [],
            "top_tracks": top_tracks.get("items", []) if top_tracks else [],
            "analysis_date": datetime.now().isoformat(),
        }

        # Add genre analysis
        if top_artists and "items" in top_artists:
            genre_counts = {}
            for artist in top_artists["items"]:
                for genre in artist.get("genres", []):
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1

            analytics["top_genres"] = sorted(
                genre_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]

        return ListeningAnalyticsResponse(success=True, analytics=analytics)

    except Exception as e:
        logger.error(f"Failed to get listening analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/discovery/similar-artists", response_model=SimilarArtistsResponse)
async def discover_similar_artists(
    request: SimilarArtistsRequest = Body(...),
    current_user: dict = Depends(require_authentication),
):
    """Discover similar artists based on Spotify data"""
    try:
        if not request.artist_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="artist_ids are required",
            )

        # Get recommendations based on these artists
        recommendations = spotify_service.get_recommendations(
            seed_artists=request.artist_ids[:5], limit=20  # Spotify allows max 5 seeds
        )

        if not recommendations or "tracks" not in recommendations:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get recommendations",
            )

        # Extract unique artists from recommendations
        similar_artists = {}
        for track in recommendations["tracks"]:
            for artist in track.get("artists", []):
                artist_id = artist.get("id")
                if artist_id not in request.artist_ids:  # Exclude seed artists
                    similar_artists[artist_id] = {
                        "id": artist_id,
                        "name": artist.get("name"),
                        "external_urls": artist.get("external_urls", {}),
                        "track_count": similar_artists.get(artist_id, {}).get(
                            "track_count", 0
                        )
                        + 1,
                    }

        # Sort by frequency in recommendations
        sorted_artists = sorted(
            similar_artists.values(), key=lambda x: x["track_count"], reverse=True
        )

        return SimilarArtistsResponse(
            success=True,
            similar_artists=sorted_artists,
            total_discovered=len(sorted_artists),
            based_on_artists=len(request.artist_ids),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to discover similar artists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
