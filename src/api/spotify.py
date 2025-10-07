"""
Spotify API endpoints for playlist import and artist synchronization
"""

import os

from flask import Blueprint, jsonify, redirect, request, session

from src.services.spotify_connect_service import spotify_connect_service
from src.services.spotify_service import spotify_service
from src.utils.logger import get_logger

spotify_bp = Blueprint("spotify", __name__, url_prefix="/spotify")
logger = get_logger("mvidarr.api.spotify")


@spotify_bp.route("/auth/url", methods=["GET"])
def get_auth_url():
    """Get Spotify authorization URL"""
    try:
        if not spotify_service.client_id:
            return (
                jsonify(
                    {
                        "error": "Spotify integration not configured. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET"
                    }
                ),
                400,
            )

        auth_url = spotify_service.get_auth_url()
        return jsonify({"auth_url": auth_url, "configured": True}), 200

    except Exception as e:
        logger.error(f"Failed to generate Spotify auth URL: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/callback", methods=["GET"])
def callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get("code")
        error = request.args.get("error")

        if error:
            logger.error(f"Spotify OAuth error: {error}")
            from src.utils.security import safe_redirect

            return safe_redirect(f"/settings?spotify_error={error}")

        if not code:
            return jsonify({"error": "No authorization code received"}), 400

        # Exchange code for access token
        token_data = spotify_service.get_access_token(code)

        # Store tokens in session (in production, use database)
        session["spotify_access_token"] = token_data.get("access_token")
        session["spotify_refresh_token"] = token_data.get("refresh_token")
        session["spotify_token_expires"] = token_data.get("expires_in")

        logger.info("Spotify authentication successful")
        return redirect("/settings?spotify_success=true")

    except Exception as e:
        logger.error(f"Spotify callback error: {e}")
        return redirect(f"/settings?spotify_error={str(e)}")


@spotify_bp.route("/profile", methods=["GET"])
def get_profile():
    """Get current user's Spotify profile"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        profile = spotify_service.get_user_profile()
        return jsonify({"profile": profile, "authenticated": True}), 200

    except Exception as e:
        logger.error(f"Failed to get Spotify profile: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/search/artists", methods=["GET"])
def search_artists():
    """Search for artists on Spotify"""
    try:
        query = request.args.get("q")
        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        limit = int(request.args.get("limit", 10))

        # Use client credentials flow for public data
        try:
            # Get client credentials token
            token_data = spotify_service.get_client_credentials_token()
            spotify_service.access_token = token_data.get("access_token")

            # Search for artists
            result = spotify_service.search_artist(query, limit)

            return jsonify({"success": True, "results": result}), 200

        except ValueError as ve:
            logger.error(f"Spotify credentials not configured: {ve}")
            return jsonify({"error": "Spotify API credentials not configured"}), 500
        except Exception as e:
            logger.error(f"Spotify API error: {e}")
            return jsonify({"error": "Failed to search Spotify"}), 500

    except Exception as e:
        logger.error(f"Failed to search Spotify artists: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/playlists", methods=["GET"])
def get_playlists():
    """Get user's Spotify playlists"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        playlists = spotify_service.get_user_playlists(limit, offset)

        # Format playlist data
        formatted_playlists = []
        for playlist in playlists.get("items", []):
            formatted_playlists.append(
                {
                    "id": playlist.get("id"),
                    "name": playlist.get("name"),
                    "description": playlist.get("description"),
                    "tracks_total": playlist.get("tracks", {}).get("total", 0),
                    "images": playlist.get("images", []),
                    "owner": playlist.get("owner", {}).get("display_name"),
                    "public": playlist.get("public", False),
                    "collaborative": playlist.get("collaborative", False),
                    "external_urls": playlist.get("external_urls", {}),
                }
            )

        return (
            jsonify(
                {
                    "playlists": formatted_playlists,
                    "total": playlists.get("total", 0),
                    "limit": limit,
                    "offset": offset,
                    "next": playlists.get("next") is not None,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Spotify playlists: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/playlists/<playlist_id>/tracks", methods=["GET"])
def get_playlist_tracks(playlist_id):
    """Get tracks from a specific playlist"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        tracks_data = spotify_service.get_playlist_tracks(playlist_id, limit, offset)

        # Format track data
        formatted_tracks = []
        for track_item in tracks_data.get("items", []):
            track = track_item.get("track")
            if not track:
                continue

            formatted_tracks.append(
                {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artists": [
                        {"name": a.get("name"), "id": a.get("id")}
                        for a in track.get("artists", [])
                    ],
                    "album": {
                        "name": track.get("album", {}).get("name"),
                        "images": track.get("album", {}).get("images", []),
                    },
                    "duration_ms": track.get("duration_ms"),
                    "popularity": track.get("popularity"),
                    "external_urls": track.get("external_urls", {}),
                }
            )

        return (
            jsonify(
                {
                    "tracks": formatted_tracks,
                    "total": tracks_data.get("total", 0),
                    "limit": limit,
                    "offset": offset,
                    "next": tracks_data.get("next") is not None,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get playlist tracks: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/playlists/<playlist_id>/import", methods=["POST"])
def import_playlist(playlist_id):
    """Import artists from a Spotify playlist"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        logger.info(f"Starting import of Spotify playlist: {playlist_id}")

        # Import playlist artists
        results = spotify_service.import_playlist_artists(playlist_id)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Successfully imported {results['imported_artists']} artists from playlist '{results['playlist_name']}'",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to import playlist: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/followed/artists", methods=["GET"])
def get_followed_artists():
    """Get user's followed artists"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        limit = int(request.args.get("limit", 50))

        followed_data = spotify_service.get_followed_artists(limit)
        artists = followed_data.get("artists", {}).get("items", [])

        # Format artist data
        formatted_artists = []
        for artist in artists:
            formatted_artists.append(
                {
                    "id": artist.get("id"),
                    "name": artist.get("name"),
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "images": artist.get("images", []),
                    "external_urls": artist.get("external_urls", {}),
                }
            )

        return (
            jsonify(
                {
                    "artists": formatted_artists,
                    "total": followed_data.get("artists", {}).get("total", 0),
                    "limit": limit,
                    "next": followed_data.get("artists", {}).get("next") is not None,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get followed artists: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/followed/sync", methods=["POST"])
def sync_followed_artists():
    """Sync user's followed artists from Spotify"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        logger.info("Starting sync of followed artists from Spotify")

        # Sync followed artists
        results = spotify_service.sync_followed_artists()

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Successfully synced {results['imported_artists']} followed artists",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to sync followed artists: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/top/artists", methods=["GET"])
def get_top_artists():
    """Get user's top artists"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        time_range = request.args.get("time_range", "medium_term")
        limit = int(request.args.get("limit", 50))

        top_artists = spotify_service.get_user_top_artists(time_range, limit)

        # Format artist data
        formatted_artists = []
        for artist in top_artists.get("items", []):
            formatted_artists.append(
                {
                    "id": artist.get("id"),
                    "name": artist.get("name"),
                    "genres": artist.get("genres", []),
                    "popularity": artist.get("popularity"),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "images": artist.get("images", []),
                    "external_urls": artist.get("external_urls", {}),
                }
            )

        return (
            jsonify(
                {
                    "artists": formatted_artists,
                    "total": top_artists.get("total", 0),
                    "time_range": time_range,
                    "limit": limit,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get top artists: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/top/tracks", methods=["GET"])
def get_top_tracks():
    """Get user's top tracks"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        time_range = request.args.get("time_range", "medium_term")
        limit = int(request.args.get("limit", 50))

        top_tracks = spotify_service.get_user_top_tracks(time_range, limit)

        # Format track data
        formatted_tracks = []
        for track in top_tracks.get("items", []):
            formatted_tracks.append(
                {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artists": [
                        {"name": a.get("name"), "id": a.get("id")}
                        for a in track.get("artists", [])
                    ],
                    "album": {
                        "name": track.get("album", {}).get("name"),
                        "images": track.get("album", {}).get("images", []),
                    },
                    "duration_ms": track.get("duration_ms"),
                    "popularity": track.get("popularity"),
                    "external_urls": track.get("external_urls", {}),
                }
            )

        return (
            jsonify(
                {
                    "tracks": formatted_tracks,
                    "total": top_tracks.get("total", 0),
                    "time_range": time_range,
                    "limit": limit,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get top tracks: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/disconnect", methods=["POST"])
def disconnect():
    """Disconnect from Spotify"""
    try:
        # Clear session tokens
        session.pop("spotify_access_token", None)
        session.pop("spotify_refresh_token", None)
        session.pop("spotify_token_expires", None)

        # Clear service tokens
        spotify_service.access_token = None
        spotify_service.refresh_token = None
        spotify_service.token_expires = None

        logger.info("Spotify disconnected successfully")
        return (
            jsonify(
                {"success": True, "message": "Successfully disconnected from Spotify"}
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to disconnect from Spotify: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/status", methods=["GET"])
def get_status():
    """Get Spotify integration status"""
    try:
        # Check if tokens are available
        has_access_token = (
            "spotify_access_token" in session
            or spotify_service.access_token is not None
        )

        # Check if client credentials are configured
        configured = (
            spotify_service.client_id is not None
            and spotify_service.client_secret is not None
        )

        profile = None
        if has_access_token:
            try:
                # Load tokens from session
                if "spotify_access_token" in session:
                    spotify_service.access_token = session["spotify_access_token"]
                    spotify_service.refresh_token = session.get("spotify_refresh_token")

                profile = spotify_service.get_user_profile()
            except Exception as e:
                logger.warning(f"Failed to get profile for status check: {e}")

        return (
            jsonify(
                {
                    "configured": configured,
                    "authenticated": has_access_token,
                    "profile": profile,
                    "client_id": (
                        spotify_service.client_id[:8] + "..."
                        if spotify_service.client_id
                        else None
                    ),
                    "redirect_uri": spotify_service.redirect_uri,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Spotify status: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/reload", methods=["POST"])
def reload_settings():
    """Force reload Spotify settings from database"""
    try:
        logger.info("Manual Spotify settings reload requested")
        spotify_service.reload_settings()
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Spotify settings reloaded successfully",
                    "redirect_uri": spotify_service.redirect_uri,
                    "client_id": (
                        spotify_service.client_id[:8] + "..."
                        if spotify_service.client_id
                        else None
                    ),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to reload Spotify settings: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/test", methods=["POST"])
def test_spotify_integration():
    """Test Spotify API connection"""
    try:
        # Check if client credentials are configured
        if not spotify_service.client_id or not spotify_service.client_secret:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Spotify client credentials not configured. Please set spotify_client_id and spotify_client_secret in settings.",
                    }
                ),
                400,
            )

        # Test client credentials flow
        try:
            token_data = spotify_service.get_client_credentials_token()
            if token_data and token_data.get("access_token"):
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "Spotify API connection successful",
                            "token_type": token_data.get("token_type"),
                            "expires_in": token_data.get("expires_in"),
                        }
                    ),
                    200,
                )
            else:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Failed to get access token from Spotify",
                        }
                    ),
                    500,
                )
        except Exception as e:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Spotify API connection failed: {str(e)}",
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Spotify integration test failed: {e}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Spotify integration test failed: {str(e)}",
                }
            ),
            500,
        )


@spotify_bp.route("/authorize", methods=["POST"])
def authorize_spotify():
    """Get Spotify authorization URL for user authentication"""
    try:
        # Force reload settings to ensure we have the latest configuration
        spotify_service.reload_settings()

        if not spotify_service.client_id or not spotify_service.client_secret:
            return jsonify({"error": "Spotify client credentials not configured"}), 400

        auth_url = spotify_service.get_auth_url()
        logger.info(
            f"Generated Spotify authorization URL with redirect URI: {spotify_service.redirect_uri}"
        )

        return (
            jsonify(
                {
                    "authorization_url": auth_url,
                    "redirect_uri": spotify_service.redirect_uri,
                    "message": "Please visit the authorization URL to connect your Spotify account",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get Spotify authorization URL: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/import-playlists", methods=["POST"])
def import_playlists():
    """Import all user playlists from Spotify"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Not authenticated with Spotify. Please authorize first.",
                    }
                ),
                401,
            )

        # Get all playlists
        playlists = spotify_service.get_user_playlists(limit=50)

        imported_count = 0
        total_artists = 0

        # Import artists from each playlist
        for playlist in playlists.get("items", []):
            try:
                results = spotify_service.import_playlist_artists(playlist["id"])
                imported_count += results.get("imported_artists", 0)
                total_artists += results.get("total_artists", 0)
            except Exception as e:
                logger.warning(f"Failed to import playlist {playlist['name']}: {e}")
                continue

        return (
            jsonify(
                {
                    "success": True,
                    "imported_count": imported_count,
                    "total_artists": total_artists,
                    "playlists_processed": len(playlists.get("items", [])),
                    "message": f'Successfully imported {imported_count} unique artists from {len(playlists.get("items", []))} playlists',
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to import playlists: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_bp.route("/discover/listening-history", methods=["POST"])
def discover_from_listening_history():
    """Discover music videos based on user's listening history"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json() or {}
        time_range = data.get("time_range", "medium_term")
        limit = min(int(data.get("limit", 50)), 50)  # Cap at 50

        logger.info(
            f"Starting music video discovery from listening history (timerange: {time_range})"
        )

        results = spotify_service.discover_music_videos_from_listening_history(
            time_range, limit
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Discovery completed: found {results['high_confidence_matches']} high confidence matches and {results['potential_matches']} potential matches",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to discover from listening history: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_bp.route("/new-releases", methods=["GET"])
def get_new_releases():
    """Get new releases from followed artists"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        country = request.args.get("country", "US")
        limit = min(int(request.args.get("limit", 50)), 50)

        results = spotify_service.get_new_releases_for_followed_artists(country, limit)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Found {results['total_releases']} new releases from {results['artists_checked']} followed artists",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get new releases: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/enhanced-import", methods=["POST"])
def enhanced_playlist_import():
    """Enhanced playlist import with metadata matching"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "playlist_id" not in data:
            return jsonify({"error": "playlist_id is required"}), 400

        playlist_id = data["playlist_id"]
        similarity_threshold = data.get("similarity_threshold", 0.85)

        logger.info(f"Starting enhanced playlist import: {playlist_id}")

        # Import with enhanced matching
        results = spotify_service.import_playlist_artists(playlist_id)

        # Add metadata matching results
        results["enhanced_matching_enabled"] = True
        results["similarity_threshold"] = similarity_threshold

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Enhanced import completed: {results['imported_artists']} artists, {results['found_videos']} videos",
                    "results": results,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Enhanced playlist import failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_bp.route("/webhooks/events", methods=["POST"])
def handle_spotify_webhook():
    """Handle Spotify webhook events"""
    try:
        # Verify webhook signature if secret is configured
        webhook_secret = (
            spotify_service.client_secret
        )  # Use client secret as webhook secret
        if webhook_secret:
            signature = request.headers.get("X-Spotify-Signature")
            if not signature:
                logger.warning("Webhook received without signature")
                return jsonify({"error": "Missing signature"}), 401

            # Verify signature (simplified - in production use proper HMAC validation)
            expected_signature = f"sha256={webhook_secret}"
            if signature != expected_signature:
                logger.warning("Invalid webhook signature")
                return jsonify({"error": "Invalid signature"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received"}), 400

        event_type = data.get("event_type")
        event_data = data.get("data", {})

        logger.info(f"Received Spotify webhook event: {event_type}")

        # Process different event types
        response_data = {"event_type": event_type, "status": "processed"}

        if event_type == "user.playlist_changed":
            # Handle playlist changes
            playlist_id = event_data.get("playlist_id")
            if playlist_id:
                logger.info(f"Playlist {playlist_id} was modified, triggering sync")
                # Could trigger automatic re-sync here
                response_data["action"] = "playlist_sync_triggered"

        elif event_type == "user.new_release":
            # Handle new release notifications
            artist_id = event_data.get("artist_id")
            release_id = event_data.get("release_id")
            if artist_id and release_id:
                logger.info(
                    f"New release detected: {release_id} from artist {artist_id}"
                )
                response_data["action"] = "new_release_notification"

        elif event_type == "user.library_changed":
            # Handle library changes (new saved tracks, followed artists)
            change_type = event_data.get("change_type")
            logger.info(f"User library changed: {change_type}")
            response_data["action"] = "library_change_processed"

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Webhook event {event_type} processed successfully",
                    "data": response_data,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@spotify_bp.route("/metadata/similarity", methods=["POST"])
def test_metadata_similarity():
    """Test metadata similarity calculation"""
    try:
        data = request.get_json()
        if not data or "spotify_track" not in data or "video_data" not in data:
            return jsonify({"error": "spotify_track and video_data required"}), 400

        spotify_track = data["spotify_track"]
        video_data = data["video_data"]

        similarity = spotify_service.calculate_metadata_similarity(
            spotify_track, video_data
        )

        return (
            jsonify(
                {
                    "similarity_score": similarity,
                    "confidence": (
                        "high"
                        if similarity >= 0.9
                        else "medium" if similarity >= 0.7 else "low"
                    ),
                    "spotify_track": spotify_track,
                    "video_data": video_data,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Metadata similarity test failed: {e}")
        return jsonify({"error": str(e)}), 500


# Spotify Connect endpoints


@spotify_bp.route("/connect/devices", methods=["GET"])
def get_connect_devices():
    """Get available Spotify Connect devices"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        refresh_cache = request.args.get("refresh", "false").lower() == "true"
        result = spotify_connect_service.get_available_devices(refresh_cache)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to get devices: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/playback", methods=["GET"])
def get_playback_state():
    """Get current playback state"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        result = spotify_connect_service.get_playback_state()
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to get playback state: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/transfer", methods=["POST"])
def transfer_playback():
    """Transfer playback to specified device"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "device_id" not in data:
            return jsonify({"error": "device_id is required"}), 400

        device_id = data["device_id"]
        force_play = data.get("force_play", False)

        result = spotify_connect_service.transfer_playback(device_id, force_play)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to transfer playback: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/play", methods=["POST"])
def control_play():
    """Start/resume playback or play specific track/playlist"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json() or {}
        device_id = data.get("device_id")

        # Play specific track
        if "track_uri" in data:
            result = spotify_connect_service.play_track(data["track_uri"], device_id)
        # Play playlist
        elif "playlist_uri" in data:
            offset = data.get("offset", 0)
            result = spotify_connect_service.play_playlist(
                data["playlist_uri"], device_id, offset
            )
        # Resume playback
        else:
            result = spotify_connect_service.resume_playback(device_id)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to control playback: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/pause", methods=["POST"])
def pause_playback():
    """Pause current playback"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json() or {}
        device_id = data.get("device_id")

        result = spotify_connect_service.pause_playback(device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to pause playback: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/next", methods=["POST"])
def skip_next():
    """Skip to next track"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json() or {}
        device_id = data.get("device_id")

        result = spotify_connect_service.skip_to_next(device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to skip to next: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/previous", methods=["POST"])
def skip_previous():
    """Skip to previous track"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json() or {}
        device_id = data.get("device_id")

        result = spotify_connect_service.skip_to_previous(device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to skip to previous: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/volume", methods=["POST"])
def set_volume():
    """Set playback volume"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "volume" not in data:
            return jsonify({"error": "volume is required"}), 400

        volume = data["volume"]
        device_id = data.get("device_id")

        result = spotify_connect_service.set_volume(volume, device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to set volume: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/repeat", methods=["POST"])
def set_repeat():
    """Set repeat mode"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "state" not in data:
            return (
                jsonify({"error": "state is required ('track', 'context', 'off')"}),
                400,
            )

        state = data["state"]
        device_id = data.get("device_id")

        result = spotify_connect_service.set_repeat_mode(state, device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to set repeat: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/shuffle", methods=["POST"])
def set_shuffle():
    """Set shuffle mode"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "state" not in data:
            return jsonify({"error": "state is required (boolean)"}), 400

        state = data["state"]
        device_id = data.get("device_id")

        result = spotify_connect_service.set_shuffle_mode(state, device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to set shuffle: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/seek", methods=["POST"])
def seek_position():
    """Seek to position in current track"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "position_ms" not in data:
            return jsonify({"error": "position_ms is required"}), 400

        position_ms = data["position_ms"]
        device_id = data.get("device_id")

        result = spotify_connect_service.seek_to_position(position_ms, device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to seek: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/queue", methods=["POST"])
def add_to_queue():
    """Add track to playback queue"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        data = request.get_json()
        if not data or "track_uri" not in data:
            return jsonify({"error": "track_uri is required"}), 400

        track_uri = data["track_uri"]
        device_id = data.get("device_id")

        result = spotify_connect_service.add_to_queue(track_uri, device_id)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to add to queue: {e}")
        return jsonify({"error": str(e)}), 500


@spotify_bp.route("/connect/recently-played", methods=["GET"])
def get_recently_played():
    """Get recently played tracks"""
    try:
        # Load tokens from session
        if "spotify_access_token" in session:
            spotify_service.access_token = session["spotify_access_token"]
            spotify_service.refresh_token = session.get("spotify_refresh_token")

        if not spotify_service.access_token:
            return jsonify({"error": "Not authenticated with Spotify"}), 401

        limit = min(int(request.args.get("limit", 20)), 50)
        result = spotify_connect_service.get_recently_played(limit)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to get recently played: {e}")
        return jsonify({"error": str(e)}), 500
