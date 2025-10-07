"""
IMVDb API endpoints
"""

from flask import Blueprint, jsonify, request

from src.services.imvdb_analytics_service import imvdb_analytics_service
from src.services.imvdb_discovery_service import imvdb_discovery_service
from src.services.imvdb_service import imvdb_service
from src.utils.logger import get_logger

imvdb_bp = Blueprint("imvdb", __name__, url_prefix="/imvdb")
logger = get_logger("mvidarr.api.imvdb")


@imvdb_bp.route("/search-artist", methods=["GET"])
def search_artist():
    """Search for artists in IMVDb"""
    try:
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        # Search for multiple artists
        artists = imvdb_service.search_artists(query, limit=10)

        return jsonify({"success": True, "results": artists, "count": len(artists)})

    except Exception as e:
        logger.error(f"Error searching IMVDb artists: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/search-videos", methods=["GET"])
def search_videos():
    """Search for videos in IMVDb"""
    try:
        query = request.args.get("q", "").strip()
        artist_id = request.args.get("artist_id")

        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        if artist_id:
            # Get videos for specific artist
            result = imvdb_service.search_artist_videos(query, limit=25)
            videos = result.get("videos", []) if result else []
        else:
            # General video search
            videos = imvdb_service.search_videos(query)

        return jsonify({"success": True, "results": videos, "count": len(videos)})

    except Exception as e:
        logger.error(f"Error searching IMVDb videos: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/artist/<int:artist_id>", methods=["GET"])
def get_artist_details(artist_id):
    """Get detailed artist information from IMVDb"""
    try:
        artist = imvdb_service.get_artist_by_id(artist_id)

        if not artist:
            return jsonify({"error": "Artist not found"}), 404

        return jsonify({"success": True, "artist": artist})

    except Exception as e:
        logger.error(f"Error getting IMVDb artist details: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/video/<int:video_id>", methods=["GET"])
def get_video_details(video_id):
    """Get detailed video information from IMVDb"""
    try:
        video = imvdb_service.get_video_by_id(video_id)

        if not video:
            return jsonify({"error": "Video not found"}), 404

        return jsonify({"success": True, "video": video})

    except Exception as e:
        logger.error(f"Error getting IMVDb video details: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/advanced-search", methods=["POST"])
def advanced_search():
    """Advanced video search with filtering"""
    try:
        filters = request.get_json() or {}

        # Validate required parameters
        if not filters.get("query") and not any(
            [
                filters.get("genre"),
                filters.get("year_min"),
                filters.get("year_max"),
                filters.get("directors"),
                filters.get("artists"),
            ]
        ):
            return jsonify({"error": "At least one search criteria is required"}), 400

        result = imvdb_service.advanced_search_videos(filters)

        return jsonify({"success": True, "results": result})

    except Exception as e:
        logger.error(f"Error in advanced search: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/search-by-genre", methods=["GET"])
def search_by_genre():
    """Search videos by genre"""
    try:
        genre = request.args.get("genre", "").strip()
        limit = int(request.args.get("limit", 50))

        if not genre:
            return jsonify({"error": "Genre parameter is required"}), 400

        videos = imvdb_service.search_videos_by_genre(genre, limit)

        return jsonify(
            {"success": True, "results": videos, "count": len(videos), "genre": genre}
        )

    except Exception as e:
        logger.error(f"Error searching by genre: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/search-by-year", methods=["GET"])
def search_by_year():
    """Search videos by year range"""
    try:
        year_min = request.args.get("year_min", type=int)
        year_max = request.args.get("year_max", type=int)
        limit = int(request.args.get("limit", 50))

        if not year_min and not year_max:
            return jsonify({"error": "At least year_min or year_max is required"}), 400

        videos = imvdb_service.search_videos_by_year_range(
            year_min or 1900, year_max or 2030, limit
        )

        return jsonify(
            {
                "success": True,
                "results": videos,
                "count": len(videos),
                "year_range": {"min": year_min, "max": year_max},
            }
        )

    except Exception as e:
        logger.error(f"Error searching by year: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/search-by-director", methods=["GET"])
def search_by_director():
    """Search videos by director"""
    try:
        director = request.args.get("director", "").strip()
        limit = int(request.args.get("limit", 50))

        if not director:
            return jsonify({"error": "Director parameter is required"}), 400

        videos = imvdb_service.search_videos_by_director(director, limit)

        return jsonify(
            {
                "success": True,
                "results": videos,
                "count": len(videos),
                "director": director,
            }
        )

    except Exception as e:
        logger.error(f"Error searching by director: {e}")
        return jsonify({"error": str(e)}), 500


@imvdb_bp.route("/trending", methods=["GET"])
def get_trending():
    """Get trending/popular videos"""
    try:
        days = int(request.args.get("days", 7))
        limit = int(request.args.get("limit", 20))

        videos = imvdb_service.get_trending_videos(days, limit)

        return jsonify(
            {
                "success": True,
                "results": videos,
                "count": len(videos),
                "parameters": {"days": days, "limit": limit},
            }
        )

    except Exception as e:
        logger.error(f"Error getting trending videos: {e}")
        return jsonify({"error": str(e)}), 500


# Discovery endpoints


@imvdb_bp.route("/discovery/run", methods=["POST"])
def run_discovery():
    """Run automated video discovery"""
    try:
        data = request.get_json() or {}
        artist_ids = data.get("artist_ids")
        force = data.get("force", False)

        result = imvdb_discovery_service.discover_new_videos(artist_ids, force)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error running discovery: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/discovery/trending", methods=["GET"])
def discover_trending():
    """Discover trending videos and suggest new artists"""
    try:
        limit = int(request.args.get("limit", 20))

        result = imvdb_discovery_service.discover_trending_videos(limit)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error discovering trending: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/discovery/similar-artists/<int:artist_id>", methods=["GET"])
def discover_similar_artists(artist_id):
    """Discover artists similar to a given artist"""
    try:
        limit = int(request.args.get("limit", 10))

        result = imvdb_discovery_service.discover_similar_artists(artist_id, limit)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error discovering similar artists: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/discovery/stats", methods=["GET"])
def get_discovery_stats():
    """Get discovery statistics"""
    try:
        stats = imvdb_discovery_service.get_discovery_statistics()

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        logger.error(f"Error getting discovery stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Quality tracking endpoints


@imvdb_bp.route("/quality/analyze", methods=["POST"])
def analyze_video_quality():
    """Analyze quality of IMVDb video data"""
    try:
        data = request.get_json()
        if not data or "video_data" not in data:
            return jsonify({"error": "video_data is required"}), 400

        video_data = data["video_data"]
        analysis = imvdb_service.analyze_video_quality(video_data)

        return jsonify({"success": True, "quality_analysis": analysis})

    except Exception as e:
        logger.error(f"Error analyzing video quality: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/quality/rank-videos", methods=["POST"])
def rank_videos_by_quality():
    """Rank videos by quality and user preferences"""
    try:
        data = request.get_json()
        if not data or "videos" not in data:
            return jsonify({"error": "videos array is required"}), 400

        videos = data["videos"]
        user_id = data.get("user_id")

        ranked_videos = imvdb_service.rank_videos_by_preferences(videos, user_id)

        return jsonify(
            {
                "success": True,
                "ranked_videos": ranked_videos,
                "total_videos": len(ranked_videos),
            }
        )

    except Exception as e:
        logger.error(f"Error ranking videos by quality: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/quality/statistics", methods=["POST"])
def get_quality_statistics():
    """Get quality statistics for a list of videos"""
    try:
        data = request.get_json()
        if not data or "videos" not in data:
            return jsonify({"error": "videos array is required"}), 400

        videos = data["videos"]
        statistics = imvdb_service.get_quality_statistics(videos)

        return jsonify({"success": True, "statistics": statistics})

    except Exception as e:
        logger.error(f"Error getting quality statistics: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/quality/preferences", methods=["GET"])
def get_user_preferences():
    """Get user preferences for video quality and sources"""
    try:
        user_id = request.args.get("user_id", type=int)
        preferences = imvdb_service.get_user_preferences(user_id)

        return jsonify({"success": True, "preferences": preferences})

    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/discovery/trending-quality", methods=["GET"])
def discover_trending_with_quality():
    """Discover trending videos with quality filtering"""
    try:
        limit = int(request.args.get("limit", 20))
        user_id = request.args.get("user_id", type=int)

        result = imvdb_discovery_service.discover_trending_videos(limit, user_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error discovering trending videos with quality: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/discovery/quality-patterns", methods=["GET"])
def get_quality_discovery_patterns():
    """Get quality patterns in discovery history"""
    try:
        patterns = imvdb_discovery_service.get_quality_discovery_patterns()

        return jsonify({"success": True, "patterns": patterns})

    except Exception as e:
        logger.error(f"Error getting quality discovery patterns: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Analytics endpoints


@imvdb_bp.route("/analytics/discovery-performance", methods=["GET"])
def analyze_discovery_performance():
    """Analyze discovery performance over time"""
    try:
        days = int(request.args.get("days", 30))
        analysis = imvdb_analytics_service.analyze_discovery_performance(days)

        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        logger.error(f"Error analyzing discovery performance: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@imvdb_bp.route("/analytics/comprehensive-report", methods=["GET"])
def generate_comprehensive_report():
    """Generate comprehensive discovery analysis report"""
    try:
        days = int(request.args.get("days", 30))
        report = imvdb_analytics_service.generate_comprehensive_discovery_report(days)

        return jsonify({"success": True, "report": report})

    except Exception as e:
        logger.error(f"Error generating comprehensive report: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
