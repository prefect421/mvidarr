"""
Spotify-specific metadata enrichment endpoints
"""

from flask import Blueprint, jsonify

from src.database.connection import get_db
from src.database.models import Artist
from src.middleware.simple_auth_middleware import auth_required
from src.utils.logger import get_logger

spotify_enrichment_bp = Blueprint(
    "spotify_enrichment", __name__, url_prefix="/metadata-enrichment/spotify"
)
logger = get_logger("mvidarr.api.spotify_enrichment")


@spotify_enrichment_bp.route("/recommendations/<int:artist_id>", methods=["GET"])
@auth_required
def get_spotify_recommendations(artist_id: int):
    """Get Spotify recommendations and related artists for a specific artist"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter(Artist.id == artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            if not artist.spotify_id:
                return (
                    jsonify(
                        {
                            "error": "No Spotify ID found for this artist",
                            "recommendations": [],
                            "related_artists": [],
                        }
                    ),
                    200,
                )

            # Import Spotify service
            from src.services.spotify_service import spotify_service

            try:
                # Get related artists
                related_response = spotify_service.get_related_artists(
                    artist.spotify_id
                )
                related_artists = []

                if related_response and "artists" in related_response:
                    for related_artist in related_response["artists"]:
                        related_artists.append(
                            {
                                "name": related_artist.get("name", ""),
                                "spotify_id": related_artist.get("id", ""),
                                "popularity": related_artist.get("popularity", 0),
                                "genres": related_artist.get("genres", []),
                                "external_urls": related_artist.get(
                                    "external_urls", {}
                                ),
                            }
                        )

                # Get recommendations using this artist as seed
                recommendations_response = spotify_service.get_recommendations(
                    seed_artists=[artist.spotify_id], limit=10
                )

                recommendations = []
                if recommendations_response and "tracks" in recommendations_response:
                    for track in recommendations_response["tracks"]:
                        track_artists = []
                        for track_artist in track.get("artists", []):
                            track_artists.append(track_artist.get("name", ""))

                        recommendations.append(
                            {
                                "name": track.get("name", ""),
                                "artists": track_artists,
                                "spotify_id": track.get("id", ""),
                                "popularity": track.get("popularity", 0),
                                "external_urls": track.get("external_urls", {}),
                                "preview_url": track.get("preview_url"),
                                "album": {
                                    "name": track.get("album", {}).get("name", ""),
                                    "images": track.get("album", {}).get("images", []),
                                },
                            }
                        )

                return (
                    jsonify(
                        {
                            "artist_id": artist_id,
                            "artist_name": artist.name,
                            "spotify_id": artist.spotify_id,
                            "related_artists": related_artists,
                            "recommendations": recommendations,
                        }
                    ),
                    200,
                )

            except Exception as spotify_error:
                logger.error(
                    f"Spotify API error for artist {artist_id}: {spotify_error}"
                )
                return (
                    jsonify(
                        {
                            "error": f"Spotify API error: {str(spotify_error)}",
                            "recommendations": [],
                            "related_artists": [],
                        }
                    ),
                    200,
                )

    except Exception as e:
        logger.error(
            f"Failed to get Spotify recommendations for artist {artist_id}: {e}"
        )
        return jsonify({"error": str(e)}), 500
