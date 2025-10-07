"""
Frontend routes for serving web interface
"""

from pathlib import Path

from flask import Blueprint, render_template, request, send_from_directory

from src.middleware.simple_auth_middleware import auth_required
from src.utils.logger import get_logger

frontend_bp = Blueprint("frontend", __name__)
logger = get_logger("mvidarr.api.frontend")


@frontend_bp.route("/")
@auth_required
def index():
    """Main dashboard page"""
    return render_template("index.html")


@frontend_bp.route("/artists")
@auth_required
def artists():
    """Artists management page"""
    return render_template("artists.html")


@frontend_bp.route("/artist/<int:artist_id>")
@auth_required
def artist_detail(artist_id):
    """Artist detail page"""
    return render_template("artist_detail.html")


@frontend_bp.route("/videos")
@auth_required
def videos():
    """Videos management page"""
    return render_template("videos.html")


@frontend_bp.route("/video/<int:video_id>")
@auth_required
def video_detail(video_id):
    """Video detail page"""
    return render_template("video_detail.html")


@frontend_bp.route("/settings")
@auth_required
def settings():
    """Settings page"""
    return render_template("settings.html")


@frontend_bp.route("/jobs")
@auth_required
def jobs():
    """Background jobs management page"""
    return render_template("jobs.html")


@frontend_bp.route("/enrichment")
@auth_required
def enrichment():
    """Metadata enrichment dashboard page"""
    return render_template("enrichment.html")


@frontend_bp.route("/themes")
@auth_required
def themes():
    """Theme customizer page"""
    return render_template("themes.html")


@frontend_bp.route("/discover")
@auth_required
def discover():
    """Discover page for searching IMVDb and YouTube"""
    query = request.args.get("q", "")
    return render_template("discover.html", query=query)


@frontend_bp.route("/playlists")
@auth_required
def playlists():
    """Playlists management page"""
    return render_template("playlists.html")


@frontend_bp.route("/playlist/<int:playlist_id>")
@auth_required
def playlist_detail(playlist_id):
    """Playlist detail page"""
    return render_template("playlist_detail.html")


@frontend_bp.route("/mvtv")
@auth_required
def mvtv():
    """MvTV continuous video player page"""
    return render_template("mvtv.html")


@frontend_bp.route("/youtube-playlists")
@auth_required
def youtube_playlists():
    """YouTube Playlists management page"""
    return render_template("youtube_playlists.html")


@frontend_bp.route("/spotify")
@auth_required
def spotify():
    """Spotify integration page"""
    return render_template("spotify.html")


@frontend_bp.route("/lastfm")
@auth_required
def lastfm():
    """Last.fm integration page"""
    return render_template("lastfm.html")


@frontend_bp.route("/plex")
@auth_required
def plex():
    """Plex integration page"""
    return render_template("plex.html")


@frontend_bp.route("/lidarr")
@auth_required
def lidarr():
    """Lidarr integration page"""
    return render_template("lidarr.html")


@frontend_bp.route("/blacklist")
@auth_required
def blacklist():
    """Video blacklist management page"""
    return render_template("blacklist.html")


@frontend_bp.route("/loading-demo")
@auth_required
def loading_demo():
    """Loading states and feedback system demo page"""
    return render_template("loading-demo.html")


@frontend_bp.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files"""
    static_dir = Path(__file__).parent.parent.parent / "frontend" / "static"
    return send_from_directory(static_dir, filename)


@frontend_bp.route("/css/<path:filename>")
def css_files(filename):
    """Serve CSS files"""
    css_dir = Path(__file__).parent.parent.parent / "frontend" / "CSS"
    return send_from_directory(css_dir, filename)


@frontend_bp.route("/js/<path:filename>")
def js_files(filename):
    """Serve JavaScript files"""
    js_dir = Path(__file__).parent.parent.parent / "frontend" / "static" / "js"
    return send_from_directory(js_dir, filename)


@frontend_bp.route("/thumbnails/<path:filename>")
def thumbnails(filename):
    """Serve thumbnail files"""
    thumbnails_dir = Path(__file__).parent.parent.parent / "data" / "thumbnails"
    return send_from_directory(thumbnails_dir, filename)
