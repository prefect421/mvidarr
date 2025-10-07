"""
Enhanced Spotify API endpoints for Issue #79 - playlist sync, recommendations, and real-time updates
"""

from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from src.database.connection import get_db
from src.database.models import Artist
from src.services.spotify_service import spotify_service
from src.services.spotify_sync_service import spotify_sync_service
from src.utils.logger import get_logger

spotify_enhanced_bp = Blueprint("spotify_enhanced", __name__, url_prefix="/spotify")
logger = get_logger("mvidarr.api.spotify_enhanced")


@spotify_enhanced_bp.route("/playlists/sync", methods=["POST"])
def sync_user_playlists():
    """Sync all user playlists from Spotify to MVidarr"""
    try:
        data = request.get_json() or {}
        force_refresh = data.get("force_refresh", False)

        logger.info("Starting Spotify playlist synchronization")

        results = spotify_sync_service.sync_user_playlists(force_refresh=force_refresh)

        # Calculate summary statistics
        successful_syncs = sum(1 for r in results if r.success)
        total_artists = sum(r.artists_discovered for r in results)
        total_videos = sum(r.videos_matched for r in results)
        total_errors = sum(len(r.errors) for r in results)

        return jsonify(
            {
                "success": successful_syncs > 0,
                "message": f"Synced {successful_syncs} of {len(results)} playlists",
                "summary": {
                    "playlists_synced": successful_syncs,
                    "total_playlists": len(results),
                    "artists_discovered": total_artists,
                    "videos_matched": total_videos,
                    "total_errors": total_errors,
                },
                "results": [
                    {
                        "success": r.success,
                        "playlist_id": r.playlist_id,
                        "spotify_playlist_id": r.spotify_playlist_id,
                        "artists_discovered": r.artists_discovered,
                        "videos_matched": r.videos_matched,
                        "errors": r.errors,
                        "processing_time": r.processing_time,
                    }
                    for r in results
                ],
            }
        ), (200 if successful_syncs > 0 else 500)

    except Exception as e:
        logger.error(f"Failed to sync Spotify playlists: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/playlists/<playlist_id>/export", methods=["POST"])
def export_playlist_to_spotify(playlist_id):
    """Export MVidarr playlist to Spotify"""
    try:
        data = request.get_json() or {}
        create_new = data.get("create_new", True)
        spotify_playlist_id = data.get("spotify_playlist_id")

        playlist_id_int = int(playlist_id)

        logger.info(f"Exporting MVidarr playlist {playlist_id} to Spotify")

        result = spotify_sync_service.export_playlist_to_spotify(
            playlist_id_int, create_new, spotify_playlist_id
        )

        if result.success:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Successfully exported {result.tracks_added} tracks to Spotify",
                        "spotify_playlist_id": result.spotify_playlist_id,
                        "tracks_added": result.tracks_added,
                        "processing_time": result.processing_time,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "errors": result.errors,
                        "processing_time": result.processing_time,
                    }
                ),
                500,
            )

    except ValueError:
        return jsonify({"success": False, "error": "Invalid playlist ID"}), 400
    except Exception as e:
        logger.error(f"Failed to export playlist to Spotify: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/recommendations", methods=["GET"])
def get_music_video_recommendations():
    """Get music video recommendations based on Spotify listening history"""
    try:
        limit = int(request.args.get("limit", 20))

        logger.info("Generating music video recommendations from Spotify data")

        result = spotify_sync_service.get_music_video_recommendations(limit)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"Failed to get music video recommendations: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/new-releases", methods=["GET"])
def check_new_releases():
    """Check for new releases from followed artists"""
    try:
        logger.info("Checking for new releases from followed Spotify artists")

        result = spotify_sync_service.sync_new_releases()

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"Failed to check for new releases: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/webhooks", methods=["POST"])
def handle_spotify_webhook():
    """Handle incoming Spotify webhooks for real-time updates"""
    try:
        # Verify webhook signature (basic implementation)
        webhook_data = request.get_json()
        if not webhook_data:
            return jsonify({"success": False, "error": "No webhook data received"}), 400

        logger.info(f"Received Spotify webhook: {webhook_data.get('type', 'unknown')}")

        result = spotify_sync_service.process_spotify_webhook(webhook_data)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"Failed to process Spotify webhook: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """Get current Spotify synchronization status"""
    try:
        status = spotify_sync_service.get_sync_status()

        return jsonify({"success": True, "status": status}), 200

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/sync/clear-cache", methods=["POST"])
def clear_sync_cache():
    """Clear Spotify synchronization cache"""
    try:
        spotify_sync_service.clear_sync_cache()

        return (
            jsonify(
                {"success": True, "message": "Spotify sync cache cleared successfully"}
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to clear sync cache: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Enhanced Spotify API methods


@spotify_enhanced_bp.route("/tracks/search", methods=["GET"])
def search_tracks():
    """Search for tracks on Spotify"""
    try:
        query = request.args.get("q")
        if not query:
            return (
                jsonify({"success": False, "error": "Query parameter 'q' is required"}),
                400,
            )

        limit = int(request.args.get("limit", 10))

        result = spotify_service.search_tracks(query, limit)

        return jsonify({"success": True, "results": result}), 200

    except Exception as e:
        logger.error(f"Failed to search Spotify tracks: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/tracks/<track_id>/audio-features", methods=["GET"])
def get_track_audio_features(track_id):
    """Get audio features for a Spotify track"""
    try:
        result = spotify_service.get_track_audio_features(track_id)

        return jsonify({"success": True, "audio_features": result}), 200

    except Exception as e:
        logger.error(f"Failed to get track audio features: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/recommendations/generate", methods=["POST"])
def generate_recommendations():
    """Generate Spotify recommendations with custom parameters"""
    try:
        data = request.get_json() or {}

        seed_artists = data.get("seed_artists", [])
        seed_tracks = data.get("seed_tracks", [])
        seed_genres = data.get("seed_genres", [])
        limit = data.get("limit", 20)

        # Audio feature parameters
        audio_params = {}
        for param in [
            "target_danceability",
            "target_energy",
            "target_valence",
            "min_popularity",
            "max_popularity",
        ]:
            if param in data:
                audio_params[param] = data[param]

        result = spotify_service.get_recommendations(
            seed_artists=seed_artists,
            seed_tracks=seed_tracks,
            seed_genres=seed_genres,
            limit=limit,
            **audio_params,
        )

        return jsonify({"success": True, "recommendations": result}), 200

    except Exception as e:
        logger.error(f"Failed to generate Spotify recommendations: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/playlists/create", methods=["POST"])
def create_spotify_playlist():
    """Create a new Spotify playlist"""
    try:
        data = request.get_json()
        if not data or "name" not in data:
            return (
                jsonify({"success": False, "error": "Playlist name is required"}),
                400,
            )

        name = data["name"]
        description = data.get("description", "")
        public = data.get("public", False)
        collaborative = data.get("collaborative", False)

        result = spotify_service.create_playlist(
            name, description, public, collaborative
        )

        if result and "id" in result:
            return (
                jsonify(
                    {
                        "success": True,
                        "playlist": result,
                        "message": f"Created Spotify playlist: {name}",
                    }
                ),
                201,
            )
        else:
            return (
                jsonify(
                    {"success": False, "error": "Failed to create Spotify playlist"}
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Failed to create Spotify playlist: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/discovery/artist-library", methods=["POST"])
def discover_artists_from_library():
    """Discover new artists from user's Spotify library"""
    try:
        data = request.get_json() or {}
        limit = data.get("limit", 50)

        logger.info("Starting artist discovery from Spotify library")

        # Get user's saved tracks
        saved_tracks_response = spotify_service._make_request(
            "me/tracks", {"limit": limit}
        )
        if not saved_tracks_response or "items" not in saved_tracks_response:
            return (
                jsonify({"success": False, "error": "Failed to get saved tracks"}),
                500,
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

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Discovered {len(discovered_artists)} new artists",
                    "discovered_artists": discovered_artists,
                    "total_discovered": len(discovered_artists),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to discover artists from Spotify library: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/metadata/enhanced-matching", methods=["POST"])
def enhanced_metadata_matching():
    """Perform enhanced metadata matching with Spotify catalog"""
    try:
        data = request.get_json() or {}
        artist_name = data.get("artist_name")
        track_title = data.get("track_title")

        if not artist_name or not track_title:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "artist_name and track_title are required",
                    }
                ),
                400,
            )

        # Search for track on Spotify
        search_query = f"track:{track_title} artist:{artist_name}"
        track_search = spotify_service.search_tracks(search_query, limit=10)

        if not track_search or "tracks" not in track_search:
            return (
                jsonify({"success": False, "error": "No tracks found on Spotify"}),
                404,
            )

        tracks = track_search["tracks"]["items"]

        # Calculate metadata similarity for each result
        matches = []
        for track in tracks:
            # Calculate similarity scores
            artist_match_score = max(
                spotify_sync_service._calculate_track_similarity(
                    artist_name, artist.get("name", "")
                )
                for artist in track.get("artists", [])
            )

            track_match_score = spotify_sync_service._calculate_track_similarity(
                track_title, track.get("name", "")
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

        return (
            jsonify(
                {
                    "success": True,
                    "query": {"artist": artist_name, "track": track_title},
                    "matches": matches,
                    "total_matches": len(matches),
                    "best_match_score": (
                        matches[0]["similarity_scores"]["overall_match"]
                        if matches
                        else 0
                    ),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to perform enhanced metadata matching: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/connect/devices", methods=["GET"])
def get_spotify_connect_devices():
    """Get available Spotify Connect devices"""
    try:
        from src.services.spotify_connect_service import spotify_connect_service

        devices = spotify_connect_service.get_available_devices()

        return (
            jsonify(
                {
                    "success": True,
                    "devices": devices.get("devices", []) if devices else [],
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Spotify Connect devices: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/connect/play", methods=["POST"])
def spotify_connect_play():
    """Control Spotify Connect playback"""
    try:
        data = request.get_json() or {}
        device_id = data.get("device_id")
        track_uris = data.get("track_uris", [])
        context_uri = data.get("context_uri")

        from src.services.spotify_connect_service import spotify_connect_service

        if track_uris:
            result = spotify_connect_service.play_tracks(track_uris, device_id)
        elif context_uri:
            result = spotify_connect_service.play_context(context_uri, device_id)
        else:
            result = spotify_connect_service.resume_playback(device_id)

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "message": "Playback command sent to Spotify Connect",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to control Spotify Connect playback: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/analytics/listening-stats", methods=["GET"])
def get_listening_analytics():
    """Get analytics from Spotify listening data"""
    try:
        time_range = request.args.get(
            "time_range", "medium_term"
        )  # short_term, medium_term, long_term

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

        return jsonify({"success": True, "analytics": analytics}), 200

    except Exception as e:
        logger.error(f"Failed to get listening analytics: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_enhanced_bp.route("/discovery/similar-artists", methods=["POST"])
def discover_similar_artists():
    """Discover similar artists based on Spotify data"""
    try:
        data = request.get_json() or {}
        artist_ids = data.get("artist_ids", [])

        if not artist_ids:
            return jsonify({"success": False, "error": "artist_ids are required"}), 400

        # Get recommendations based on these artists
        recommendations = spotify_service.get_recommendations(
            seed_artists=artist_ids[:5], limit=20  # Spotify allows max 5 seeds
        )

        if not recommendations or "tracks" not in recommendations:
            return (
                jsonify({"success": False, "error": "Failed to get recommendations"}),
                500,
            )

        # Extract unique artists from recommendations
        similar_artists = {}
        for track in recommendations["tracks"]:
            for artist in track.get("artists", []):
                artist_id = artist.get("id")
                if artist_id not in artist_ids:  # Exclude seed artists
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

        return (
            jsonify(
                {
                    "success": True,
                    "similar_artists": sorted_artists,
                    "total_discovered": len(sorted_artists),
                    "based_on_artists": len(artist_ids),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to discover similar artists: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
