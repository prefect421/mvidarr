"""
MusicBrainz API endpoints for frontend integration
"""

from flask import Blueprint, jsonify, request

from src.middleware.simple_auth_middleware import auth_required
from src.services.musicbrainz_service import musicbrainz_service
from src.utils.logger import get_logger

musicbrainz_bp = Blueprint("musicbrainz", __name__, url_prefix="/musicbrainz")
logger = get_logger("mvidarr.api.musicbrainz")


@musicbrainz_bp.route("/search-artist", methods=["POST"])
@auth_required
def search_artist():
    """Search for artists in MusicBrainz database"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON payload required"}), 400

        data = request.get_json()
        query = data.get("query", "").strip()

        if not query:
            return jsonify({"error": "Query parameter is required"}), 400

        # TEMPORARY DEBUG: Direct API call to MusicBrainz bypassing service
        from urllib.parse import quote_plus

        import requests

        try:
            # Direct MusicBrainz API call
            base_url = "https://musicbrainz.org/ws/2"
            endpoint = "artist"
            params = {
                "query": f'artist:"{query}"',
                "limit": 10,
                "offset": 0,
                "fmt": "json",
            }
            headers = {
                "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr)",
                "Accept": "application/json",
            }

            response = requests.get(
                f"{base_url}/{endpoint}", params=params, headers=headers, timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                artists = []

                for artist in data.get("artists", []):
                    artist_info = {
                        "mbid": artist.get("id"),
                        "name": artist.get("name"),
                        "sort_name": artist.get("sort-name"),
                        "type": artist.get("type"),
                        "country": artist.get("country"),
                        "area": (
                            artist.get("area", {}).get("name")
                            if artist.get("area")
                            else None
                        ),
                        "confidence": 1.0,  # Direct match confidence
                        "disambiguation": artist.get("disambiguation", ""),
                    }
                    artists.append(artist_info)

                return (
                    jsonify(
                        {
                            "success": True,
                            "query": query,
                            "results": artists,
                            "count": len(artists),
                            "debug": "Direct MusicBrainz API call",
                        }
                    ),
                    200,
                )

        except Exception as direct_error:
            logger.error(f"Direct MusicBrainz API call failed: {direct_error}")

        # Fallback to original service call
        results = musicbrainz_service.search_artist(query)

        return (
            jsonify(
                {
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to search MusicBrainz artists: {e}")
        return jsonify({"error": str(e)}), 500


@musicbrainz_bp.route("/test-direct", methods=["POST"])
@auth_required
def test_direct_api():
    """Test direct MusicBrainz API call for debugging"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON payload required"}), 400

        data = request.get_json()
        query = data.get("query", "Bad Religion").strip()

        # Direct test call
        import requests

        try:
            base_url = "https://musicbrainz.org/ws/2"
            params = {"query": f'artist:"{query}"', "limit": 5, "fmt": "json"}
            headers = {
                "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr)",
                "Accept": "application/json",
            }

            response = requests.get(
                f"{base_url}/artist", params=params, headers=headers, timeout=15
            )

            return (
                jsonify(
                    {
                        "test": "direct_api_call",
                        "status_code": response.status_code,
                        "response_size": len(response.text),
                        "url": response.url,
                        "headers_sent": dict(headers),
                        "raw_response": (
                            response.text[:500] + "..."
                            if len(response.text) > 500
                            else response.text
                        ),
                    }
                ),
                200,
            )

        except Exception as e:
            return (
                jsonify(
                    {
                        "test": "direct_api_call",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                ),
                200,
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@musicbrainz_bp.route("/artist/<mbid>", methods=["GET"])
@auth_required
def get_artist_details(mbid: str):
    """Get detailed artist information by MusicBrainz ID"""
    try:
        if not mbid:
            return jsonify({"error": "MusicBrainz ID is required"}), 400

        # Get artist details from MusicBrainz
        artist_data = musicbrainz_service.get_artist_by_mbid(mbid)

        if not artist_data:
            return jsonify({"error": "Artist not found in MusicBrainz"}), 404

        return jsonify({"success": True, "mbid": mbid, "artist": artist_data}), 200

    except Exception as e:
        logger.error(f"Failed to get MusicBrainz artist details for {mbid}: {e}")
        return jsonify({"error": str(e)}), 500


@musicbrainz_bp.route("/test", methods=["GET"])
@auth_required
def test_connection():
    """Test MusicBrainz API connectivity"""
    try:
        is_connected = musicbrainz_service.test_connection()

        return jsonify(
            {
                "success": is_connected,
                "service": "MusicBrainz",
                "status": "connected" if is_connected else "disconnected",
                "enabled": musicbrainz_service.enabled,
            }
        ), (200 if is_connected else 503)

    except Exception as e:
        logger.error(f"MusicBrainz connection test failed: {e}")
        return (
            jsonify(
                {
                    "success": False,
                    "service": "MusicBrainz",
                    "status": "error",
                    "error": str(e),
                }
            ),
            500,
        )
