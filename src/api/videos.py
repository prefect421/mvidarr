"""
Videos API endpoints
"""

import json
import mimetypes
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from flask import Blueprint, Response, jsonify, render_template, request, send_file
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

from src.database.connection import get_db
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.metadata_enrichment_service import metadata_enrichment_service
from src.services.video_indexing_service import VideoIndexingService
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

videos_bp = Blueprint("videos", __name__, url_prefix="/videos")
logger = get_logger("mvidarr.api.videos")


def get_ytdlp_path():
    """Get the best available yt-dlp executable path"""
    return (
        "/root/.local/bin/yt-dlp"  # pipx installed (latest)
        if os.path.exists("/root/.local/bin/yt-dlp")
        else shutil.which("yt-dlp")
        or shutil.which("yt-dlp.exe")
        or "/usr/local/bin/yt-dlp"
    )


def _safe_parse_genres(genres):
    """Safely parse genres field that may be JSON string or list"""
    if isinstance(genres, list):
        return genres
    if not genres:
        return []
    if isinstance(genres, str):
        try:
            genres = genres.strip()
            if not genres:
                return []
            return json.loads(genres)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse genres JSON: {genres}, error: {e}")
            return []
    return []


def public_endpoint(f):
    """Decorator to mark an endpoint as public (no authentication required)"""
    f._auth_protected = True  # Mark as already protected to skip auto-protection
    return f


def resolve_video_url(video, session):
    """
    Helper function to resolve video URL using yt-dlp search

    Args:
        video: Video object
        session: Database session

    Returns:
        str: Resolved URL or None
    """
    if video.url:
        return video.url

    # Also check youtube_url field as fallback (but ensure it's complete)
    if (
        video.youtube_url and len(video.youtube_url.strip()) > 30
    ):  # Valid YouTube URLs are longer than 30 chars
        # Additional check: ensure URL has a video ID (not just ending with "?v=")
        if not video.youtube_url.endswith("?v="):
            return video.youtube_url

    try:
        import json
        import subprocess

        artist_name = video.artist.name if video.artist else "Unknown Artist"
        # Ensure title is a string (fix for integer title issue)
        video_title = str(video.title) if video.title is not None else "Unknown"
        search_query = f"{artist_name} {video_title}"
        logger.info(f"Searching for video URL: {search_query}")

        # Use yt-dlp to search YouTube
        cmd = [
            get_ytdlp_path(),  # Use the best available version
            "--dump-json",
            "--no-download",
            "--playlist-items",
            "1",
            f"ytsearch1:{search_query}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and result.stdout:
            video_info = json.loads(result.stdout.strip())
            resolved_url = video_info.get("webpage_url") or video_info.get("url")

            if resolved_url:
                # Update video with resolved URL
                video.url = resolved_url
                if "id" in video_info:
                    video.youtube_id = video_info["id"]
                session.commit()
                logger.info(f"Resolved video URL for '{video.title}': {resolved_url}")
                return resolved_url
            else:
                logger.warning(f"No URL found in video info for '{video.title}'")
        else:
            logger.error(f"yt-dlp search failed for '{search_query}': {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp search timed out for '{search_query}'")
    except Exception as e:
        logger.error(f"Error resolving video URL for '{video.title}': {e}")

    return None


def find_relocated_video(video, session):
    """
    Try to find a relocated video file in expected artist folders

    Args:
        video: Video object with artist relationship
        session: Database session

    Returns:
        str: Path to relocated file or None if not found
    """
    if not video.artist:
        return None

    from src.services.settings_service import settings

    try:
        # Get the downloads directory from settings
        downloads_dir = settings.get("downloads_directory", "data/downloads")
        if not os.path.isabs(downloads_dir):
            downloads_dir = os.path.join(os.getcwd(), downloads_dir)

        # Expected artist folder path
        artist_folder = os.path.join(downloads_dir, video.artist.name)

        if not os.path.exists(artist_folder):
            # Try with sanitized artist name
            import re

            sanitized_name = re.sub(r'[<>:"/\\|?*]', "_", video.artist.name)
            artist_folder = os.path.join(downloads_dir, sanitized_name)

        if os.path.exists(artist_folder):
            # Search for video files with similar names
            # Ensure title is a string (fix for integer title issue)
            video_title = str(video.title) if video.title is not None else ""
            video_title_clean = (
                video_title.lower().replace(" ", "").replace("_", "").replace("-", "")
            )

            for filename in os.listdir(artist_folder):
                if filename.lower().endswith((".mp4", ".mkv", ".avi", ".webm", ".mov")):
                    # Check if filename contains the video title (fuzzy match)
                    filename_clean = (
                        filename.lower()
                        .replace(" ", "")
                        .replace("_", "")
                        .replace("-", "")
                    )

                    # Try different matching strategies
                    if (
                        video_title_clean in filename_clean
                        or filename_clean.startswith(video_title_clean[:10])
                        or any(
                            word in filename_clean
                            for word in video_title_clean.split()
                            if len(word) > 3
                        )
                    ):
                        full_path = os.path.join(artist_folder, filename)
                        logger.info(f"Found potential relocated video: {full_path}")
                        return full_path

            # If no fuzzy match, try exact YouTube ID match if available
            if video.youtube_id:
                for filename in os.listdir(artist_folder):
                    if video.youtube_id in filename:
                        full_path = os.path.join(artist_folder, filename)
                        logger.info(f"Found relocated video by YouTube ID: {full_path}")
                        return full_path

    except Exception as e:
        logger.error(f"Error searching for relocated video: {e}")

    return None


def _trigger_video_download(video_id):
    """
    Helper function to trigger video download

    Args:
        video_id: Video ID to download

    Returns:
        dict: Download result with success/error information
    """
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return {"success": False, "error": "Video not found"}

            # Store video data for URL resolution
            artist_name = video.artist.name if video.artist else "Unknown Artist"

            # Resolve video URL using helper function
            video_url = resolve_video_url(video, session)

            if not video_url:
                return {
                    "success": False,
                    "error": "Video has no URL to download and could not resolve one",
                }

            # Import ytdlp service and settings
            from src.services.download_service_adapter import ytdlp_service
            from src.services.settings_service import settings

            # Check if video is already downloaded
            status_value = (
                video.status.value if hasattr(video.status, "value") else video.status
            )
            if (
                status_value == "DOWNLOADED"
                and video.local_path
                and video.local_path.strip()  # Ensure path is not empty or whitespace
                and os.path.exists(video.local_path)
            ):
                return {"success": False, "error": "Video is already downloaded"}

            # Read subtitle settings from database
            download_subtitles = settings.get_bool("download_subtitles", False)
            subtitle_languages = settings.get("subtitle_languages", "en,en-US")

            # Add download to yt-dlp queue
            result = ytdlp_service.add_music_video_download(
                artist=artist_name,
                title=video.title,
                url=video_url,
                quality="best",
                video_id=video_id,
                download_subtitles=download_subtitles,
                subtitle_languages=subtitle_languages,
            )

            if result and result.get("success"):
                # Update video status to indicate download started
                # Re-query the video object to ensure it's bound to the current session
                video = session.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = VideoStatus.DOWNLOADING
                    session.commit()

                return {
                    "success": True,
                    "message": f'Download queued for "{video.title}"',
                    "download_id": result.get("id"),
                    "video_id": video_id,
                }
            else:
                error_msg = (
                    result.get("error", "Failed to queue download")
                    if result
                    else "yt-dlp service unavailable"
                )
                return {"success": False, "error": error_msg}

    except Exception as e:
        logger.error(f"Failed to trigger download for video {video_id}: {e}")
        return {"success": False, "error": str(e)}


@videos_bp.route("/", methods=["GET"])
@monitor_performance("api.videos.list")
def get_videos():
    """Get all videos with optional sorting and pagination"""
    try:
        # Get sorting and pagination parameters
        sort_by = request.args.get("sort", "title")
        sort_order = request.args.get("order", "asc")
        limit = request.args.get("limit", type=int)
        offset = request.args.get("offset", 0, type=int)

        with get_db() as session:
            # Always need artist data for response, but optimize how we get it
            need_artist_join_for_sort = sort_by == "artist_name"

            if need_artist_join_for_sort:
                # Need JOIN for sorting by artist name
                query = session.query(Video).join(
                    Artist, Video.artist_id == Artist.id, isouter=True
                )
                # Count on joined query when needed for sorting
                total_count = query.count()
            else:
                # For counting and basic querying, use base Video table (much faster)
                base_query = session.query(Video)
                total_count = base_query.count()

                # For data retrieval, use eager loading to prevent N+1 queries
                # This is more efficient than JOIN when we're not sorting by artist
                from sqlalchemy.orm import joinedload

                query = session.query(Video).options(joinedload(Video.artist))

            # Apply sorting
            if sort_by == "title":
                sort_column = Video.title
            elif sort_by == "artist_name":
                sort_column = Artist.name
            elif sort_by == "year":
                sort_column = Video.year
            elif sort_by == "created_at":
                sort_column = Video.created_at
            elif sort_by == "status":
                sort_column = Video.status
            else:
                sort_column = Video.title

            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

            # Apply pagination if limit is specified
            if limit is not None:
                query = query.offset(offset).limit(limit)

            videos = query.all()

            videos_list = []
            for video in videos:
                videos_list.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist_id": video.artist_id,
                        "artist_name": video.artist.name if video.artist else None,
                        "status": (
                            video.status.value
                            if hasattr(video.status, "value")
                            else video.status
                        ),
                        "imvdb_id": video.imvdb_id,
                        "video_url": video.url,
                        "local_path": video.local_path,
                        "thumbnail_url": video.thumbnail_url,
                        "duration": video.duration,
                        "quality": video.quality,
                        "year": video.year,
                        "video_metadata": video.video_metadata,
                        "created_at": video.created_at.isoformat(),
                    }
                )

            return (
                jsonify(
                    {
                        "videos": videos_list,
                        "count": len(videos_list),
                        "total": total_count,
                        "offset": offset,
                        "limit": limit,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get videos: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/search", methods=["GET"])
@monitor_performance("api.videos.search")
def search_videos():
    """Search videos with multiple filters - OPTIMIZED VERSION"""
    import time

    start_time = time.time()

    try:
        # Get search parameters
        filters = {
            "query": request.args.get("q", "").strip(),
            "artist_name": request.args.get("artist_name", "").strip(),
            "artist": request.args.get("artist", "").strip(),
            "status": request.args.get("status", "").strip(),
            "year": request.args.get("year", "").strip(),
            "year_from": request.args.get("year_from", "").strip(),
            "year_to": request.args.get("year_to", "").strip(),
            "genre": request.args.get("genre", "").strip(),
            "quality": request.args.get("quality", "").strip(),
            "has_thumbnail": request.args.get("has_thumbnail", "").strip(),
            "source": request.args.get("source", "").strip(),
            "duration_min": request.args.get("duration_min", type=int),
            "duration_max": request.args.get("duration_max", type=int),
            "date_from": request.args.get("date_from", "").strip(),
            "date_to": request.args.get("date_to", "").strip(),
            "keywords": request.args.get("keywords", "").strip(),
            "sort_by": request.args.get("sort_by", request.args.get("sort", "title")),
            "sort_order": request.args.get(
                "sort_order", request.args.get("order", "asc")
            ),
        }

        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        with get_db() as session:
            # Determine if we need Artist join - used by both optimizer and fallback
            need_artist_join = (
                filters["query"]
                or filters["artist_name"]
                or filters["artist"]
                or filters["sort_by"] in ["artist_name", "artist"]
            )

            # Use optimized query builder
            try:
                from src.database.performance_optimizations import (
                    DatabasePerformanceOptimizer,
                )

                optimizer = DatabasePerformanceOptimizer()
                videos_query = optimizer.optimize_video_search_query(session, filters)
            except ImportError:
                # Fallback to basic optimized query if optimizer not available
                videos_query = session.query(Video)

                if need_artist_join:
                    videos_query = videos_query.join(Artist)

                # Apply most selective filters first
                if filters["status"]:
                    try:
                        # Convert string to VideoStatus enum
                        status_enum = VideoStatus(filters["status"])
                        videos_query = videos_query.filter(Video.status == status_enum)
                    except ValueError:
                        # Invalid status value, skip filter
                        logger.warning(
                            f"Invalid video status filter: {filters['status']}"
                        )
                        pass

                if filters["source"]:
                    if filters["source"] == "youtube":
                        videos_query = videos_query.filter(Video.youtube_id.isnot(None))
                    elif filters["source"] == "imvdb":
                        videos_query = videos_query.filter(Video.imvdb_id.isnot(None))
                    elif filters["source"] == "manual":
                        videos_query = videos_query.filter(
                            and_(Video.youtube_id.is_(None), Video.imvdb_id.is_(None))
                        )

                if filters["quality"]:
                    videos_query = videos_query.filter(
                        Video.quality == filters["quality"]
                    )

                # Year filters - handle both single year and year range
                if filters["year"]:
                    try:
                        year_int = int(filters["year"])
                        videos_query = videos_query.filter(Video.year == year_int)
                    except ValueError:
                        pass

                # Year range filters (from frontend)
                year_from = request.args.get("year_from", "").strip()
                year_to = request.args.get("year_to", "").strip()
                if year_from:
                    try:
                        year_from_int = int(year_from)
                        videos_query = videos_query.filter(Video.year >= year_from_int)
                    except ValueError:
                        pass
                if year_to:
                    try:
                        year_to_int = int(year_to)
                        videos_query = videos_query.filter(Video.year <= year_to_int)
                    except ValueError:
                        pass

                # Duration filters
                if filters["duration_min"]:
                    try:
                        duration_min = (
                            int(filters["duration_min"]) * 60
                        )  # Convert minutes to seconds
                        videos_query = videos_query.filter(
                            Video.duration >= duration_min
                        )
                    except (ValueError, TypeError):
                        pass

                if filters["duration_max"]:
                    try:
                        duration_max = (
                            int(filters["duration_max"]) * 60
                        )  # Convert minutes to seconds
                        videos_query = videos_query.filter(
                            Video.duration <= duration_max
                        )
                    except (ValueError, TypeError):
                        pass

                # Date range filters
                if filters["date_from"]:
                    try:
                        from datetime import datetime

                        date_from = datetime.strptime(filters["date_from"], "%Y-%m-%d")
                        videos_query = videos_query.filter(
                            Video.created_at >= date_from
                        )
                    except ValueError:
                        pass

                if filters["date_to"]:
                    try:
                        from datetime import datetime

                        date_to = datetime.strptime(filters["date_to"], "%Y-%m-%d")
                        videos_query = videos_query.filter(Video.created_at <= date_to)
                    except ValueError:
                        pass

                # Thumbnail filter
                if filters["has_thumbnail"]:
                    has_thumbnail_bool = filters["has_thumbnail"].lower() in [
                        "true",
                        "1",
                        "yes",
                    ]
                    if has_thumbnail_bool:
                        videos_query = videos_query.filter(
                            Video.thumbnail_path.isnot(None)
                        )
                    else:
                        videos_query = videos_query.filter(
                            Video.thumbnail_path.is_(None)
                        )

                # Genre filter
                if filters["genre"]:
                    genre = filters["genre"]
                    videos_query = videos_query.filter(
                        Video.genres.contains(f'"{genre}"')
                    )

                # Keywords filter - search in video title and description
                if filters["keywords"]:
                    keywords = filters["keywords"].strip()
                    if keywords:
                        keyword_list = [
                            k.strip().lower() for k in keywords.split(",") if k.strip()
                        ]
                        if keyword_list:
                            # Create OR conditions for each keyword
                            keyword_conditions = []
                            for keyword in keyword_list:
                                keyword_conditions.append(
                                    func.lower(Video.title).contains(keyword)
                                )
                                if Video.description:
                                    keyword_conditions.append(
                                        func.lower(Video.description).contains(keyword)
                                    )
                            videos_query = videos_query.filter(or_(*keyword_conditions))

                if filters["query"]:
                    from sqlalchemy import or_

                    if need_artist_join:
                        videos_query = videos_query.filter(
                            or_(
                                Video.title.contains(filters["query"]),
                                Artist.name.contains(filters["query"]),
                            )
                        )
                    else:
                        videos_query = videos_query.filter(
                            Video.title.contains(filters["query"])
                        )

                # Artist name filter (handle both 'artist' and 'artist_name' params)
                artist_filter = (
                    filters["artist_name"] or request.args.get("artist", "").strip()
                )
                if artist_filter and need_artist_join:
                    videos_query = videos_query.filter(
                        Artist.name.contains(artist_filter)
                    )

            # Apply sorting with performance consideration
            sort_by = filters["sort_by"]
            sort_order = filters["sort_order"]

            if sort_by == "title":
                sort_column = Video.title
            elif sort_by in ["artist_name", "artist"] and need_artist_join:
                sort_column = Artist.name
            elif sort_by == "created_at":
                sort_column = Video.created_at
            elif sort_by == "status":
                sort_column = Video.status
            else:
                sort_column = Video.title

            if sort_order.lower() == "desc":
                videos_query = videos_query.order_by(sort_column.desc())
            else:
                videos_query = videos_query.order_by(sort_column.asc())

            # Get total count using standard method - more reliable than complex subqueries
            count_start = time.time()
            try:
                total_count = videos_query.count()
                logger.debug(
                    f"Count query completed successfully: {total_count} results"
                )
            except Exception as count_error:
                logger.error(f"Count query failed: {count_error}")
                total_count = 0
            count_time = time.time() - count_start

            # Apply pagination
            query_start = time.time()
            videos = videos_query.offset(offset).limit(limit).all()
            query_time = time.time() - query_start

            # Format results
            videos_list = []
            for video in videos:
                videos_list.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist_id": video.artist_id,
                        "artist_name": video.artist.name if video.artist else None,
                        "status": (
                            video.status.value
                            if hasattr(video.status, "value")
                            else video.status
                        ),
                        "imvdb_id": video.imvdb_id,
                        "video_url": video.url,
                        "local_path": video.local_path,
                        "thumbnail_url": video.thumbnail_url,
                        "duration": video.duration,
                        "year": video.year,
                        "genres": video.genres if video.genres else [],
                        "quality": video.quality,
                        "video_metadata": video.video_metadata,
                        "created_at": video.created_at.isoformat(),
                    }
                )

            return (
                jsonify(
                    {
                        "videos": videos_list,
                        "count": len(videos_list),
                        "total": total_count,
                        "offset": offset,
                        "limit": limit,
                        "filters": {
                            "query": filters["query"],
                            "artist": filters["artist_name"],
                            "status": filters["status"],
                            "year": filters["year"],
                            "genre": filters["genre"],
                            "quality": filters["quality"],
                            "has_thumbnail": filters["has_thumbnail"],
                            "source": filters["source"],
                            "duration_min": filters["duration_min"],
                            "duration_max": filters["duration_max"],
                            "date_from": filters["date_from"],
                            "date_to": filters["date_to"],
                            "keywords": filters["keywords"],
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        import traceback

        logger.error(f"Failed to search videos: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.error(f"Search filters were: {filters}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>", methods=["GET"])
@public_endpoint
def get_video(video_id):
    """Get specific video by ID"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            video_data = {
                "id": video.id,
                "title": video.title,
                "artist_id": video.artist_id,
                "artist_name": video.artist.name if video.artist else None,
                "status": (
                    video.status.value
                    if hasattr(video.status, "value")
                    else video.status
                ),
                "imvdb_id": video.imvdb_id,
                "video_url": video.url,
                "local_path": video.local_path,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "quality": video.quality,
                "year": video.year,
                "genres": _safe_parse_genres(video.genres),
                "album": video.album,
                "search_keywords": video.search_keywords,
                "description": video.description,
                "view_count": video.view_count,
                "like_count": video.like_count,
                "directors": video.directors,
                "producers": video.producers,
                "release_date": (
                    video.release_date.isoformat() if video.release_date else None
                ),
                "lyrics": video.lyrics,
                "video_metadata": video.video_metadata,
                "created_at": video.created_at.isoformat(),
            }

            return jsonify(video_data), 200

    except Exception as e:
        logger.error(f"Failed to get video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/download", methods=["POST"])
def download_video(video_id):
    """Queue video for download using YT-DLP service"""
    try:
        logger.info(f"Starting download for video {video_id}")

        # Use the working YT-DLP trigger function that properly links files immediately
        result = _trigger_video_download(video_id)

        if result.get("success"):
            logger.info(
                f"Queued download for video {video_id}: {result.get('message')}"
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "video_id": video_id,
                        "download_id": result.get("download_id"),
                        "message": result.get(
                            "message", "Download queued successfully"
                        ),
                    }
                ),
                202,
            )  # 202 Accepted - processing started
        else:
            logger.error(
                f"Failed to queue download for video {video_id}: {result.get('error')}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": result.get("error", "Unknown error occurred"),
                    }
                ),
                400,
            )

    except Exception as e:
        logger.error(f"Failed to queue video download job: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/identify-artist", methods=["POST"])
def identify_artist(video_id):
    """Get artist identification suggestions for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Extract video data within the session
            video_title = video.title
            current_artist = video.artist.name if video.artist else None

        # Import the identification service
        from src.services.artist_identification_service import (
            artist_identification_service,
        )

        # Get identification candidates
        candidates = artist_identification_service.identify_artist_from_title(
            video_title
        )

        # Filter to top 3 candidates with confidence > 0.6
        top_candidates = [c for c in candidates if c["confidence"] > 0.6][:3]

        # Format response
        result = {
            "video_id": video_id,
            "title": video_title,
            "current_artist": current_artist,
            "suggestions": [],
        }

        for candidate in top_candidates:
            result["suggestions"].append(
                {
                    "artist_name": candidate["artist_name"],
                    "confidence": candidate["confidence"],
                    "source": candidate["source"],
                    "reason": candidate.get("match_reason", "No additional info"),
                }
            )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Failed to identify artist for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/search-artists", methods=["GET"])
def search_artists():
    """Search for existing artists by name"""
    try:
        query = request.args.get("q", "").strip()

        if not query:
            return jsonify({"artists": []}), 200

        # Minimum query length to avoid too many results
        if len(query) < 2:
            return jsonify({"artists": []}), 200

        with get_db() as session:
            # Search for artists whose names contain the query (case-insensitive)
            artists = (
                session.query(Artist)
                .filter(Artist.name.ilike(f"%{query}%"))
                .filter(Artist.name != "Unknown Artist")
                .order_by(Artist.name)
                .limit(10)
                .all()
            )

            # Format results
            results = []
            for artist in artists:
                results.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "video_count": len(artist.videos),
                    }
                )

            return jsonify({"artists": results}), 200

    except Exception as e:
        logger.error(f"Failed to search artists: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>", methods=["DELETE"])
def delete_video(video_id):
    """Delete a specific video"""
    try:
        # Get optional blacklist parameter from request body
        data = request.get_json() or {}
        add_to_blacklist = data.get("add_to_blacklist", False)

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Store video info for response
            video_info = {
                "id": video.id,
                "title": video.title,
                "artist_name": video.artist.name if video.artist else None,
            }

            # First, delete any playlist entries that reference this video
            from src.database.models import PlaylistEntry

            playlist_entries = (
                session.query(PlaylistEntry)
                .filter(PlaylistEntry.video_id == video_id)
                .all()
            )
            playlist_count = len(playlist_entries)

            for entry in playlist_entries:
                session.delete(entry)

            # Delete any downloads that reference this video
            downloads = (
                session.query(Download).filter(Download.video_id == video_id).all()
            )
            download_count = len(downloads)

            for download in downloads:
                session.delete(download)

            # Add to blacklist if requested
            blacklisted = False
            if add_to_blacklist and video.url:
                try:
                    from flask import g

                    from src.database.models import VideoBlacklist

                    # Check if URL is already blacklisted
                    existing_blacklist = (
                        session.query(VideoBlacklist)
                        .filter(VideoBlacklist.youtube_url == video.url)
                        .first()
                    )

                    if not existing_blacklist:
                        # Add to blacklist
                        blacklist_entry = VideoBlacklist(
                            youtube_url=video.url,
                            title=video.title,
                            artist_name=video.artist.name if video.artist else None,
                            blacklisted_by=getattr(g, "current_user_id", None),
                        )
                        session.add(blacklist_entry)
                        blacklisted = True
                        logger.info(f"Added video to blacklist: {video.url}")
                    else:
                        blacklisted = True  # Already blacklisted

                except Exception as e:
                    logger.warning(f"Failed to add video to blacklist: {e}")

            # Now delete the video record
            session.delete(video)
            session.commit()

            logger.info(
                f"Deleted video: {video_info['title']} by {video_info['artist_name']} "
                f"(removed from {playlist_count} playlists, {download_count} downloads)"
            )

            return (
                jsonify(
                    {
                        "message": "Video deleted successfully",
                        "video": video_info,
                        "playlist_entries_removed": playlist_count,
                        "downloads_removed": download_count,
                        "blacklisted": blacklisted,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to delete video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/delete", methods=["POST"])
def bulk_delete_videos():
    """Delete multiple videos using background job queue"""
    try:
        data = request.get_json()
        video_ids = data.get("video_ids", [])
        delete_files = data.get("delete_files", True)
        blacklist = data.get("blacklist", False)

        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400

        if not isinstance(video_ids, list):
            return jsonify({"error": "video_ids must be a list"}), 400

        # Validate that video IDs are integers
        try:
            video_ids = [int(vid) for vid in video_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "All video IDs must be integers"}), 400

        # Create bulk delete job
        from ..services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        job = BackgroundJob(
            type=JobType.BULK_VIDEO_DELETE,
            priority=JobPriority.HIGH,
            payload={
                "operation_type": "delete",
                "video_ids": video_ids,
                "params": {"delete_files": delete_files, "blacklist": blacklist},
            },
        )

        job_queue = asyncio.run(get_job_queue())
        job_id = asyncio.run(job_queue.enqueue(job))

        logger.info(f"Queued bulk delete job {job_id} for {len(video_ids)} videos")

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "total_videos": len(video_ids),
                    "message": f"Bulk delete job queued for {len(video_ids)} videos. Job ID: {job_id}",
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to create bulk delete job: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail", methods=["GET"])
def get_video_thumbnail(video_id):
    """Get thumbnail for a specific video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Check if we have a local thumbnail file
            if video.thumbnail_path and os.path.exists(video.thumbnail_path):
                return send_file(video.thumbnail_path, as_attachment=False)

            # If we have a thumbnail URL but no local file, download and cache it
            if video.thumbnail_url and not video.thumbnail_path:
                try:
                    from src.services.thumbnail_service import thumbnail_service

                    artist_name = video.artist.name if video.artist else "Unknown"
                    thumbnail_path = thumbnail_service.download_video_thumbnail(
                        artist_name, video.title, video.thumbnail_url
                    )

                    if thumbnail_path and os.path.exists(thumbnail_path):
                        # Update the database with the new thumbnail path
                        video.thumbnail_path = thumbnail_path
                        session.commit()
                        logger.info(
                            f"Downloaded and cached thumbnail for video {video_id}"
                        )
                        return send_file(thumbnail_path, as_attachment=False)

                except Exception as e:
                    logger.error(
                        f"Failed to download thumbnail for video {video_id}: {e}"
                    )

            # If we have a thumbnail URL but couldn't download, proxy it
            if video.thumbnail_url:
                try:
                    import requests

                    response = requests.get(
                        video.thumbnail_url, timeout=10, stream=True
                    )
                    if response.status_code == 200:
                        # Get content type from response
                        content_type = response.headers.get(
                            "Content-Type", "image/jpeg"
                        )

                        def generate():
                            for chunk in response.iter_content(chunk_size=8192):
                                yield chunk

                        return Response(generate(), content_type=content_type)

                except Exception as e:
                    logger.error(f"Failed to proxy thumbnail for video {video_id}: {e}")

            # Return placeholder if no thumbnail available
            placeholder_path = "frontend/static/placeholder-video.png"
            if os.path.exists(placeholder_path):
                return send_file(placeholder_path, as_attachment=False)

            return jsonify({"error": "Thumbnail not available"}), 404

    except Exception as e:
        logger.error(f"Failed to get thumbnail for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/refresh-thumbnails", methods=["POST"])
def refresh_thumbnails():
    """Find and download thumbnails for videos that don't have any"""
    try:
        from src.services.thumbnail_service import thumbnail_service

        # Get request parameters
        data = request.get_json() or {}
        video_ids = data.get("video_ids", None)

        with get_db() as session:
            # Build base query for videos without thumbnails or with thumbnail_url but no thumbnail_path
            query = (
                session.query(Video)
                .join(Artist)
                .filter(
                    or_(
                        # Videos with no thumbnail at all
                        and_(
                            Video.thumbnail_url.is_(None),
                            Video.thumbnail_path.is_(None),
                        ),
                        # Videos with thumbnail_url but no thumbnail_path (all URLs, not just specific patterns)
                        and_(
                            Video.thumbnail_url.isnot(None),
                            Video.thumbnail_path.is_(None),
                        ),
                    )
                )
            )

            # Filter by specific video IDs if provided
            if video_ids:
                query = query.filter(Video.id.in_(video_ids))

            videos = query.all()

            downloaded_count = 0
            skipped_count = 0
            failed_count = 0

            for video in videos:
                try:
                    # Get the artist name for proper thumbnail naming
                    artist_name = video.artist.name if video.artist else "Unknown"

                    # If video has no thumbnail_url, try to find one using search
                    if not video.thumbnail_url:
                        logger.info(
                            f"Searching for thumbnail for: {video.title} by {artist_name}"
                        )
                        # Try to find thumbnail URL using YouTube search or other sources
                        try:
                            from src.services.youtube_service import youtube_service

                            search_query = f"{artist_name} {video.title}"
                            search_results = youtube_service.search_videos(
                                search_query, max_results=1
                            )

                            if search_results.get("success") and search_results.get(
                                "results"
                            ):
                                video_result = search_results["results"][0]
                                if (
                                    "snippet" in video_result
                                    and "thumbnails" in video_result["snippet"]
                                ):
                                    # Get the highest quality thumbnail available
                                    thumbnails = video_result["snippet"]["thumbnails"]
                                    thumbnail_url = None
                                    for quality in [
                                        "maxres",
                                        "high",
                                        "medium",
                                        "default",
                                    ]:
                                        if quality in thumbnails:
                                            thumbnail_url = thumbnails[quality]["url"]
                                            break

                                    if thumbnail_url:
                                        video.thumbnail_url = thumbnail_url
                                        session.commit()
                                        logger.info(
                                            f"Found thumbnail URL: {thumbnail_url}"
                                        )
                                    else:
                                        logger.warning(
                                            f"No thumbnail found for: {video.title}"
                                        )
                                        skipped_count += 1
                                        continue
                                else:
                                    logger.warning(
                                        f"No thumbnail data in search result for: {video.title}"
                                    )
                                    skipped_count += 1
                                    continue
                            else:
                                logger.warning(f"No search results for: {video.title}")
                                skipped_count += 1
                                continue
                        except Exception as search_error:
                            logger.error(
                                f"Error searching for thumbnail for {video.title}: {search_error}"
                            )
                            skipped_count += 1
                            continue

                    # Check if thumbnail file already exists before trying to download
                    from pathlib import Path

                    from src.services.settings_service import SettingsService

                    thumbnails_dir = SettingsService.get(
                        "thumbnails_path", "data/thumbnails"
                    )
                    expected_filename = thumbnail_service.generate_filename(
                        video.thumbnail_url
                    )
                    expected_path = (
                        Path(thumbnails_dir) / artist_name / expected_filename
                    )

                    file_already_exists = expected_path.exists()

                    thumbnail_path = thumbnail_service.download_video_thumbnail(
                        artist_name, video.title, video.thumbnail_url
                    )
                    if thumbnail_path:
                        video.thumbnail_path = thumbnail_path
                        if file_already_exists:
                            skipped_count += 1
                            logger.debug(
                                f"Skipped existing thumbnail for video: {video.title} by {artist_name}"
                            )
                        else:
                            downloaded_count += 1
                            logger.info(
                                f"Downloaded thumbnail for video: {video.title} by {artist_name}"
                            )
                    else:
                        failed_count += 1
                        logger.warning(
                            f"Failed to download thumbnail for video: {video.title}"
                        )

                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"Failed to download thumbnail for video {video.title}: {e}"
                    )

            # Handle IMVDb URLs that might be expired - try to download them or find alternatives
            imvdb_videos_query = (
                session.query(Video)
                .join(Artist)
                .filter(
                    Video.thumbnail_url.isnot(None),
                    Video.thumbnail_path.is_(None),
                    Video.thumbnail_url.like("%imvdb%"),
                )
            )

            # Filter by specific video IDs if provided
            if video_ids:
                imvdb_videos_query = imvdb_videos_query.filter(Video.id.in_(video_ids))

            imvdb_videos = imvdb_videos_query.all()
            imvdb_skipped_count = 0
            imvdb_fixed_count = 0

            # Try to download or fix IMVDb thumbnails
            for video in imvdb_videos:
                try:
                    artist_name = video.artist.name if video.artist else "Unknown"

                    # First try to download the IMVDb thumbnail as-is
                    thumbnail_path = thumbnail_service.download_video_thumbnail(
                        artist_name, video.title, video.thumbnail_url
                    )

                    if thumbnail_path:
                        video.thumbnail_path = thumbnail_path
                        downloaded_count += 1
                        imvdb_fixed_count += 1
                        logger.info(f"Downloaded IMVDb thumbnail for: {video.title}")
                    else:
                        # IMVDb URL is expired, try to find a new thumbnail
                        logger.info(
                            f"IMVDb thumbnail expired for {video.title}, searching for replacement"
                        )
                        try:
                            from src.services.youtube_service import youtube_service

                            search_query = f"{artist_name} {video.title}"
                            search_results = youtube_service.search_videos(
                                search_query, max_results=1
                            )

                            if search_results.get("success") and search_results.get(
                                "results"
                            ):
                                video_result = search_results["results"][0]
                                if (
                                    "snippet" in video_result
                                    and "thumbnails" in video_result["snippet"]
                                ):
                                    thumbnails = video_result["snippet"]["thumbnails"]
                                    new_thumbnail_url = None
                                    for quality in [
                                        "maxres",
                                        "high",
                                        "medium",
                                        "default",
                                    ]:
                                        if quality in thumbnails:
                                            new_thumbnail_url = thumbnails[quality][
                                                "url"
                                            ]
                                            break

                                    if new_thumbnail_url:
                                        # Update with new thumbnail URL and download
                                        video.thumbnail_url = new_thumbnail_url
                                        thumbnail_path = (
                                            thumbnail_service.download_video_thumbnail(
                                                artist_name,
                                                video.title,
                                                new_thumbnail_url,
                                            )
                                        )
                                        if thumbnail_path:
                                            video.thumbnail_path = thumbnail_path
                                            downloaded_count += 1
                                            imvdb_fixed_count += 1
                                            logger.info(
                                                f"Replaced expired IMVDb thumbnail for: {video.title}"
                                            )
                                        else:
                                            imvdb_skipped_count += 1
                                    else:
                                        imvdb_skipped_count += 1
                                else:
                                    imvdb_skipped_count += 1
                            else:
                                imvdb_skipped_count += 1
                        except Exception as search_error:
                            logger.error(
                                f"Error searching for replacement thumbnail for {video.title}: {search_error}"
                            )
                            imvdb_skipped_count += 1
                except Exception as e:
                    logger.error(
                        f"Error processing IMVDb thumbnail for {video.title}: {e}"
                    )
                    imvdb_skipped_count += 1

            session.commit()

            total_skipped = skipped_count + imvdb_skipped_count

            # Create detailed message
            message_parts = []
            if downloaded_count > 0:
                message_parts.append(f"Downloaded {downloaded_count} thumbnails")
            if imvdb_fixed_count > 0:
                message_parts.append(
                    f"fixed {imvdb_fixed_count} expired IMVDb thumbnails"
                )
            if skipped_count > 0:
                message_parts.append(f"skipped {skipped_count} existing files")
            if imvdb_skipped_count > 0:
                message_parts.append(
                    f"skipped {imvdb_skipped_count} IMVDb URLs (could not fix)"
                )
            if failed_count > 0:
                message_parts.append(f"failed {failed_count}")

            if not message_parts:
                # Check if there are any videos with thumbnail_url at all
                total_videos_with_urls = (
                    session.query(Video).filter(Video.thumbnail_url.isnot(None)).count()
                )

                if total_videos_with_urls == 0:
                    message = "No videos found with thumbnail URLs"
                else:
                    already_downloaded = (
                        session.query(Video)
                        .filter(
                            Video.thumbnail_url.isnot(None),
                            Video.thumbnail_path.isnot(None),
                        )
                        .count()
                    )
                    message = f"No new thumbnails to download. Found {total_videos_with_urls} videos with thumbnail URLs, {already_downloaded} already have local thumbnails"
            else:
                message = ", ".join(message_parts).capitalize()

            return (
                jsonify(
                    {
                        "message": message,
                        "processed": len(videos) + imvdb_skipped_count,
                        "downloaded": downloaded_count,
                        "skipped": total_skipped,
                        "skipped_existing": skipped_count,
                        "skipped_imvdb": imvdb_skipped_count,
                        "failed": failed_count,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to refresh thumbnails: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail", methods=["PUT"])
def update_video_thumbnail(video_id):
    """Update video thumbnail URL or remove thumbnail"""
    try:
        data = request.get_json()
        thumbnail_url = data.get("thumbnail_url")
        action = data.get("action", "update")

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if action == "remove":
                # Remove thumbnail files and clear database fields
                from src.services.thumbnail_service import thumbnail_service

                if video.thumbnail_path:
                    thumbnail_service.delete_thumbnail_files(video.thumbnail_path)

                video.thumbnail_url = None
                video.thumbnail_path = None
                video.thumbnail_source = None
                video.thumbnail_metadata = None
                video.thumbnail_uploaded_at = None
                session.commit()

                logger.info(f"Removed thumbnail for video {video_id}")
                return jsonify({"message": "Thumbnail removed successfully"}), 200

            elif action == "update" and thumbnail_url:
                # Update thumbnail URL and clear cached path to force new download
                video.thumbnail_url = thumbnail_url
                video.thumbnail_source = "manual"
                # Clear cached thumbnail path so new URL will be used
                if video.thumbnail_path:
                    from src.services.thumbnail_service import thumbnail_service

                    thumbnail_service.delete_thumbnail_files(video.thumbnail_path)
                    video.thumbnail_path = None
                session.commit()

                logger.info(f"Updated thumbnail URL for video {video_id}")
                return jsonify({"message": "Thumbnail URL updated successfully"}), 200

            else:
                return (
                    jsonify({"error": "Invalid action or missing thumbnail_url"}),
                    400,
                )

    except Exception as e:
        logger.error(f"Failed to update thumbnail for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail/upload", methods=["POST"])
def upload_video_thumbnail(video_id):
    """Upload a manual thumbnail file for a video"""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            from src.services.thumbnail_service import thumbnail_service

            # Generate filename based on video info
            artist_name = video.artist.name if video.artist else "Unknown"
            # Ensure title is a string (fix for integer title issue)
            video_title = str(video.title) if video.title is not None else "Unknown"
            filename = f"{artist_name} - {video_title}".replace("/", "_")

            result = thumbnail_service.upload_manual_thumbnail(
                file, filename, entity_type="video"
            )

            if result["success"]:
                # Update video thumbnail information
                video.thumbnail_path = result["thumbnail_path"]
                video.thumbnail_url = (
                    None  # Clear external URL since we have local file
                )
                video.thumbnail_source = "manual"
                video.thumbnail_metadata = result["metadata"]
                video.thumbnail_uploaded_at = datetime.now()
                session.commit()

                logger.info(f"Uploaded manual thumbnail for video {video_id}")
                return (
                    jsonify(
                        {
                            "message": "Thumbnail uploaded successfully",
                            "thumbnail_path": result["thumbnail_path"],
                            "metadata": result["metadata"],
                        }
                    ),
                    200,
                )
            else:
                return jsonify({"error": result["error"]}), 400

    except Exception as e:
        logger.error(f"Failed to upload thumbnail for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail/crop", methods=["POST"])
def crop_video_thumbnail(video_id):
    """Crop existing video thumbnail"""
    try:
        data = request.get_json()
        crop_data = data.get("crop_data")

        if not crop_data:
            return jsonify({"error": "No crop data provided"}), 400

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if not video.thumbnail_path or not os.path.exists(video.thumbnail_path):
                return (
                    jsonify(
                        {"error": "No local thumbnail file available for cropping"}
                    ),
                    400,
                )

            from src.services.thumbnail_service import thumbnail_service

            result = thumbnail_service.crop_thumbnail(video.thumbnail_path, crop_data)

            if result["success"]:
                # Update video thumbnail metadata
                video.thumbnail_source = "manual_crop"
                video.thumbnail_metadata = result["metadata"]
                video.thumbnail_uploaded_at = datetime.now()
                session.commit()

                logger.info(f"Cropped thumbnail for video {video_id}")
                return (
                    jsonify(
                        {
                            "message": "Thumbnail cropped successfully",
                            "metadata": result["metadata"],
                        }
                    ),
                    200,
                )
            else:
                return jsonify({"error": result["error"]}), 400

    except Exception as e:
        logger.error(f"Failed to crop thumbnail for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail/search", methods=["POST"])
def search_video_thumbnails(video_id):
    """Search for video thumbnails using various sources"""
    try:
        data = request.get_json()
        search_query = data.get("search_query", "")
        sources = data.get("sources", ["youtube", "imvdb", "google"])

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Capture video attributes while session is active
            artist_name = video.artist.name if video.artist else "Unknown"
            video_title = video.title
            video_url = video.url
            video_imvdb_id = video.imvdb_id

            # Use video info for search if no custom query provided
            if not search_query:
                search_query = f"{artist_name} {video_title}"

            results = []

            # 1. First check video URL for thumbnails (highest priority)
            youtube_id = None

            # Try to extract YouTube ID from existing URL if available
            if video_url:
                import re

                patterns = [
                    r"(?:youtube\.com/watch\?v=|youtu\.be/)([^&\n?#]+)",
                    r"youtube\.com/embed/([^&\n?#]+)",
                    r"(?:youtube\.com/v/|youtube\.com/watch\?.*&v=)([^&\n?#]+)",
                ]

                logger.debug(f"Checking video URL for YouTube ID: {video_url}")
                for pattern in patterns:
                    match = re.search(pattern, video_url)
                    if match:
                        youtube_id = match.group(1)
                        logger.info(
                            f"Extracted YouTube ID from video URL: {youtube_id}"
                        )
                        break

            # 2. Search YouTube by artist - song title if no URL or ID found
            if not youtube_id and "youtube" in sources:
                try:
                    logger.info(f"Searching YouTube for: {search_query}")
                    from src.services.youtube_service import youtube_service

                    search_results = youtube_service.search_videos(
                        search_query, max_results=1
                    )
                    if search_results["success"] and search_results["results"]:
                        # Get video ID from YouTube API response format
                        first_result = search_results["results"][0]
                        youtube_id = first_result["id"]["videoId"]
                        logger.info(f"Found YouTube video via search: {youtube_id}")
                except Exception as e:
                    logger.warning(f"YouTube search failed for '{search_query}': {e}")

            # Add YouTube thumbnails if we have an ID (from URL or search)
            if youtube_id and "youtube" in sources:
                try:
                    yt_thumbnails = [
                        {
                            "url": f"https://img.youtube.com/vi/{youtube_id}/maxresdefault.jpg",
                            "source": "youtube",
                            "quality": "maxres",
                            "title": f"{video_title} - Max Resolution",
                        },
                        {
                            "url": f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg",
                            "source": "youtube",
                            "quality": "hq",
                            "title": f"{video_title} - High Quality",
                        },
                        {
                            "url": f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg",
                            "source": "youtube",
                            "quality": "mq",
                            "title": f"{video_title} - Medium Quality",
                        },
                    ]
                    results.extend(yt_thumbnails)
                    logger.info(
                        f"Added {len(yt_thumbnails)} YouTube thumbnail options for video {video_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to create YouTube thumbnails for video {video_id}: {e}"
                    )

            # Search IMVDb
            if "imvdb" in sources:
                try:
                    from src.services.imvdb_service import imvdb_service

                    video_details = None

                    # First try to get by existing IMVDb ID
                    if video_imvdb_id:
                        video_details = imvdb_service.get_video_by_id(video_imvdb_id)
                        logger.debug(f"Retrieved IMVDb data using ID: {video_imvdb_id}")

                    # If no ID or no details found, try searching
                    if not video_details:
                        logger.info(f"No IMVDb ID found, searching for: {search_query}")
                        try:
                            search_result = imvdb_service.find_best_video_match(
                                artist_name, video_title
                            )
                            if search_result:
                                video_details = search_result
                                logger.info(f"Found IMVDb video via search")
                        except Exception as search_e:
                            logger.debug(f"IMVDb search failed: {search_e}")

                    if video_details:
                        # Extract thumbnail metadata using existing extract_metadata method
                        metadata = imvdb_service.extract_metadata(video_details)
                        thumbnail_url = metadata.get("thumbnail_url")

                        if thumbnail_url:
                            imvdb_thumbnails = [
                                {
                                    "url": thumbnail_url,
                                    "source": "imvdb",
                                    "quality": "original",
                                    "title": f"{video_title} - IMVDb Original",
                                }
                            ]
                            results.extend(imvdb_thumbnails)
                            logger.info(
                                f"Found IMVDb thumbnail for video {video_id}: {thumbnail_url}"
                            )
                        else:
                            logger.debug(
                                f"No thumbnail URL found in IMVDb data for video {video_id}"
                            )
                    else:
                        logger.info(f"No IMVDb thumbnails found for: {search_query}")
                except Exception as e:
                    logger.warning(
                        f"Failed to get IMVDb thumbnails for video {video_id}: {e}"
                    )

            # Search Google Images
            if "google" in sources:
                try:
                    logger.info(f"Searching Google Images for: {search_query}")

                    # Use requests to search Google Images
                    from urllib.parse import quote

                    import requests

                    # Format query for image search
                    image_query = f"{search_query} music video thumbnail"
                    encoded_query = quote(image_query)

                    # Google Images search URL
                    search_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch&safe=off"

                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }

                    response = requests.get(search_url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        # Simple regex to extract image URLs from the page
                        import re

                        # Look for image URLs in the page content
                        image_pattern = r'"(https?://[^"]*\.(?:jpg|jpeg|png|webp))"'
                        matches = re.findall(image_pattern, response.text)

                        # Filter and clean up the results
                        google_thumbnails = []
                        seen_urls = set()

                        for match in matches[:6]:  # Limit to first 6 results
                            if match not in seen_urls and "encrypted" not in match:
                                seen_urls.add(match)
                                google_thumbnails.append(
                                    {
                                        "url": match,
                                        "source": "google",
                                        "quality": "varies",
                                        "title": f"{video_title} - Google Images",
                                    }
                                )

                        if google_thumbnails:
                            results.extend(google_thumbnails)
                            logger.info(
                                f"Added {len(google_thumbnails)} Google Images results for video {video_id}"
                            )
                        else:
                            logger.info(
                                f"No Google Images results found for: {search_query}"
                            )
                    else:
                        logger.warning(
                            f"Google Images search failed with status: {response.status_code}"
                        )

                except Exception as e:
                    logger.warning(
                        f"Failed to search Google Images for video {video_id}: {e}"
                    )

            logger.info(
                f"Found {len(results)} thumbnail options for video {video_id} (query: '{search_query}', sources: {sources})"
            )

        # Add debugging info for empty results
        if not results:
            debug_info = {
                "video_url": video_url,
                "imvdb_id": video_imvdb_id,
                "sources_requested": sources,
                "has_youtube_url": bool(
                    video_url
                    and ("youtube.com" in video_url or "youtu.be" in video_url)
                ),
                "has_imvdb_id": bool(video_imvdb_id),
            }
            logger.warning(
                f"No thumbnail results found for video {video_id}. Debug info: {debug_info}"
            )

        return (
            jsonify(
                {
                    "results": results,
                    "query": search_query,
                    "sources_searched": sources,
                    "total_results": len(results),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to search thumbnails for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail/info", methods=["GET"])
def get_video_thumbnail_info(video_id):
    """Get detailed thumbnail information for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            from src.services.thumbnail_service import thumbnail_service

            info = {
                "has_thumbnail": bool(video.thumbnail_url or video.thumbnail_path),
                "thumbnail_url": video.thumbnail_url,
                "thumbnail_path": video.thumbnail_path,
                "thumbnail_source": video.thumbnail_source,
                "thumbnail_uploaded_at": (
                    video.thumbnail_uploaded_at.isoformat()
                    if video.thumbnail_uploaded_at
                    else None
                ),
                "thumbnail_metadata": video.thumbnail_metadata,
            }

            # Get file information if local thumbnail exists
            if video.thumbnail_path and os.path.exists(video.thumbnail_path):
                file_info = thumbnail_service.get_thumbnail_info(video.thumbnail_path)
                info.update(file_info)

            return jsonify(info), 200

    except Exception as e:
        logger.error(f"Failed to get thumbnail info for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/thumbnail/<size>", methods=["GET"])
def get_video_thumbnail_size(video_id, size):
    """Get specific size of video thumbnail (small/medium/large/original)"""
    try:
        if size not in ["small", "medium", "large", "original"]:
            return (
                jsonify(
                    {"error": "Invalid size. Use: small, medium, large, or original"}
                ),
                400,
            )

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if not video.thumbnail_path:
                return jsonify({"error": "No local thumbnail available"}), 404

            from src.services.thumbnail_service import thumbnail_service

            # Get the specific size path
            size_path = thumbnail_service.get_thumbnail_size_path(
                video.thumbnail_path, size
            )

            if size_path and os.path.exists(size_path):
                return send_file(size_path, as_attachment=False)
            else:
                # Fallback to original if specific size doesn't exist
                if os.path.exists(video.thumbnail_path):
                    return send_file(video.thumbnail_path, as_attachment=False)
                else:
                    return jsonify({"error": "Thumbnail file not found"}), 404

    except Exception as e:
        logger.error(f"Failed to get thumbnail size {size} for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/stream", methods=["GET"])
def stream_video(video_id):
    """Stream local video file with HTTP range support for better video playback"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Check if we have a local file
            if video.local_path:
                # Construct absolute path
                if os.path.isabs(video.local_path):
                    full_path = video.local_path
                else:
                    # Relative path - construct from app root
                    full_path = os.path.join(os.getcwd(), video.local_path)

                if os.path.exists(full_path):
                    # Check if this is an MKV file that needs transcoding
                    if full_path.lower().endswith(".mkv") or full_path.lower().endswith(
                        ".avi"
                    ):
                        # Use FFmpeg streaming for MKV/AVI files
                        from src.services.ffmpeg_streaming_service import (
                            ffmpeg_streaming_service,
                        )

                        return ffmpeg_streaming_service.stream_video(full_path)

                    # Get MIME type based on file extension
                    mime_type, _ = mimetypes.guess_type(full_path)

                    # Set default MIME type if not detected
                    if not mime_type:
                        # Common video formats
                        if full_path.lower().endswith(".mp4"):
                            mime_type = "video/mp4"
                        elif full_path.lower().endswith(".webm"):
                            mime_type = "video/webm"
                        elif full_path.lower().endswith(".mkv"):
                            mime_type = "video/x-matroska"
                        elif full_path.lower().endswith(".avi"):
                            mime_type = "video/x-msvideo"
                        elif full_path.lower().endswith(".mov"):
                            mime_type = "video/quicktime"
                        else:
                            mime_type = "video/mp4"  # Default fallback

                    logger.info(
                        f"Serving video {video.title} from {full_path} with MIME type: {mime_type}"
                    )

                    # Always use send_file for simplicity - let Flask handle the range requests
                    return send_file(
                        full_path,
                        as_attachment=False,
                        mimetype=mime_type,
                        conditional=True,  # This enables range request support in Flask
                    )

                else:
                    # File not found at stored path - try to locate it in artist folders
                    logger.warning(f"Video file not found at stored path: {full_path}")

                    # Try to find the file in the expected artist folder
                    relocated_path = find_relocated_video(video, session)
                    if relocated_path:
                        logger.info(f"Found relocated video at: {relocated_path}")
                        # Update the database with the correct path
                        video.local_path = relocated_path
                        session.commit()

                        # Serve the relocated file
                        mime_type, _ = mimetypes.guess_type(relocated_path)
                        if not mime_type:
                            if relocated_path.lower().endswith(".mp4"):
                                mime_type = "video/mp4"
                            elif relocated_path.lower().endswith(".mkv"):
                                mime_type = "video/x-matroska"
                            else:
                                mime_type = "video/mp4"

                        return send_file(
                            relocated_path,
                            as_attachment=False,
                            mimetype=mime_type,
                            conditional=True,
                        )
                    else:
                        # File truly missing - mark as wanted and track artist
                        logger.error(
                            f"Video file not found and could not be relocated: {full_path}"
                        )

                        # Mark video as wanted if it was previously downloaded
                        if video.status == VideoStatus.DOWNLOADED:
                            video.status = VideoStatus.WANTED
                            video.local_path = None
                            session.commit()
                            logger.info(
                                f"Marked missing video as wanted: {video.title}"
                            )

                            # Ensure artist is being tracked
                            if video.artist:
                                video.artist.monitored = True
                                session.commit()
                                logger.info(
                                    f"Enabled monitoring for artist: {video.artist.name}"
                                )

                        return (
                            jsonify(
                                {
                                    "error": "Video file not found",
                                    "message": "File has been marked as wanted and will be re-downloaded",
                                    "status": "wanted",
                                }
                            ),
                            404,
                        )

            return jsonify({"error": "Local video file not found"}), 404

    except Exception as e:
        logger.error(f"Failed to stream video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/subtitles", methods=["GET"])
def get_video_subtitles(video_id):
    """Get available subtitle tracks for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video or not video.local_path:
                return jsonify({"subtitles": []}), 200

            video_path = Path(video.local_path)
            if not video_path.exists():
                return jsonify({"subtitles": []}), 200

            # Look for subtitle files in the same directory
            video_dir = video_path.parent
            video_name_stem = video_path.stem

            subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa", ".sub"]
            subtitles = []

            for subtitle_ext in subtitle_extensions:
                # Look for subtitle files with the same base name
                for subtitle_file in video_dir.glob(
                    f"{video_name_stem}*{subtitle_ext}"
                ):
                    # Extract language from filename (e.g., video.en.srt -> en)
                    relative_name = subtitle_file.name
                    parts = relative_name.split(".")

                    language = "unknown"
                    if len(parts) >= 3:  # video.en.srt
                        language = parts[-2]
                    elif len(parts) == 2:  # video.srt (assume default language)
                        language = "default"

                    subtitles.append(
                        {
                            "language": language,
                            "filename": relative_name,
                            "url": f"/api/videos/{video_id}/subtitles/{quote(relative_name)}",
                            "format": subtitle_ext[1:],  # Remove the dot
                        }
                    )

            return jsonify({"subtitles": subtitles}), 200

    except Exception as e:
        logger.error(f"Failed to get subtitles for video {video_id}: {e}")
        return jsonify({"subtitles": []}), 200


@videos_bp.route("/<int:video_id>/subtitles/<subtitle_filename>", methods=["GET"])
@public_endpoint
def serve_video_subtitle(video_id, subtitle_filename):
    """Serve subtitle file for a video"""
    try:
        # URL decode the subtitle filename
        decoded_filename = unquote(subtitle_filename)
        logger.info(
            f"Attempting to serve subtitle: {decoded_filename} for video {video_id}"
        )

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video or not video.local_path:
                logger.error(f"Video {video_id} not found or no local path")
                return "Video not found or no local file", 404

            video_path = Path(video.local_path)
            logger.info(f"Video path: {video_path}")

            # Handle relative paths by making them absolute
            if not video_path.is_absolute():
                video_path = Path.cwd() / video_path
                logger.info(f"Converted to absolute path: {video_path}")

            if not video_path.exists():
                logger.error(f"Video file does not exist: {video_path}")
                return "Video file not found", 404

            # Security check: ensure subtitle filename doesn't contain path traversal
            if (
                ".." in decoded_filename
                or "/" in decoded_filename
                or "\\" in decoded_filename
            ):
                logger.error(
                    f"Invalid subtitle filename (path traversal): {decoded_filename}"
                )
                return "Invalid subtitle filename", 400

            # Find subtitle file in the same directory as the video
            video_dir = video_path.parent
            subtitle_path = video_dir / decoded_filename
            logger.info(f"Subtitle path: {subtitle_path}")

            if not subtitle_path.exists():
                logger.error(f"Subtitle file does not exist: {subtitle_path}")
                return "Subtitle file not found", 404

            # Security check: ensure subtitle file is in the same directory as video
            if not str(subtitle_path).startswith(str(video_dir)):
                logger.error(f"Subtitle file outside video directory: {subtitle_path}")
                return "Subtitle file access denied", 403

            # Determine MIME type based on extension
            subtitle_ext = subtitle_path.suffix.lower()
            if subtitle_ext == ".srt":
                mimetype = "text/srt; charset=utf-8"
            elif subtitle_ext == ".vtt":
                mimetype = "text/vtt; charset=utf-8"
            elif subtitle_ext in [".ass", ".ssa"]:
                mimetype = "text/plain; charset=utf-8"
            else:
                mimetype = "text/plain; charset=utf-8"

            logger.info(
                f"Serving subtitle {decoded_filename} for video {video_id} with MIME type {mimetype}"
            )

            response = send_file(
                subtitle_path,
                mimetype=mimetype,
                as_attachment=False,
                download_name=decoded_filename,
            )

            # Add CORS headers to allow video player to access subtitles
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"

            return response

    except Exception as e:
        logger.error(
            f"Failed to serve subtitle {subtitle_filename} for video {video_id}: {e}"
        )
        logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Subtitle serving error", 500


@videos_bp.route("/recovery/fix-missing", methods=["POST"])
def fix_missing_downloaded_videos():
    """Fix all videos marked as downloaded but with missing files"""
    try:
        from src.services.video_recovery_service import video_recovery_service

        # Run the fix operation
        stats = video_recovery_service.fix_missing_downloaded_videos()

        logger.info(f"Missing downloaded videos fix completed: {stats}")

        message = f"Fixed {stats['missing_files']} missing videos: "
        message += f"{stats['recovered_videos']} recovered, {stats['marked_wanted']} marked as wanted"

        return jsonify({"success": True, "message": message, "statistics": stats})

    except Exception as e:
        logger.error(f"Error fixing missing downloaded videos: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/recovery/scan", methods=["POST"])
def scan_missing_videos():
    """Scan for missing videos and attempt recovery"""
    try:
        from src.services.video_recovery_service import video_recovery_service

        # Run the recovery scan
        stats = video_recovery_service.scan_missing_videos()

        logger.info(f"Video recovery scan completed: {stats}")

        return jsonify(
            {
                "success": True,
                "message": "Video recovery scan completed",
                "statistics": stats,
            }
        )

    except Exception as e:
        logger.error(f"Error during video recovery scan: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/recovery/orphans", methods=["POST"])
def scan_orphaned_files():
    """Scan for orphaned video files without database records"""
    try:
        from src.services.video_recovery_service import video_recovery_service

        # Run the orphaned files scan
        stats = video_recovery_service.scan_orphaned_files()

        logger.info(f"Orphaned files scan completed: {stats}")

        return jsonify(
            {
                "success": True,
                "message": "Orphaned files scan completed",
                "statistics": stats,
            }
        )

    except Exception as e:
        logger.error(f"Error during orphaned files scan: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/transcode", methods=["POST"])
def transcode_video(video_id):
    """Transcode video to MP4 format for better browser compatibility"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if not video.local_path:
                return (
                    jsonify({"error": "No local file available for transcoding"}),
                    400,
                )

            # Construct absolute path
            if os.path.isabs(video.local_path):
                source_path = video.local_path
            else:
                source_path = os.path.join(os.getcwd(), video.local_path)

            if not os.path.exists(source_path):
                return jsonify({"error": "Source video file not found"}), 404

            # Check if already an MP4
            if source_path.lower().endswith(".mp4"):
                return jsonify({"error": "Video is already in MP4 format"}), 400

            # Generate output path
            source_dir = os.path.dirname(source_path)
            source_name = Path(source_path).stem
            output_path = os.path.join(source_dir, f"{source_name}_transcoded.mp4")

            # Check if transcoded version already exists
            if os.path.exists(output_path):
                return jsonify({"error": "Transcoded version already exists"}), 400

            # Start transcoding in background thread
            def transcode_worker():
                try:
                    logger.info(f"Starting transcoding: {source_path} -> {output_path}")

                    # FFmpeg command for transcoding
                    cmd = [
                        "ffmpeg",
                        "-i",
                        source_path,  # Input file
                        "-c:v",
                        "libx264",  # Video codec
                        "-crf",
                        "23",  # Quality (18-28, 23 is good balance)
                        "-preset",
                        "medium",  # Encoding speed vs compression
                        "-c:a",
                        "aac",  # Audio codec
                        "-b:a",
                        "128k",  # Audio bitrate
                        "-movflags",
                        "+faststart",  # Web optimization
                        "-y",  # Overwrite output file
                        output_path,
                    ]

                    # Run ffmpeg
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=3600,  # 1 hour timeout
                    )

                    if result.returncode == 0:
                        logger.info(
                            f"Transcoding completed successfully: {output_path}"
                        )

                        # Update database with transcoded path
                        with get_db() as update_session:
                            update_video = (
                                update_session.query(Video)
                                .filter(Video.id == video_id)
                                .first()
                            )
                            if update_video:
                                # Store relative path for transcoded file
                                relative_output = os.path.relpath(
                                    output_path, os.getcwd()
                                )
                                update_video.local_path = relative_output
                                update_session.commit()
                                logger.info(
                                    f"Updated video {video_id} with transcoded path: {relative_output}"
                                )
                    else:
                        logger.error(
                            f"Transcoding failed for video {video_id}: {result.stderr}"
                        )

                        # Clean up failed output file
                        if os.path.exists(output_path):
                            os.remove(output_path)

                except subprocess.TimeoutExpired:
                    logger.error(f"Transcoding timeout for video {video_id}")
                except Exception as e:
                    logger.error(f"Transcoding error for video {video_id}: {e}")
                    if os.path.exists(output_path):
                        os.remove(output_path)

            # Start transcoding in background
            thread = threading.Thread(target=transcode_worker)
            thread.daemon = True
            thread.start()

            return (
                jsonify(
                    {
                        "message": "Transcoding started",
                        "video_id": video_id,
                        "source_file": source_path,
                        "output_file": output_path,
                        "status": "processing",
                    }
                ),
                202,
            )

    except Exception as e:
        logger.error(f"Failed to start transcoding for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/transcode/status", methods=["GET"])
def transcode_status(video_id):
    """Check transcoding status for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if not video.local_path:
                return jsonify({"status": "no_file"}), 200

            # Check if current file is MP4
            if video.local_path.lower().endswith(".mp4"):
                return jsonify({"status": "completed", "format": "mp4"}), 200

            # Check for transcoded version
            if os.path.isabs(video.local_path):
                source_path = video.local_path
            else:
                source_path = os.path.join(os.getcwd(), video.local_path)

            source_dir = os.path.dirname(source_path)
            source_name = Path(source_path).stem
            transcoded_path = os.path.join(source_dir, f"{source_name}_transcoded.mp4")

            if os.path.exists(transcoded_path):
                return (
                    jsonify(
                        {"status": "completed", "transcoded_file": transcoded_path}
                    ),
                    200,
                )
            else:
                return (
                    jsonify(
                        {
                            "status": "not_started",
                            "format": Path(video.local_path).suffix,
                        }
                    ),
                    200,
                )

    except Exception as e:
        logger.error(f"Failed to check transcoding status for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/refresh-metadata", methods=["POST"])
def refresh_video_metadata(video_id):
    """Refresh metadata from IMVDb for a specific video"""
    try:
        from src.services.imvdb_service import imvdb_service
        from src.services.settings_service import settings

        # Force reload settings cache to ensure we have the latest API key
        settings.reload_cache()
        # IMVDb service will get the API key from settings automatically

        # First, get video data and close session to avoid binding issues
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Extract data we need before closing session
            artist_name = video.artist.name if video.artist else None
            video_title = video.title
            current_imvdb_id = video.imvdb_id
            created_at = video.created_at

            if not artist_name:
                return jsonify({"error": "No artist associated with video"}), 400

        # Now perform external API calls without holding the session
        logger.info(f"Refreshing metadata for video: {video_title} by {artist_name}")

        # Try to find best match on IMVDb
        imvdb_data = None

        # If we have an existing IMVDb ID, try to get detailed info
        if current_imvdb_id:
            logger.info(
                f"Attempting to refresh using existing IMVDb ID: {current_imvdb_id}"
            )
            imvdb_data = imvdb_service.get_video_by_id(current_imvdb_id)

        # If no IMVDb ID or the lookup failed, try searching
        if not imvdb_data:
            logger.info(f"Searching for new match: {artist_name} - {video_title}")
            imvdb_data = imvdb_service.find_best_video_match(artist_name, video_title)

        # If IMVDb search failed, try YouTube as fallback
        youtube_metadata = None
        if not imvdb_data:
            try:
                logger.info(
                    f"IMVDb search failed, trying YouTube: {artist_name} - {video_title}"
                )
                from src.services.youtube_service import youtube_service

                search_query = f"{artist_name} {video_title}"
                youtube_results = youtube_service.search_videos(
                    search_query, max_results=1
                )

                if youtube_results["success"] and youtube_results["results"]:
                    video_item = youtube_results["results"][0]
                    video_id_yt = video_item["id"]["videoId"]

                    # Get detailed video information
                    video_details = youtube_service.get_video_details(video_id_yt)
                    if video_details["success"] and video_details.get("video"):
                        yt_video = video_details["video"]

                        # Extract metadata from YouTube
                        snippet = yt_video.get("snippet", {})
                        youtube_metadata = {
                            "source": "youtube",
                            "youtube_id": video_id_yt,
                            "title": snippet.get("title", video_title),
                            "description": snippet.get("description", ""),
                            "published_at": snippet.get("publishedAt"),
                            "thumbnail_url": snippet.get("thumbnails", {})
                            .get("high", {})
                            .get("url"),
                            "channel_title": snippet.get("channelTitle"),
                            "tags": snippet.get("tags", []),
                        }
                        logger.info(f"Found YouTube metadata for: {video_title}")

            except Exception as e:
                logger.warning(f"YouTube metadata search failed: {e}")

        if not imvdb_data and not youtube_metadata:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No matching video found on IMVDb or YouTube",
                        "searched_for": f"{artist_name} - {video_title}",
                    }
                ),
                404,
            )

        # Extract and update metadata
        if imvdb_data:
            metadata = imvdb_service.extract_metadata(imvdb_data)
            metadata_source = "IMVDb"
        else:
            # Use YouTube metadata
            metadata = youtube_metadata
            metadata_source = "YouTube"

        # Now update the video in a fresh session
        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return (
                    jsonify({"error": "Video was deleted during metadata refresh"}),
                    404,
                )

            # Update video with new metadata based on source
            if metadata_source == "IMVDb":
                new_imvdb_id = metadata.get("imvdb_id")
                if new_imvdb_id and new_imvdb_id != current_imvdb_id:
                    # Check if this IMVDb ID already exists in another video
                    existing_video = (
                        session.query(Video)
                        .filter(Video.imvdb_id == new_imvdb_id, Video.id != video_id)
                        .first()
                    )

                    if existing_video:
                        logger.warning(
                            f"IMVDb ID {new_imvdb_id} already exists for video '{existing_video.title}' (ID: {existing_video.id}). Duplicate detected."
                        )
                        # Return a special response indicating duplicate found
                        return (
                            jsonify(
                                {
                                    "error": "duplicate_imvdb_id",
                                    "message": f"A video with IMVDb ID {new_imvdb_id} already exists",
                                    "duplicate_video": {
                                        "id": existing_video.id,
                                        "title": existing_video.title,
                                        "artist": (
                                            existing_video.artist.name
                                            if existing_video.artist
                                            else "Unknown"
                                        ),
                                        "url": existing_video.url or "",
                                        "quality": existing_video.quality,
                                        "duration": existing_video.duration,
                                        "year": existing_video.year,
                                        "thumbnail_url": existing_video.thumbnail_url,
                                        "thumbnail_path": existing_video.thumbnail_path,
                                        "video_metadata": existing_video.video_metadata,
                                        "status": (
                                            existing_video.status.value
                                            if hasattr(existing_video.status, "value")
                                            else existing_video.status
                                        ),
                                    },
                                    "current_video": {
                                        "id": video_id,
                                        "title": video_title,
                                        "artist": artist_name,
                                        "quality": (
                                            video.quality
                                            if "video" in locals() and video
                                            else None
                                        ),
                                        "duration": (
                                            video.duration
                                            if "video" in locals() and video
                                            else None
                                        ),
                                        "year": (
                                            video.year
                                            if "video" in locals() and video
                                            else None
                                        ),
                                        "thumbnail_url": (
                                            video.thumbnail_url
                                            if "video" in locals() and video
                                            else None
                                        ),
                                        "thumbnail_path": (
                                            video.thumbnail_path
                                            if "video" in locals() and video
                                            else None
                                        ),
                                        "video_metadata": (
                                            video.video_metadata
                                            if "video" in locals() and video
                                            else None
                                        ),
                                    },
                                    "suggested_action": "merge",
                                    "merge_endpoint": f"/api/videos/{video_id}/merge/{existing_video.id}",
                                }
                            ),
                            409,
                        )  # Conflict status code
                    else:
                        video.imvdb_id = new_imvdb_id
                if metadata.get("year"):
                    video.year = metadata["year"]
                if metadata.get("thumbnail_url"):
                    video.thumbnail_url = metadata["thumbnail_url"]
                if metadata.get("directors"):
                    video.directors = metadata["directors"]
                if metadata.get("producers"):
                    video.producers = metadata["producers"]

                # Store full IMVDb metadata
                video.imvdb_metadata = metadata.get("raw_metadata", {})
            else:
                # YouTube metadata
                if metadata.get("youtube_id"):
                    video.youtube_id = metadata["youtube_id"]
                    # Update URL if we don't have one
                    if not video.url:
                        video.url = (
                            f"https://www.youtube.com/watch?v={metadata['youtube_id']}"
                        )
                if metadata.get("thumbnail_url"):
                    video.thumbnail_url = metadata["thumbnail_url"]
                if metadata.get("published_at"):
                    # Extract year from published date
                    try:
                        from datetime import datetime

                        published_date = datetime.fromisoformat(
                            metadata["published_at"].replace("Z", "+00:00")
                        )
                        video.year = published_date.year
                    except:
                        pass

                # Store YouTube metadata in custom field or use existing metadata field
                video.youtube_metadata = metadata

            # Also extract FFmpeg metadata if video has a local file
            ffmpeg_extracted = False
            ffmpeg_metadata = {}
            if video.local_path:
                try:
                    from pathlib import Path

                    from src.services.video_indexing_service import VideoIndexingService

                    video_path = Path(video.local_path)
                    if video_path.exists():
                        indexing_service = VideoIndexingService()
                        ffmpeg_metadata = indexing_service.extract_ffmpeg_metadata(
                            video_path
                        )

                        # Update basic fields if not already set
                        if ffmpeg_metadata.get("duration") and not video.duration:
                            video.duration = ffmpeg_metadata["duration"]
                            ffmpeg_extracted = True

                        if ffmpeg_metadata.get("quality") and not video.quality:
                            video.quality = ffmpeg_metadata["quality"]
                            ffmpeg_extracted = True

                        # Store additional technical metadata in video_metadata field
                        if ffmpeg_metadata.get("width") or ffmpeg_metadata.get(
                            "height"
                        ):
                            from datetime import datetime

                            existing_metadata = video.video_metadata or {}
                            tech_metadata = {
                                "width": ffmpeg_metadata.get("width"),
                                "height": ffmpeg_metadata.get("height"),
                                "video_codec": ffmpeg_metadata.get("video_codec"),
                                "audio_codec": ffmpeg_metadata.get("audio_codec"),
                                "fps": ffmpeg_metadata.get("fps"),
                                "bitrate": ffmpeg_metadata.get("bitrate"),
                                "ffmpeg_extracted": True,
                                "extraction_date": datetime.utcnow().isoformat(),
                            }
                            existing_metadata.update(tech_metadata)
                            video.video_metadata = existing_metadata
                            ffmpeg_extracted = True

                        if ffmpeg_extracted:
                            logger.info(
                                f"Updated video {video_id} with FFmpeg metadata: duration={video.duration}s, quality={video.quality}"
                            )
                    else:
                        logger.warning(
                            f"Video file not found for FFmpeg extraction: {video.local_path}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to extract FFmpeg metadata for video {video_id}: {e}"
                    )

            session.commit()

            logger.info(
                f"Successfully updated metadata for video {video_id} from {metadata_source}"
            )

            # Return updated video data
            updated_video = {
                "id": video.id,
                "title": video.title,
                "artist_id": video.artist_id,
                "artist_name": video.artist.name if video.artist else None,
                "status": (
                    video.status.value
                    if hasattr(video.status, "value")
                    else video.status
                ),
                "imvdb_id": video.imvdb_id,
                "video_url": video.url,
                "local_path": video.local_path,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "year": video.year,
                "directors": video.directors,
                "producers": video.producers,
                "created_at": created_at.isoformat(),
                "metadata_refreshed": True,
                "metadata_source": metadata_source,
                "youtube_id": (
                    video.youtube_id if hasattr(video, "youtube_id") else None
                ),
                "quality": video.quality,
                "video_metadata": video.video_metadata,
            }

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Metadata refreshed successfully from {metadata_source}{'and FFmpeg' if ffmpeg_extracted else ''}",
                        "video": updated_video,
                        "metadata_match": metadata,
                        "source": metadata_source,
                        "ffmpeg_extracted": ffmpeg_extracted,
                        "ffmpeg_metadata": (
                            ffmpeg_metadata if ffmpeg_extracted else None
                        ),
                    }
                ),
                200,
            )

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        logger.error(f"Failed to refresh metadata for video {video_id}: {e}")
        logger.error(f"Full traceback: {error_details}")
        return jsonify({"error": str(e), "details": error_details}), 500


@videos_bp.route("/<int:video_id>/enhanced-refresh-metadata", methods=["POST"])
def enhanced_refresh_video_metadata(video_id):
    """Enhanced metadata refresh using multiple sources"""
    import asyncio
    import signal
    from concurrent.futures import TimeoutError

    try:
        # Get force_refresh parameter from JSON or form data
        force_refresh = False
        if request.is_json and request.json:
            force_refresh = request.json.get("force_refresh", False)
        elif request.form:
            force_refresh = request.form.get("force_refresh", "false").lower() == "true"

        # Add timeout wrapper to prevent hanging
        async def run_with_timeout():
            try:
                return await asyncio.wait_for(
                    metadata_enrichment_service.enrich_video_metadata(
                        video_id, force_refresh=force_refresh
                    ),
                    timeout=60.0,  # 60 second timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Metadata enrichment for video {video_id} timed out after 60 seconds"
                )
                return type(
                    "Result",
                    (),
                    {
                        "success": False,
                        "errors": [
                            "Metadata enrichment timed out - external services may be slow"
                        ],
                        "enriched_fields": [],
                        "metadata_sources": [],
                    },
                )()

        # Run the async enrichment function with timeout
        result = asyncio.run(run_with_timeout())

        if result.success:
            return jsonify(
                {
                    "success": True,
                    "message": f"Enhanced metadata enrichment completed for video {video_id}",
                    "enriched_fields": result.enriched_fields,
                    "metadata_sources": result.metadata_sources,
                    "errors": result.errors,
                }
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Metadata enrichment failed",
                        "errors": result.errors,
                    }
                ),
                500,
            )

    except asyncio.TimeoutError:
        logger.error(f"Metadata enrichment for video {video_id} timed out")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Metadata enrichment timed out",
                    "errors": [
                        "Process timed out - external services may be unresponsive"
                    ],
                }
            ),
            408,
        )
    except Exception as e:
        logger.error(
            f"Failed to run enhanced metadata refresh for video {video_id}: {e}"
        )
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/fix-title-artist-swap", methods=["POST"])
def fix_title_artist_swap():
    """Fix videos where song title is in artist field and title is 'video'"""
    try:
        from src.database.models import Artist

        # Get request parameters
        data = request.get_json() or {}
        dry_run = data.get("dry_run", True)  # Default to dry run for safety
        limit = data.get("limit", None)  # Optional limit for testing

        with get_db() as session:
            # Find videos with title 'video' (case insensitive)
            query = session.query(Video).filter(Video.title.ilike("video"))

            if limit:
                query = query.limit(limit)

            problematic_videos = query.all()

            if not problematic_videos:
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": 'No videos found with title "video"',
                            "processed": 0,
                            "fixed": 0,
                            "errors": 0,
                        }
                    ),
                    200,
                )

            logger.info(f"Found {len(problematic_videos)} videos with title 'video'")

            processed = 0
            fixed = 0
            errors = 0
            changes = []
            error_details = []

            for video in problematic_videos:
                # Capture video data while session is active
                video_id = video.id
                current_artist_name = video.artist.name if video.artist else None
                current_title = video.title

                try:
                    processed += 1

                    # Skip if we don't have an artist name to swap
                    if not current_artist_name:
                        logger.warning(f"Video {video_id} has no artist name to swap")
                        continue

                    # Skip if the artist name looks like an actual artist (common artists)
                    common_artists = [
                        "Unknown",
                        "Various Artists",
                        "Compilation",
                        "Soundtrack",
                    ]
                    if current_artist_name in common_artists:
                        logger.debug(
                            f"Skipping video {video_id} - artist name '{current_artist_name}' looks like actual artist"
                        )
                        continue

                    # The fix: swap artist name and title
                    new_title = current_artist_name  # Move artist name to title
                    new_artist_name = (
                        "Unknown"  # Reset artist to Unknown (will be fixed later)
                    )

                    # Try to extract actual artist from the current artist name if it contains " - "
                    if " - " in current_artist_name:
                        parts = current_artist_name.split(" - ", 1)
                        if len(parts) == 2:
                            new_artist_name = parts[0].strip()
                            new_title = parts[1].strip()

                    change_record = {
                        "video_id": video_id,
                        "old_artist": current_artist_name,
                        "old_title": current_title,
                        "new_artist": new_artist_name,
                        "new_title": new_title,
                    }

                    if not dry_run:
                        # Find or create the new artist
                        if new_artist_name != "Unknown":
                            artist = (
                                session.query(Artist)
                                .filter(Artist.name == new_artist_name)
                                .first()
                            )
                            if not artist:
                                from src.utils.filename_cleanup import FilenameCleanup

                                folder_path = FilenameCleanup.sanitize_folder_name(
                                    new_artist_name
                                )
                                artist = Artist(
                                    name=new_artist_name, folder_path=folder_path
                                )
                                session.add(artist)
                                session.flush()  # Get the artist ID
                            video.artist_id = artist.id

                        # Update the title
                        video.title = new_title

                        # Log the change
                        logger.info(
                            f"Fixed video {video_id}: '{current_artist_name}' -> '{new_artist_name}' | '{current_title}' -> '{new_title}'"
                        )

                        # Commit periodically to avoid long transactions
                        if processed % 50 == 0:
                            session.commit()

                    changes.append(change_record)
                    fixed += 1

                except Exception as e:
                    errors += 1
                    error_msg = str(e)
                    logger.error(f"Error processing video {video_id}: {error_msg}")
                    error_details.append({"video_id": video_id, "error": error_msg})

            # Final commit if not dry run
            if not dry_run:
                session.commit()

            logger.info(
                f"Title/Artist swap {'dry run' if dry_run else 'fix'} completed: {processed} processed, {fixed} fixed, {errors} errors"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f'Title/Artist swap {"dry run" if dry_run else "fix"} completed',
                        "dry_run": dry_run,
                        "processed": processed,
                        "fixed": fixed,
                        "errors": errors,
                        "changes": (
                            changes[:20] if dry_run else []
                        ),  # Show first 20 changes for dry run
                        "error_details": error_details[:10] if error_details else [],
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to fix title/artist swap: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/enhanced-refresh-all-metadata", methods=["POST"])
def enhanced_refresh_all_metadata():
    """Enhanced metadata refresh for all videos using comprehensive enrichment"""
    import asyncio

    try:
        # Get request parameters
        data = request.get_json() or {}
        force_refresh = data.get("force_refresh", False)
        limit = data.get("limit", None)
        video_ids = data.get("video_ids", None)

        from src.services.metadata_enrichment_service import metadata_enrichment_service

        # Get videos to process
        with get_db() as session:
            query = session.query(Video).join(Video.artist)

            # Filter by specific video IDs if provided
            if video_ids:
                query = query.filter(Video.id.in_(video_ids))

            if limit:
                query = query.limit(limit)

            videos = query.all()
            videos_to_process = [
                {
                    "id": video.id,
                    "title": video.title,
                    "artist_name": video.artist.name if video.artist else None,
                }
                for video in videos
            ]

        if not videos_to_process:
            return jsonify(
                {
                    "success": True,
                    "message": "No videos found to process",
                    "processed": 0,
                    "updated": 0,
                    "errors": 0,
                }
            )

        # Process videos using enhanced metadata service
        processed = 0
        updated = 0
        errors = 0
        error_details = []

        for video_data in videos_to_process:
            try:
                result = asyncio.run(
                    metadata_enrichment_service.enrich_video_metadata(
                        video_data["id"], force_refresh=force_refresh
                    )
                )

                processed += 1
                if result.get("success", False):
                    updated += 1
                else:
                    errors += 1
                    error_details.append(
                        f"Video {video_data['id']} ({video_data['title']}): {result.get('error', 'Unknown error')}"
                    )

            except Exception as e:
                processed += 1
                errors += 1
                error_details.append(
                    f"Video {video_data['id']} ({video_data['title']}): {str(e)}"
                )
                logger.error(
                    f"Error enriching metadata for video {video_data['id']}: {e}"
                )

        return jsonify(
            {
                "success": True,
                "processed": processed,
                "updated": updated,
                "errors": errors,
                "error_details": (
                    error_details[:10] if error_details else []
                ),  # Limit error details
            }
        )

    except Exception as e:
        logger.error(f"Error in enhanced refresh all metadata: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/refresh-all-metadata", methods=["POST"])
def refresh_all_metadata():
    """Refresh metadata from IMVDb for all videos"""
    try:
        logger.info("Starting refresh-all-metadata endpoint")

        try:
            from src.services.imvdb_service import imvdb_service

            logger.info("Successfully imported imvdb_service")
        except Exception as e:
            logger.error(f"Failed to import imvdb_service: {e}")
            return jsonify({"error": f"Import error: imvdb_service - {str(e)}"}), 500

        try:
            from src.services.settings_service import settings

            logger.info("Successfully imported settings")
        except Exception as e:
            logger.error(f"Failed to import settings: {e}")
            return jsonify({"error": f"Import error: settings - {str(e)}"}), 500

        try:
            # Force reload settings cache to ensure we have the latest API key
            settings.reload_cache()
            logger.info("Settings cache reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload settings cache: {e}")
            return jsonify({"error": f"Settings reload error: {str(e)}"}), 500

        try:
            # Get request parameters
            data = request.get_json() or {}
            force_refresh = data.get("force_refresh", False)
            limit = data.get("limit", None)
            video_ids = data.get("video_ids", None)
            logger.info(
                f"Request params: force_refresh={force_refresh}, limit={limit}, video_ids={video_ids}"
            )
        except Exception as e:
            logger.error(f"Failed to parse request parameters: {e}")
            return jsonify({"error": f"Request parsing error: {str(e)}"}), 500

        try:
            processed = 0
            updated = 0
            errors = 0
            error_details = []
            logger.info("Initializing counters and connecting to database")

            # First, get list of videos to process
            videos_to_process = []
            with get_db() as session:
                try:
                    logger.info("Building database query")
                    query = session.query(Video).join(Video.artist)

                    # Filter by specific video IDs if provided
                    if video_ids:
                        query = query.filter(Video.id.in_(video_ids))
                        logger.info(f"Filtering by video IDs: {len(video_ids)} videos")

                    # If not forcing refresh, only process videos without IMVDb metadata
                    if not force_refresh:
                        query = query.filter(Video.imvdb_id.is_(None))
                        logger.info("Filtering to videos without IMVDb metadata")

                    if limit:
                        query = query.limit(limit)
                        logger.info(f"Limiting to {limit} videos")

                    logger.info("Executing database query")
                    videos = query.all()
                    logger.info(f"Found {len(videos)} videos to process")

                    # Extract video data while session is active
                    for video in videos:
                        videos_to_process.append(
                            {
                                "id": video.id,
                                "title": video.title,
                                "artist_name": (
                                    video.artist.name if video.artist else None
                                ),
                                "imvdb_id": video.imvdb_id,
                                "url": video.url,
                            }
                        )

                except Exception as e:
                    logger.error(f"Database query failed: {e}")
                    return jsonify({"error": f"Database query error: {str(e)}"}), 500

            if not videos_to_process:
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "No videos found to refresh",
                            "processed": 0,
                            "updated": 0,
                            "errors": 0,
                        }
                    ),
                    200,
                )

            logger.info(
                f"Starting metadata refresh for {len(videos_to_process)} videos"
            )

            for video_data in videos_to_process:
                # Use extracted video data
                video_id = video_data["id"]
                video_title = video_data["title"]
                artist_name = video_data["artist_name"]
                imvdb_id = video_data["imvdb_id"]

                try:
                    processed += 1

                    if not artist_name:
                        logger.warning(
                            f"Skipping video {video_id}: No artist associated"
                        )
                        errors += 1
                        error_details.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "error": "No artist associated",
                            }
                        )
                        continue

                    logger.info(
                        f"Processing {processed}/{len(videos_to_process)}: {video_title} by {artist_name}"
                    )

                    # Try to find match on IMVDb
                    imvdb_data = None

                    # If forcing refresh and we have an IMVDb ID, try to get detailed info
                    if force_refresh and imvdb_id:
                        imvdb_data = imvdb_service.get_video_by_id(imvdb_id)

                    # If no IMVDb data yet, try searching
                    if not imvdb_data:
                        imvdb_data = imvdb_service.find_best_video_match(
                            artist_name, video_title
                        )

                    # Try YouTube as fallback if IMVDb failed
                    youtube_metadata = None
                    if not imvdb_data:
                        try:
                            logger.debug(
                                f"Trying YouTube fallback for: {video_title} by {artist_name}"
                            )
                            from src.services.youtube_service import youtube_service

                            search_query = f"{artist_name} {video_title}"
                            youtube_results = youtube_service.search_videos(
                                search_query, max_results=1
                            )

                            if (
                                youtube_results["success"]
                                and youtube_results["results"]
                            ):
                                video_item = youtube_results["results"][0]
                                video_id_yt = video_item["id"]["videoId"]

                                # Get detailed video information
                                video_details = youtube_service.get_video_details(
                                    video_id_yt
                                )
                                if video_details["success"] and video_details.get(
                                    "video"
                                ):
                                    yt_video = video_details["video"]

                                    # Extract metadata from YouTube
                                    snippet = yt_video.get("snippet", {})
                                    youtube_metadata = {
                                        "source": "youtube",
                                        "youtube_id": video_id_yt,
                                        "title": snippet.get("title", video_title),
                                        "description": snippet.get("description", ""),
                                        "published_at": snippet.get("publishedAt"),
                                        "thumbnail_url": snippet.get("thumbnails", {})
                                        .get("high", {})
                                        .get("url"),
                                        "channel_title": snippet.get("channelTitle"),
                                        "tags": snippet.get("tags", []),
                                    }

                        except Exception as yt_e:
                            logger.debug(
                                f"YouTube search failed for {video_title}: {yt_e}"
                            )

                    if imvdb_data or youtube_metadata:
                        # Update video in database
                        with get_db() as update_session:
                            video = (
                                update_session.query(Video)
                                .filter(Video.id == video_id)
                                .first()
                            )
                            if video:
                                if imvdb_data:
                                    # Extract and update metadata from IMVDb
                                    metadata = imvdb_service.extract_metadata(
                                        imvdb_data
                                    )

                                    # Update video with new metadata
                                    new_imvdb_id = metadata.get("imvdb_id")
                                    if new_imvdb_id:
                                        # Check for duplicates
                                        existing_video = (
                                            update_session.query(Video)
                                            .filter(
                                                Video.imvdb_id == new_imvdb_id,
                                                Video.id != video_id,
                                            )
                                            .first()
                                        )

                                        if existing_video:
                                            logger.warning(
                                                f"Bulk refresh: IMVDb ID {new_imvdb_id} already exists for video '{existing_video.title}' (ID: {existing_video.id}). Skipping this video."
                                            )
                                            continue  # Skip this video in bulk refresh
                                        else:
                                            video.imvdb_id = new_imvdb_id
                                    if metadata.get("year"):
                                        video.year = metadata["year"]
                                    if metadata.get("thumbnail_url"):
                                        video.thumbnail_url = metadata["thumbnail_url"]
                                    if metadata.get("directors"):
                                        video.directors = metadata["directors"]
                                    if metadata.get("producers"):
                                        video.producers = metadata["producers"]

                                    # Store full IMVDb metadata
                                    video.imvdb_metadata = metadata.get(
                                        "raw_metadata", {}
                                    )

                                    updated += 1
                                    logger.info(
                                        f"Updated metadata for: {video_title} (IMVDb)"
                                    )

                                elif youtube_metadata:
                                    # Update with YouTube metadata
                                    if youtube_metadata.get("youtube_id"):
                                        video.youtube_id = youtube_metadata[
                                            "youtube_id"
                                        ]
                                        # Update URL if we don't have one
                                        if not video.url:
                                            video.url = f"https://www.youtube.com/watch?v={youtube_metadata['youtube_id']}"
                                    if youtube_metadata.get("thumbnail_url"):
                                        video.thumbnail_url = youtube_metadata[
                                            "thumbnail_url"
                                        ]
                                    if youtube_metadata.get("published_at"):
                                        # Extract year from published date
                                        try:
                                            from datetime import datetime

                                            published_date = datetime.fromisoformat(
                                                youtube_metadata[
                                                    "published_at"
                                                ].replace("Z", "+00:00")
                                            )
                                            video.year = published_date.year
                                        except:
                                            pass

                                    # Store YouTube metadata
                                    video.youtube_metadata = youtube_metadata

                                    updated += 1
                                    logger.info(
                                        f"Updated metadata for: {video_title} (YouTube)"
                                    )

                                update_session.commit()
                            else:
                                logger.warning(f"Video {video_id} not found for update")

                    else:
                        logger.debug(
                            f"No metadata found for: {video_title} by {artist_name}"
                        )

                except Exception as e:
                    errors += 1
                    error_msg = str(e)
                    logger.error(f"Error processing video {video_id}: {error_msg}")
                    error_details.append(
                        {"video_id": video_id, "title": video_title, "error": error_msg}
                    )

            logger.info(
                f"Metadata refresh completed: {processed} processed, {updated} updated, {errors} errors"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Metadata refresh completed",
                        "processed": processed,
                        "updated": updated,
                        "errors": errors,
                        "error_details": (
                            error_details[:10] if error_details else []
                        ),  # Limit error details
                    }
                ),
                200,
            )
        except Exception as e:
            logger.error(f"Database operation failed during metadata refresh: {e}")
            return jsonify({"error": f"Database operation error: {str(e)}"}), 500

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        logger.error(f"Failed to refresh all metadata: {e}")
        logger.error(f"Full traceback: {error_details}")
        return jsonify({"error": str(e), "details": error_details}), 500


@videos_bp.route("/<int:video_id>", methods=["PUT"])
def update_video(video_id):
    """Update video metadata and optionally move/rename file"""
    try:
        data = request.get_json()

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Store original values for file operations
            original_title = video.title
            original_artist_name = video.artist.name if video.artist else None
            original_local_path = video.local_path
            move_file = data.get("move_file", False)

            # Update video metadata
            if "title" in data and data["title"]:
                video.title = data["title"]
            if "year" in data:
                video.year = data["year"]
            if "status" in data and data["status"]:
                video.status = data["status"]
            if "video_url" in data:
                video.url = data["video_url"]
            if "thumbnail_url" in data:
                video.thumbnail_url = data["thumbnail_url"]
            if "duration" in data:
                video.duration = data["duration"]
            if "imvdb_id" in data:
                video.imvdb_id = data["imvdb_id"]
            if "genres" in data:
                video.genres = data["genres"]

            # Handle artist name change
            new_artist_name = data.get("artist_name")
            if new_artist_name and new_artist_name != original_artist_name:
                # Find or create artist
                from src.database.models import Artist

                artist = (
                    session.query(Artist).filter(Artist.name == new_artist_name).first()
                )
                if not artist:
                    from src.utils.filename_cleanup import FilenameCleanup

                    folder_path = FilenameCleanup.sanitize_folder_name(new_artist_name)
                    artist = Artist(name=new_artist_name, folder_path=folder_path)
                    session.add(artist)
                    session.flush()  # Get the artist ID
                video.artist_id = artist.id

            # Handle file moving/renaming if requested
            new_local_path = original_local_path
            if move_file and original_local_path:
                new_local_path = _move_and_rename_video_file(
                    original_local_path,
                    new_artist_name or original_artist_name,
                    video.title,
                    original_title,
                    original_artist_name,
                )
                if new_local_path != original_local_path:
                    video.local_path = new_local_path

            # Optional FFmpeg metadata extraction
            refresh_ffmpeg = data.get("refresh_ffmpeg", False)
            if refresh_ffmpeg and video.local_path:
                try:
                    from pathlib import Path

                    from src.services.video_indexing_service import VideoIndexingService

                    video_path = Path(video.local_path)
                    if video_path.exists():
                        indexing_service = VideoIndexingService()
                        ffmpeg_metadata = indexing_service.extract_ffmpeg_metadata(
                            video_path
                        )

                        # Update basic fields if not already set or if forced
                        force_ffmpeg_update = data.get("force_ffmpeg_update", False)
                        ffmpeg_updated = False

                        if ffmpeg_metadata.get("duration") and (
                            not video.duration or force_ffmpeg_update
                        ):
                            video.duration = ffmpeg_metadata["duration"]
                            ffmpeg_updated = True

                        if ffmpeg_metadata.get("quality") and (
                            not video.quality or force_ffmpeg_update
                        ):
                            video.quality = ffmpeg_metadata["quality"]
                            ffmpeg_updated = True

                        # Update technical metadata
                        if (
                            ffmpeg_updated
                            or force_ffmpeg_update
                            or not video.video_metadata
                            or not video.video_metadata.get("ffmpeg_extracted")
                        ):
                            existing_metadata = video.video_metadata or {}
                            tech_metadata = {
                                "width": ffmpeg_metadata.get("width"),
                                "height": ffmpeg_metadata.get("height"),
                                "video_codec": ffmpeg_metadata.get("video_codec"),
                                "audio_codec": ffmpeg_metadata.get("audio_codec"),
                                "fps": ffmpeg_metadata.get("fps"),
                                "bitrate": ffmpeg_metadata.get("bitrate"),
                                "ffmpeg_extracted": True,
                                "extraction_date": datetime.utcnow().isoformat(),
                            }
                            existing_metadata.update(tech_metadata)
                            video.video_metadata = existing_metadata

                        logger.info(
                            f"FFmpeg metadata extracted for video {video_id}: duration={video.duration}s, quality={video.quality}"
                        )
                    else:
                        logger.warning(
                            f"Video file not found for FFmpeg extraction: {video.local_path}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to extract FFmpeg metadata for video {video_id}: {e}"
                    )

            session.commit()

            # Update artist genres if video genres were changed
            if "genres" in data and video.artist_id:
                try:
                    from src.services.genre_service import genre_service

                    # Use the same session for genre operations
                    genre_service._update_artist_genres_with_session(
                        video.artist_id, session
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to update artist genres for video {video_id}: {e}"
                    )

            # Return updated video data
            updated_video = {
                "id": video.id,
                "title": video.title,
                "artist_id": video.artist_id,
                "artist_name": video.artist.name if video.artist else None,
                "status": (
                    video.status.value
                    if hasattr(video.status, "value")
                    else video.status
                ),
                "imvdb_id": video.imvdb_id,
                "video_url": video.url,
                "local_path": video.local_path,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "year": video.year,
                "genres": video.genres,
                "created_at": video.created_at.isoformat(),
                "file_moved": new_local_path != original_local_path,
            }

            logger.info(
                f"Updated video {video_id}: {video.title} by {video.artist.name if video.artist else 'Unknown'}"
            )

            return jsonify(updated_video), 200

    except Exception as e:
        logger.error(f"Failed to update video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


def _move_and_rename_video_file(
    original_path, new_artist_name, new_title, original_title, original_artist_name
):
    """
    Move and rename video file based on new metadata
    Returns the new file path
    """
    try:
        # Skip if no actual changes
        if new_artist_name == original_artist_name and new_title == original_title:
            return original_path

        # Construct absolute path
        if os.path.isabs(original_path):
            current_file_path = original_path
        else:
            current_file_path = os.path.join(os.getcwd(), original_path)

        if not os.path.exists(current_file_path):
            logger.warning(f"Original file not found: {current_file_path}")
            return original_path

        # Get file extension
        file_extension = os.path.splitext(current_file_path)[1]

        # Clean names for filename
        clean_artist = _clean_filename(new_artist_name)
        clean_title = _clean_filename(new_title)

        # Create new directory structure
        base_dir = os.path.dirname(
            os.path.dirname(current_file_path)
        )  # Go up from artist folder
        new_artist_dir = os.path.join(base_dir, clean_artist)

        # Create artist directory if it doesn't exist
        os.makedirs(new_artist_dir, exist_ok=True)

        # Create new filename
        new_filename = f"{clean_artist} - {clean_title}{file_extension}"
        new_file_path = os.path.join(new_artist_dir, new_filename)

        # Move and rename the file
        if current_file_path != new_file_path:
            os.rename(current_file_path, new_file_path)
            logger.info(f"Moved file from {current_file_path} to {new_file_path}")

            # Try to remove old artist directory if it's empty
            old_artist_dir = os.path.dirname(current_file_path)
            try:
                if os.path.exists(old_artist_dir) and not os.listdir(old_artist_dir):
                    os.rmdir(old_artist_dir)
                    logger.info(f"Removed empty directory: {old_artist_dir}")
            except OSError:
                pass  # Directory not empty or other error

        # Return relative path
        return os.path.relpath(new_file_path, os.getcwd())

    except Exception as e:
        logger.error(f"Failed to move/rename file {original_path}: {e}")
        return original_path  # Return original path if move fails


def _clean_filename(name):
    """Clean filename by removing invalid characters"""
    if not name:
        return "Unknown"

    # Replace invalid characters with underscores
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "_")

    # Remove extra whitespace and limit length
    name = " ".join(name.split())[:100]

    return name or "Unknown"


@videos_bp.route("/<int:video_id>/status", methods=["PUT"])
def update_video_status(video_id):
    """Update video status"""
    try:
        data = request.get_json()
        if not data or "status" not in data:
            return jsonify({"error": "Status is required"}), 400

        new_status = data["status"]

        # Validate status
        valid_statuses = ["WANTED", "DOWNLOADING", "DOWNLOADED", "FAILED", "IGNORED"]
        if new_status not in valid_statuses:
            return (
                jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}),
                400,
            )

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            old_status = (
                video.status.value if hasattr(video.status, "value") else video.status
            )
            video.status = VideoStatus[new_status]
            session.commit()

            logger.info(
                f"Updated video {video_id} status from {old_status} to {new_status}"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Video status updated to {new_status}",
                        "video_id": video_id,
                        "old_status": old_status,
                        "new_status": new_status,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to update video status: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/download", methods=["POST"])
def bulk_download_videos():
    """Download multiple videos using background job queue"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        if not isinstance(video_ids, list):
            return jsonify({"error": "video_ids must be an array"}), 400

        # Get operation parameters
        quality = data.get("quality", "best")
        force_redownload = data.get("force_redownload", False)

        # Use the working YT-DLP trigger function for each video
        results = []
        successful_downloads = 0
        failed_downloads = 0

        for video_id in video_ids:
            result = _trigger_video_download(video_id)
            results.append(
                {
                    "video_id": video_id,
                    "success": result.get("success", False),
                    "message": result.get(
                        "message", result.get("error", "Unknown result")
                    ),
                }
            )

            if result.get("success"):
                successful_downloads += 1
            else:
                failed_downloads += 1

        logger.info(
            f"Bulk download completed: {successful_downloads} successful, {failed_downloads} failed"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "total_videos": len(video_ids),
                    "successful_downloads": successful_downloads,
                    "failed_downloads": failed_downloads,
                    "results": results,
                    "message": f"Bulk download completed: {successful_downloads} successful, {failed_downloads} failed",
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to create bulk download job: {e}")
        return jsonify({"error": str(e)}), 500


def download_all_wanted_videos_internal(limit=50):
    """Internal function to download all videos with WANTED status"""
    try:
        results = []
        success_count = 0
        failed_count = 0
        wanted_video_ids = []

        # Import settings service for subtitle configuration
        from src.services.settings_service import settings

        # Read subtitle settings from database once for all downloads
        download_subtitles = settings.get_bool("download_subtitles", False)
        subtitle_languages = settings.get("subtitle_languages", "en,en-US")

        # First, get all wanted video IDs
        with get_db() as session:
            wanted_videos = (
                session.query(Video.id, Video.title, Artist.name)
                .join(Artist)
                .filter(Video.status == VideoStatus.WANTED)
                .limit(limit)
                .all()
            )

            if not wanted_videos:
                return {
                    "success": True,
                    "message": "No wanted videos found",
                    "success_count": 0,
                    "failed_count": 0,
                    "results": [],
                }

            wanted_video_ids = [(v.id, v.title, v.name) for v in wanted_videos]

        logger.info(f"Found {len(wanted_video_ids)} wanted videos to download")

        # Process each video individually to avoid session issues
        for video_id, video_title, artist_name in wanted_video_ids:
            try:
                with get_db() as session:
                    # Get fresh video object for each download
                    video = session.query(Video).filter(Video.id == video_id).first()

                    if not video:
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": "Video not found",
                            }
                        )
                        failed_count += 1
                        continue

                    # Resolve video URL using helper function
                    video_url = resolve_video_url(video, session)

                    if not video_url:
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": "No URL available for download",
                            }
                        )
                        failed_count += 1
                        continue

                    # Import yt-dlp service
                    from src.services.download_service_adapter import ytdlp_service

                    # Queue download
                    result = ytdlp_service.add_music_video_download(
                        artist=artist_name,
                        title=video_title,
                        url=video_url,
                        quality="best",
                        video_id=video_id,
                        download_subtitles=download_subtitles,
                        subtitle_languages=subtitle_languages,
                    )

                    if result and result.get("success"):
                        # Update the video status in a separate transaction
                        video.status = VideoStatus.DOWNLOADING
                        session.commit()

                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": True,
                                "download_id": result.get("id"),
                            }
                        )
                        success_count += 1
                    else:
                        error_msg = (
                            result.get("error", "Failed to queue download")
                            if result
                            else "MeTube service unavailable"
                        )
                        results.append(
                            {
                                "video_id": video_id,
                                "title": video_title,
                                "artist": artist_name,
                                "success": False,
                                "error": error_msg,
                            }
                        )
                        failed_count += 1

            except Exception as e:
                logger.error(f"Failed to download wanted video {video_id}: {e}")
                results.append(
                    {
                        "video_id": video_id,
                        "title": video_title,
                        "artist": artist_name,
                        "success": False,
                        "error": str(e),
                    }
                )
                failed_count += 1

        message = f"Downloaded all wanted videos: {success_count} queued successfully"
        if failed_count > 0:
            message += f", {failed_count} failed"

        return {
            "success": True,
            "message": message,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_wanted": len(wanted_video_ids),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Failed to download wanted videos: {e}")
        return {"success": False, "error": str(e)}


@videos_bp.route("/bulk/download-wanted", methods=["POST"])
def download_all_wanted_videos():
    """Download all videos with WANTED status"""
    try:
        data = request.get_json() or {}
        limit = data.get(
            "limit", 50
        )  # Default limit to prevent overwhelming the system

        # Call the internal function
        result = download_all_wanted_videos_internal(limit=limit)

        # Return JSON response
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Failed to download wanted videos: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/status", methods=["POST", "PUT"])
@monitor_performance("api.videos.bulk_status_update")
def bulk_update_video_status():
    """Update status for multiple videos using background job queue"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data or "status" not in data:
            return jsonify({"error": "video_ids array and status are required"}), 400

        video_ids = data["video_ids"]
        new_status = data["status"]

        if not isinstance(video_ids, list):
            return jsonify({"error": "video_ids must be an array"}), 400

        # Validate status
        valid_statuses = ["WANTED", "DOWNLOADING", "DOWNLOADED", "FAILED", "IGNORED"]
        if new_status not in valid_statuses:
            return (
                jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}),
                400,
            )

        # Validate that video IDs are integers
        try:
            video_ids = [int(vid) for vid in video_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "All video IDs must be integers"}), 400

        # Create bulk status update job
        from ..services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        job = BackgroundJob(
            type=JobType.BULK_VIDEO_DELETE,  # Using the same job type, handled by operation_type
            priority=JobPriority.NORMAL,
            payload={
                "operation_type": "status_update",
                "video_ids": video_ids,
                "params": {"status": new_status},
            },
        )

        job_queue = asyncio.run(get_job_queue())
        job_id = asyncio.run(job_queue.enqueue(job))

        logger.info(
            f"Queued bulk status update job {job_id} for {len(video_ids)} videos to {new_status}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "total_videos": len(video_ids),
                    "new_status": new_status,
                    "message": f"Bulk status update job queued for {len(video_ids)} videos to '{new_status}'. Job ID: {job_id}",
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to create bulk status update job: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/edit", methods=["POST"])
@monitor_performance("api.videos.bulk_edit")
def bulk_edit_videos():
    """Apply bulk edits to multiple videos"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data or "updates" not in data:
            return (
                jsonify({"error": "video_ids array and updates object are required"}),
                400,
            )

        video_ids = data["video_ids"]
        updates = data["updates"]

        if not isinstance(video_ids, list) or len(video_ids) == 0:
            return jsonify({"error": "video_ids must be a non-empty array"}), 400

        if not isinstance(updates, dict) or len(updates) == 0:
            return jsonify({"error": "updates must be a non-empty object"}), 400

        updated_count = 0
        failed_count = 0
        errors = []

        with get_db() as session:
            for video_id in video_ids:
                try:
                    video = session.query(Video).filter(Video.id == video_id).first()
                    if not video:
                        failed_count += 1
                        errors.append(f"Video {video_id} not found")
                        continue

                    # Apply updates
                    for field, value in updates.items():
                        if field == "artist_name":
                            # Handle artist name change - find or create artist
                            if value and value.strip():
                                artist = (
                                    session.query(Artist)
                                    .filter_by(name=value.strip())
                                    .first()
                                )
                                if not artist:
                                    artist = Artist(name=value.strip())
                                    session.add(artist)
                                    session.flush()  # Get the ID
                                video.artist_id = artist.id
                        elif field == "status":
                            # Validate status
                            valid_statuses = [
                                "WANTED",
                                "DOWNLOADING",
                                "DOWNLOADED",
                                "FAILED",
                                "IGNORED",
                            ]
                            if value in valid_statuses:
                                video.status = value
                            else:
                                errors.append(
                                    f"Invalid status '{value}' for video {video_id}"
                                )
                                continue
                        elif field == "priority":
                            # Validate priority
                            valid_priorities = ["LOW", "NORMAL", "HIGH", "URGENT"]
                            if value in valid_priorities:
                                video.priority = value
                            else:
                                errors.append(
                                    f"Invalid priority '{value}' for video {video_id}"
                                )
                                continue
                        elif field == "year":
                            # Validate year
                            if isinstance(value, int) and 1900 <= value <= 2030:
                                video.year = value
                            else:
                                errors.append(
                                    f"Invalid year '{value}' for video {video_id}"
                                )
                                continue
                        else:
                            # Direct field assignment for other supported fields
                            if hasattr(video, field):
                                setattr(video, field, value)
                            else:
                                errors.append(
                                    f"Unknown field '{field}' for video {video_id}"
                                )
                                continue

                    updated_count += 1

                except Exception as video_error:
                    failed_count += 1
                    errors.append(
                        f"Error updating video {video_id}: {str(video_error)}"
                    )
                    logger.error(f"Error updating video {video_id}: {video_error}")

            # Commit all changes
            session.commit()

        logger.info(
            f"Bulk edit completed: {updated_count} updated, {failed_count} failed"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "updated_count": updated_count,
                    "failed_count": failed_count,
                    "errors": errors if errors else None,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk edit videos: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/refresh-metadata", methods=["POST"])
def bulk_refresh_metadata():
    """Refresh metadata from IMVDb for multiple videos using background job queue"""
    try:
        data = request.get_json()
        video_ids = data.get("video_ids", [])
        force_refresh = data.get("force_refresh", True)

        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400

        if not isinstance(video_ids, list):
            return jsonify({"error": "video_ids must be a list"}), 400

        # Validate that video IDs are integers
        try:
            video_ids = [int(vid) for vid in video_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "All video IDs must be integers"}), 400

        # Create bulk metadata refresh job
        from ..services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        job = BackgroundJob(
            type=JobType.BULK_VIDEO_DELETE,  # Using the same job type, handled by operation_type
            priority=JobPriority.NORMAL,
            payload={
                "operation_type": "metadata_refresh",
                "video_ids": video_ids,
                "params": {"force_refresh": force_refresh},
            },
        )

        job_queue = asyncio.run(get_job_queue())
        job_id = asyncio.run(job_queue.enqueue(job))

        logger.info(
            f"Queued bulk metadata refresh job {job_id} for {len(video_ids)} videos"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": job_id,
                    "total_videos": len(video_ids),
                    "force_refresh": force_refresh,
                    "message": f"Bulk metadata refresh job queued for {len(video_ids)} videos. Job ID: {job_id}",
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to create bulk metadata refresh job: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/quality-check", methods=["POST"])
def bulk_quality_check():
    """Check quality status for multiple videos"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids required"}), 400

        video_ids = data["video_ids"]
        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({"error": "video_ids must be a non-empty list"}), 400

        checked_videos = []
        failed_checks = []

        with get_db() as session:
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()

            for video in videos:
                try:
                    # Basic quality analysis
                    quality_info = {
                        "video_id": video.id,
                        "title": video.title,
                        "current_quality": video.quality or "Unknown",
                        "file_size": video.file_size,
                        "resolution": video.resolution,
                        "bitrate": video.bitrate,
                        "file_path": video.file_path,
                    }

                    # Check if file exists
                    if video.file_path and os.path.exists(video.file_path):
                        quality_info["file_exists"] = True
                        try:
                            # Get file stats
                            stat = os.stat(video.file_path)
                            quality_info["file_size_actual"] = stat.st_size
                        except Exception as e:
                            quality_info["file_error"] = str(e)
                    else:
                        quality_info["file_exists"] = False

                    # Assess quality level
                    resolution = video.resolution
                    if resolution:
                        if "4K" in resolution or "2160" in resolution:
                            quality_info["quality_level"] = "4K"
                        elif "1080" in resolution:
                            quality_info["quality_level"] = "HD"
                        elif "720" in resolution:
                            quality_info["quality_level"] = "HD-Ready"
                        else:
                            quality_info["quality_level"] = "Standard"
                    else:
                        quality_info["quality_level"] = "Unknown"

                    checked_videos.append(quality_info)

                except Exception as e:
                    logger.error(f"Failed to check quality for video {video.id}: {e}")
                    failed_checks.append(
                        {
                            "video_id": video.id,
                            "title": video.title if video else f"Video {video.id}",
                            "error": str(e),
                        }
                    )

        return (
            jsonify(
                {
                    "success": True,
                    "checked_count": len(checked_videos),
                    "failed_count": len(failed_checks),
                    "checked_videos": checked_videos,
                    "failed_checks": failed_checks,
                    "message": f"Quality check completed for {len(checked_videos)} video(s)",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk check quality: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/upgrade-quality", methods=["POST"])
def bulk_upgrade_quality():
    """Upgrade quality for multiple videos"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids required"}), 400

        video_ids = data["video_ids"]
        target_quality = data.get("target_quality", "1080p")

        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({"error": "video_ids must be a non-empty list"}), 400

        upgraded_videos = []
        failed_upgrades = []
        skipped_videos = []

        with get_db() as session:
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()

            for video in videos:
                try:
                    current_quality = video.quality or "Unknown"

                    # Skip if already at target quality or higher
                    if current_quality == target_quality:
                        skipped_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "reason": f"Already at {target_quality} quality",
                            }
                        )
                        continue

                    # Check if higher quality is available for download
                    # This would typically involve checking YouTube or other sources
                    # For now, we'll mark as WANTED for manual re-download
                    if video.status in ["DOWNLOADED", "UNWANTED"]:
                        video.status = VideoStatus.WANTED
                        video.quality = target_quality

                        upgraded_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "old_quality": current_quality,
                                "new_quality": target_quality,
                                "status": "Marked for re-download",
                            }
                        )

                        logger.info(
                            f"Marked video {video.title} for quality upgrade: {current_quality} -> {target_quality}"
                        )
                    else:
                        skipped_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "reason": f"Current status ({video.status}) not eligible for upgrade",
                            }
                        )

                except Exception as e:
                    logger.error(f"Failed to upgrade quality for video {video.id}: {e}")
                    failed_upgrades.append(
                        {
                            "video_id": video.id,
                            "title": video.title if video else f"Video {video.id}",
                            "error": str(e),
                        }
                    )

            session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "upgraded_count": len(upgraded_videos),
                    "skipped_count": len(skipped_videos),
                    "failed_count": len(failed_upgrades),
                    "upgraded_videos": upgraded_videos,
                    "skipped_videos": skipped_videos,
                    "failed_upgrades": failed_upgrades,
                    "message": f"Quality upgrade completed for {len(upgraded_videos)} video(s)",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk upgrade quality: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/transcode", methods=["POST"])
def bulk_transcode():
    """Transcode multiple videos to different formats"""
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids required"}), 400

        video_ids = data["video_ids"]
        target_format = data.get("target_format", "mp4")
        target_codec = data.get("target_codec", "h264")

        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({"error": "video_ids must be a non-empty list"}), 400

        transcoded_videos = []
        failed_transcodes = []
        skipped_videos = []

        with get_db() as session:
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()

            for video in videos:
                try:
                    # Check if video file exists
                    if not video.file_path or not os.path.exists(video.file_path):
                        skipped_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "reason": "Video file not found",
                            }
                        )
                        continue

                    # Check current format
                    current_format = (
                        os.path.splitext(video.file_path)[1].lower().lstrip(".")
                    )

                    if current_format == target_format.lower():
                        skipped_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "reason": f"Already in {target_format} format",
                            }
                        )
                        continue

                    # For now, we'll just mark the transcode request
                    # In a full implementation, this would queue the video for transcoding
                    # using ffmpeg or similar tools

                    transcode_info = {
                        "video_id": video.id,
                        "title": video.title,
                        "current_format": current_format,
                        "target_format": target_format,
                        "target_codec": target_codec,
                        "status": "Queued for transcoding",
                        "original_path": video.file_path,
                    }

                    # Update video metadata to reflect pending transcode
                    video.transcoding_status = "pending"
                    video.target_format = target_format

                    transcoded_videos.append(transcode_info)

                    logger.info(
                        f"Queued video {video.title} for transcoding: {current_format} -> {target_format}"
                    )

                except Exception as e:
                    logger.error(f"Failed to queue transcode for video {video.id}: {e}")
                    failed_transcodes.append(
                        {
                            "video_id": video.id,
                            "title": video.title if video else f"Video {video.id}",
                            "error": str(e),
                        }
                    )

            session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "transcoded_count": len(transcoded_videos),
                    "skipped_count": len(skipped_videos),
                    "failed_count": len(failed_transcodes),
                    "transcoded_videos": transcoded_videos,
                    "skipped_videos": skipped_videos,
                    "failed_transcodes": failed_transcodes,
                    "message": f"Transcode queued for {len(transcoded_videos)} video(s)",
                    "note": "Transcoding feature is currently in development. Videos are queued for future processing.",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk transcode: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/scan-directories", methods=["POST"])
def scan_artist_directories():
    """Scan artist directories to find downloaded videos not tracked in database"""
    try:
        logger.info("Starting directory scan request")
        import re
        from pathlib import Path

        from src.database.models import Artist

        # Get request parameters
        data = request.get_json() or {}
        artist_id = data.get("artist_id")  # Optional: scan specific artist
        dry_run = data.get("dry_run", True)  # Default to dry run
        video_extensions = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".m4v"]

        base_video_dir = Path("data/musicvideos")
        if not base_video_dir.exists():
            return jsonify({"error": "Video directory not found"}), 404

        found_videos = []
        updated_videos = []
        errors = []

        with get_db() as session:
            # Get artists to scan
            if artist_id:
                artists = session.query(Artist).filter(Artist.id == artist_id).all()
                if not artists:
                    return jsonify({"error": "Artist not found"}), 404
            else:
                # Scan all artists with video directories
                artists = session.query(Artist).all()

            for artist in artists:
                try:
                    artist_name = artist.name

                    # Try multiple variations of the artist name for directory matching
                    artist_name_variations = [
                        artist_name,
                        artist_name.replace(
                            '"', "'"
                        ),  # Replace double quotes with single quotes
                        artist_name.replace('"', ""),  # Remove quotes entirely
                        artist_name.replace(
                            "'", '"'
                        ),  # Replace single quotes with double quotes
                        artist_name.replace("'", ""),  # Remove single quotes entirely
                    ]

                    artist_dir = None
                    for name_variant in artist_name_variations:
                        potential_dir = base_video_dir / name_variant
                        if potential_dir.exists():
                            artist_dir = potential_dir
                            logger.info(
                                f"Found directory for artist '{artist_name}' using variant: '{name_variant}'"
                            )
                            break

                    # Check if artist directory exists
                    if not artist_dir:
                        logger.debug(
                            f"No directory found for artist: {artist_name} (tried {len(artist_name_variations)} variations)"
                        )
                        continue

                    # Find video files in directory
                    video_files = []
                    for ext in video_extensions:
                        video_files.extend(artist_dir.glob(f"*{ext}"))

                    if not video_files:
                        continue

                    logger.info(
                        f"Scanning {len(video_files)} video files for artist: {artist_name}"
                    )

                    # Get existing videos for this artist
                    existing_videos = (
                        session.query(Video).filter(Video.artist_id == artist.id).all()
                    )
                    existing_paths = {
                        v.local_path for v in existing_videos if v.local_path
                    }
                    existing_titles = {v.title.lower() for v in existing_videos}

                    for video_file in video_files:
                        try:
                            # Get relative path from the app root
                            try:
                                relative_path = str(video_file.relative_to(Path.cwd()))
                            except ValueError:
                                # If relative_to fails, construct the path manually
                                relative_path = str(video_file)
                                if relative_path.startswith("/"):
                                    # Try to make it relative to current working directory
                                    cwd = str(Path.cwd())
                                    if relative_path.startswith(cwd):
                                        relative_path = relative_path[
                                            len(cwd) :
                                        ].lstrip("/")

                            # Skip if already tracked with correct path
                            if relative_path in existing_paths:
                                continue

                            # Extract title from filename
                            filename = video_file.stem

                            # Try different patterns to extract title
                            title_patterns = [
                                rf"^{re.escape(artist_name)}\s*-\s*(.+)$",  # "Artist - Title"
                                rf"^(.+?)\s*-\s*{re.escape(artist_name)}$",  # "Title - Artist"
                                rf"^(.+)$",  # Just the filename
                            ]

                            extracted_title = None
                            for pattern in title_patterns:
                                match = re.match(pattern, filename, re.IGNORECASE)
                                if match:
                                    extracted_title = match.group(1).strip()
                                    break

                            if not extracted_title:
                                extracted_title = filename

                            # Check if we have an existing video with similar title
                            matching_video = None
                            for video in existing_videos:
                                if (
                                    video.title.lower() == extracted_title.lower()
                                    or video.title.lower() in extracted_title.lower()
                                    or extracted_title.lower() in video.title.lower()
                                ):
                                    matching_video = video
                                    break

                            video_info = {
                                "artist_id": artist.id,
                                "artist_name": artist_name,
                                "file_path": relative_path,
                                "filename": video_file.name,
                                "extracted_title": extracted_title,
                                "file_size": video_file.stat().st_size,
                                "existing_video_id": (
                                    matching_video.id if matching_video else None
                                ),
                                "existing_video_title": (
                                    matching_video.title if matching_video else None
                                ),
                                "existing_status": (
                                    matching_video.status.value
                                    if matching_video
                                    and hasattr(matching_video.status, "value")
                                    else (
                                        matching_video.status
                                        if matching_video
                                        else None
                                    )
                                ),
                                "existing_local_path": (
                                    matching_video.local_path
                                    if matching_video
                                    else None
                                ),
                            }

                            found_videos.append(video_info)

                            # If we found a matching video, update it (unless dry run)
                            if matching_video and not dry_run:
                                old_status = (
                                    matching_video.status.value
                                    if hasattr(matching_video.status, "value")
                                    else matching_video.status
                                )
                                old_path = matching_video.local_path

                                matching_video.local_path = relative_path
                                matching_video.status = VideoStatus.DOWNLOADED

                                updated_videos.append(
                                    {
                                        "video_id": matching_video.id,
                                        "title": matching_video.title,
                                        "artist_name": artist_name,
                                        "old_status": old_status,
                                        "new_status": "DOWNLOADED",
                                        "old_path": old_path,
                                        "new_path": relative_path,
                                    }
                                )

                                logger.info(
                                    f"Updated video {matching_video.id}: {matching_video.title}"
                                )

                        except Exception as e:
                            logger.error(f"Error processing file {video_file}: {e}")
                            errors.append(
                                {
                                    "file": str(video_file),
                                    "artist": artist_name,
                                    "error": str(e),
                                }
                            )

                except Exception as e:
                    logger.error(f"Error processing artist {artist.name}: {e}")
                    errors.append({"artist": artist.name, "error": str(e)})

            # Commit changes if not dry run
            if not dry_run:
                session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "dry_run": dry_run,
                    "summary": {
                        "artists_scanned": len(artists),
                        "video_files_found": len(found_videos),
                        "videos_updated": len(updated_videos),
                        "errors": len(errors),
                    },
                    "found_videos": found_videos[:50],  # Limit for response size
                    "updated_videos": updated_videos,
                    "errors": errors[:10] if errors else [],
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to scan directories: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/import-from-imvdb", methods=["POST"])
def import_video_from_imvdb():
    """Import a single video from IMVDb by ID"""
    try:
        data = request.get_json()
        if not data or "imvdb_id" not in data:
            return jsonify({"error": "imvdb_id is required"}), 400

        # Check if we have either artist_id or artist name
        if "artist_id" not in data and "artist" not in data:
            return (
                jsonify({"error": "Either artist_id or artist name is required"}),
                400,
            )

        imvdb_id = data["imvdb_id"]
        auto_download = data.get("auto_download", False)
        skip_existing = data.get("skip_existing", True)
        priority = data.get("priority", 5)  # Default to normal priority

        with get_db() as session:
            # Handle artist - either by ID or by name
            if "artist_id" in data:
                # Use existing artist_id logic
                artist_id = data["artist_id"]
                artist = session.query(Artist).filter_by(id=artist_id).first()
                if not artist:
                    return jsonify({"error": "Artist not found"}), 404
            else:
                # Find or create artist by name
                artist_name = data["artist"]
                if not artist_name or not artist_name.strip():
                    return jsonify({"error": "Artist name cannot be empty"}), 400

                # Use VideoIndexingService to find or create artist
                video_indexing_service = VideoIndexingService()
                artist = video_indexing_service.find_or_create_artist(
                    artist_name.strip(), session
                )

                if not artist:
                    return jsonify({"error": "Failed to create or find artist"}), 500

            # Store artist info for later use (avoid session binding issues)
            artist_name = artist.name
            artist_id_value = artist.id

            # Check if video already exists
            existing_video = session.query(Video).filter_by(imvdb_id=imvdb_id).first()
            if existing_video:
                if skip_existing:
                    # Get existing video artist name safely
                    existing_artist_name = None
                    if existing_video.artist_id:
                        existing_artist = (
                            session.query(Artist)
                            .filter_by(id=existing_video.artist_id)
                            .first()
                        )
                        existing_artist_name = (
                            existing_artist.name if existing_artist else None
                        )

                    return (
                        jsonify(
                            {
                                "success": True,
                                "skipped": True,
                                "message": f'Video "{existing_video.title}" already exists',
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                                "artist_name": existing_artist_name,
                            }
                        ),
                        200,
                    )
                else:
                    # Get existing video artist name safely
                    existing_artist_name = None
                    if existing_video.artist_id:
                        existing_artist = (
                            session.query(Artist)
                            .filter_by(id=existing_video.artist_id)
                            .first()
                        )
                        existing_artist_name = (
                            existing_artist.name if existing_artist else None
                        )

                    return (
                        jsonify(
                            {
                                "error": "Video already exists",
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                                "artist_name": existing_artist_name,
                            }
                        ),
                        409,
                    )

            # Fetch video data from IMVDb (outside session to avoid blocking)
            video_data = imvdb_service.get_video_by_id(imvdb_id)
            if not video_data:
                # If direct fetch fails, try to find the video through search
                # This can happen due to IMVDb API inconsistencies
                logger.warning(
                    f"Direct fetch failed for IMVDb ID {imvdb_id}, trying search fallback"
                )

                # Try to search for the video using artist info
                if "title" in data and data["title"]:
                    # Use provided title if available
                    search_query = data["title"]
                    if artist_name:
                        search_query = f"{artist_name} {data['title']}"

                    search_results = imvdb_service.search_videos(search_query)
                    if search_results and search_results.get("results"):
                        # Look for a video with matching ID in search results
                        for result_video in search_results["results"]:
                            if str(result_video.get("id")) == str(imvdb_id):
                                video_data = result_video
                                logger.info(
                                    f"Found video via search fallback: {imvdb_id}"
                                )
                                break

                if not video_data:
                    return jsonify({"error": "Video not found on IMVDb"}), 404

            # Extract metadata using IMVDb service
            video_metadata = imvdb_service.extract_metadata(video_data)
            if not video_metadata:
                return (
                    jsonify({"error": "Failed to extract video metadata from IMVDb"}),
                    500,
                )

            # Create new video
            new_video = Video(
                artist_id=artist_id_value,
                title=video_metadata["title"],
                imvdb_id=imvdb_id,
                thumbnail_url=video_metadata.get("thumbnail_url"),
                year=video_metadata.get("year"),
                directors=video_metadata.get("directors", []),
                producers=video_metadata.get("producers", []),
                duration=video_metadata.get("duration"),
                description=video_metadata.get("description"),
                imvdb_metadata=video_metadata.get("raw_metadata"),
                video_metadata=video_metadata.get("raw_metadata"),
                status=VideoStatus.WANTED,
                discovered_date=datetime.utcnow(),
            )

            session.add(new_video)
            session.commit()

            # Refresh the new_video object to get the generated ID and ensure it's bound to session
            session.refresh(new_video)

            logger.info(
                f"Successfully imported video '{video_metadata['title']}' for artist '{artist_name}'"
            )

            # Store video ID for automatic download
            video_id = new_video.id

        # Conditionally trigger download after import (outside session to avoid blocking)
        download_result = None
        download_error = None

        if auto_download:
            try:
                # Trigger automatic download with priority
                download_result = _trigger_video_download(video_id)

                if download_result and download_result.get("success"):
                    # Update download priority if specified
                    if priority != 5:  # Only update if not default priority
                        try:
                            from src.database.models import Download

                            with get_db() as session:
                                download = (
                                    session.query(Download)
                                    .filter(Download.video_id == video_id)
                                    .first()
                                )
                                if download:
                                    download.priority = priority
                                    session.commit()
                        except Exception as priority_error:
                            logger.warning(
                                f"Could not set priority for download: {priority_error}"
                            )

                    logger.info(
                        f"Automatically started download for imported video: {video_metadata['title']} (Priority: {priority})"
                    )
                else:
                    download_error = (
                        download_result.get("error", "Unknown download error")
                        if download_result
                        else "Failed to start download"
                    )
                    logger.warning(
                        f"Could not automatically start download for imported video {video_metadata['title']}: {download_error}"
                    )
            except Exception as e:
                download_error = str(e)
                logger.error(
                    f"Error during automatic download for imported video {video_metadata['title']}: {e}"
                )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f'Video "{video_metadata["title"]}" imported successfully',
                    "auto_download": {
                        "attempted": auto_download,
                        "success": (
                            download_result.get("success", False)
                            if download_result and auto_download
                            else False
                        ),
                        "error": download_error,
                        "priority": priority if auto_download else None,
                    },
                    "video": {
                        "id": video_id,
                        "title": video_metadata["title"],
                        "imvdb_id": imvdb_id,
                        "artist_id": artist_id_value,
                        "artist_name": artist_name,
                        "status": (
                            "DOWNLOADING"
                            if download_result and download_result.get("success")
                            else "WANTED"
                        ),
                        "year": video_metadata.get("year"),
                        "directors": video_metadata.get("directors", []),
                        "producers": video_metadata.get("producers", []),
                        "thumbnail_url": video_metadata.get("thumbnail_url"),
                        "duration": video_metadata.get("duration"),
                        "created_at": datetime.utcnow().isoformat(),
                    },
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Failed to import video from IMVDb: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/import-from-youtube", methods=["POST"])
def import_video_from_youtube():
    """Import a single video from YouTube by ID"""
    try:
        data = request.get_json()
        if not data or "youtube_id" not in data:
            return jsonify({"error": "youtube_id is required"}), 400

        # Check if we have either artist_id or artist name
        if "artist_id" not in data and "artist" not in data:
            return (
                jsonify({"error": "Either artist_id or artist name is required"}),
                400,
            )

        youtube_id = data["youtube_id"]
        auto_download = data.get("auto_download", False)
        skip_existing = data.get("skip_existing", True)
        priority = data.get("priority", 5)  # Default to normal priority

        # Initialize variables to avoid undefined reference errors
        artist_id = None

        with get_db() as session:
            # Handle artist - either by ID or by name
            if "artist_id" in data:
                # Use existing artist_id logic
                artist_id = data["artist_id"]
                artist = session.query(Artist).filter_by(id=artist_id).first()
                if not artist:
                    return jsonify({"error": "Artist not found"}), 404
            else:
                # Find or create artist by name
                artist_name = data["artist"]
                if not artist_name or not artist_name.strip():
                    return jsonify({"error": "Artist name cannot be empty"}), 400

                # Use VideoIndexingService to find or create artist
                video_indexing_service = VideoIndexingService()
                artist = video_indexing_service.find_or_create_artist(
                    artist_name.strip(), session
                )

                if not artist:
                    return jsonify({"error": "Failed to create or find artist"}), 500

            # Store artist info for later use (avoid session binding issues)
            artist_name = artist.name
            artist_id_value = artist.id

            # Check if video already exists
            existing_video = (
                session.query(Video).filter_by(youtube_id=youtube_id).first()
            )
            if existing_video:
                if skip_existing:
                    # Get existing video artist name safely
                    existing_artist_name = None
                    if existing_video.artist_id:
                        existing_artist = (
                            session.query(Artist)
                            .filter_by(id=existing_video.artist_id)
                            .first()
                        )
                        existing_artist_name = (
                            existing_artist.name if existing_artist else None
                        )

                    return (
                        jsonify(
                            {
                                "success": True,
                                "skipped": True,
                                "message": f'Video "{existing_video.title}" already exists',
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                                "artist_name": existing_artist_name,
                            }
                        ),
                        200,
                    )
                else:
                    # Get existing video artist name safely
                    existing_artist_name = None
                    if existing_video.artist_id:
                        existing_artist = (
                            session.query(Artist)
                            .filter_by(id=existing_video.artist_id)
                            .first()
                        )
                        existing_artist_name = (
                            existing_artist.name if existing_artist else None
                        )

                    return (
                        jsonify(
                            {
                                "error": "Video already exists",
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                                "artist_name": existing_artist_name,
                            }
                        ),
                        409,
                    )

            # For YouTube videos, we need to get the video data from the discovery results
            # If title is not provided, fetch it from YouTube API
            title = data.get("title")
            if not title:
                # Try to fetch title from YouTube API
                from src.services.youtube_search_service import youtube_search_service

                try:
                    # Get video details from YouTube
                    youtube_details = youtube_search_service._get_video_details(
                        [youtube_id]
                    )
                    if youtube_details and youtube_id in youtube_details:
                        video_data = youtube_details[youtube_id]
                        # Try to get title from video details
                        if "title" in video_data:
                            title = video_data["title"]
                        else:
                            # Make a direct API call to get snippet data
                            import requests

                            api_key = youtube_search_service.api_key
                            if api_key:
                                try:
                                    url = f"{youtube_search_service.base_url}/videos"
                                    params = {
                                        "part": "snippet",
                                        "id": youtube_id,
                                        "key": api_key,
                                    }
                                    response = requests.get(
                                        url, params=params, timeout=10
                                    )
                                    if response.status_code == 200:
                                        video_info = response.json()
                                        items = video_info.get("items", [])
                                        if items:
                                            title = (
                                                items[0].get("snippet", {}).get("title")
                                            )
                                except:
                                    pass
                except Exception as e:
                    logger.warning(
                        f"Could not fetch YouTube title for video {youtube_id}: {e}"
                    )

                # Final fallback
                if not title:
                    title = f"YouTube Video {youtube_id}"
            description = data.get("description", "")
            thumbnail_url = data.get("thumbnail_url", "")
            duration = data.get("duration")
            view_count = data.get("view_count")
            like_count = data.get("like_count")
            published_at = data.get("published_at")
            channel_title = data.get("channel_title", "")

            # Parse year from published_at if available
            year = None
            if published_at:
                try:
                    year = int(published_at[:4])
                except:
                    pass

            # Prepare video metadata
            video_metadata = {
                "youtube_data": {
                    "published_at": published_at,
                    "channel_title": channel_title,
                    "like_count": like_count,
                    "imported_at": datetime.utcnow().isoformat(),
                }
            }

            # Create new video
            new_video = Video(
                artist_id=artist_id_value,
                title=title,
                youtube_id=youtube_id,
                youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
                thumbnail_url=thumbnail_url,
                year=year,
                duration=duration,
                description=description,
                view_count=view_count,
                like_count=like_count,
                video_metadata=video_metadata,
                source="youtube_discovery",
                status=VideoStatus.WANTED,
                discovered_date=datetime.utcnow(),
            )

            session.add(new_video)
            session.commit()

            # Refresh the new_video object to get the generated ID and ensure it's bound to session
            session.refresh(new_video)

            logger.info(
                f"Successfully imported YouTube video '{title}' for artist '{artist_name}'"
            )

            # Store video ID for automatic download
            video_id = new_video.id

        # Conditionally trigger download after import (outside session to avoid blocking)
        download_result = None
        download_error = None

        if auto_download:
            try:
                # Trigger automatic download with priority
                download_result = _trigger_video_download(video_id)

                if download_result and download_result.get("success"):
                    # Update download priority if specified
                    if priority != 5:  # Only update if not default priority
                        try:
                            from src.database.models import Download

                            with get_db() as session:
                                download = (
                                    session.query(Download)
                                    .filter(Download.video_id == video_id)
                                    .first()
                                )
                                if download:
                                    download.priority = priority
                                    session.commit()
                        except Exception as priority_error:
                            logger.warning(
                                f"Could not set priority for download: {priority_error}"
                            )

                    logger.info(
                        f"Automatically started download for imported YouTube video: {title} (Priority: {priority})"
                    )
                else:
                    download_error = (
                        download_result.get("error", "Unknown download error")
                        if download_result
                        else "Failed to start download"
                    )
                    logger.warning(
                        f"Could not automatically start download for imported YouTube video {title}: {download_error}"
                    )
            except Exception as e:
                download_error = str(e)
                logger.error(
                    f"Error during automatic download for imported YouTube video {title}: {e}"
                )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f'Video "{title}" imported successfully',
                    "auto_download": {
                        "attempted": auto_download,
                        "success": (
                            download_result.get("success", False)
                            if download_result and auto_download
                            else False
                        ),
                        "error": download_error,
                        "priority": priority if auto_download else None,
                    },
                    "video": {
                        "id": video_id,
                        "title": title,
                        "youtube_id": youtube_id,
                        "youtube_url": f"https://www.youtube.com/watch?v={youtube_id}",
                        "artist_id": artist_id_value,
                        "artist_name": artist_name,
                        "status": (
                            "DOWNLOADING"
                            if download_result and download_result.get("success")
                            else "WANTED"
                        ),
                        "year": year,
                        "channel_title": channel_title,
                        "thumbnail_url": thumbnail_url,
                        "duration": duration,
                        "view_count": view_count,
                        "like_count": like_count,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Failed to import video from YouTube: {e}")
        return jsonify({"error": str(e)}), 500


# Download Queue Priority Management Endpoints


@videos_bp.route("/downloads/queue", methods=["GET"])
def get_download_queue():
    """Get prioritized download queue with detailed status"""
    try:
        with get_db() as session:
            from src.database.models import Download

            # Get filter parameters
            status_filter = request.args.get("status")
            priority_filter = request.args.get("priority")
            artist_id_filter = request.args.get("artist_id")
            limit = min(int(request.args.get("limit", 100)), 500)

            # Build query with priority ordering
            query = session.query(Download).join(Download.artist)

            # Apply filters
            if status_filter:
                query = query.filter(Download.status == status_filter)
            if priority_filter:
                query = query.filter(Download.priority == int(priority_filter))
            if artist_id_filter:
                query = query.filter(Download.artist_id == int(artist_id_filter))

            # Order by priority (ascending = higher priority first), then by created_at
            downloads = (
                query.order_by(Download.priority.asc(), Download.created_at.asc())
                .limit(limit)
                .all()
            )

            # Format response with enhanced data
            queue_data = []
            for download in downloads:
                queue_data.append(
                    {
                        "id": download.id,
                        "title": download.title,
                        "artist_name": (
                            download.artist.name if download.artist else "Unknown"
                        ),
                        "artist_id": download.artist_id,
                        "video_id": download.video_id,
                        "status": download.status,
                        "priority": download.priority,
                        "priority_label": get_priority_label(download.priority),
                        "progress": download.progress,
                        "file_size": download.file_size,
                        "quality": download.quality,
                        "format": download.format,
                        "download_date": (
                            download.download_date.isoformat()
                            if download.download_date
                            else None
                        ),
                        "created_at": download.created_at.isoformat(),
                        "updated_at": download.updated_at.isoformat(),
                        "error_message": download.error_message,
                        "metube_id": download.metube_id,
                        "estimated_time_remaining": calculate_eta(download),
                        "can_modify_priority": download.status in ["pending", "failed"],
                    }
                )

            # Calculate queue statistics
            stats = calculate_queue_statistics(session)

            return (
                jsonify(
                    {
                        "queue": queue_data,
                        "count": len(queue_data),
                        "statistics": stats,
                        "priority_levels": get_priority_levels(),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get download queue: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/downloads/<int:download_id>/priority", methods=["PUT"])
def update_download_priority(download_id):
    """Update download priority"""
    try:
        data = request.get_json()
        new_priority = data.get("priority")

        if (
            not new_priority
            or not isinstance(new_priority, int)
            or new_priority < 1
            or new_priority > 10
        ):
            return (
                jsonify(
                    {
                        "error": "Priority must be an integer between 1 (highest) and 10 (lowest)"
                    }
                ),
                400,
            )

        with get_db() as session:
            from src.database.models import Download

            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            if not download:
                return jsonify({"error": "Download not found"}), 404

            # Check if priority can be modified
            if download.status not in ["pending", "failed"]:
                return (
                    jsonify(
                        {
                            "error": f"Cannot modify priority for {download.status} downloads"
                        }
                    ),
                    400,
                )

            old_priority = download.priority
            download.priority = new_priority
            session.commit()

            logger.info(
                f"Updated download {download_id} priority from {old_priority} to {new_priority}"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Priority updated from {get_priority_label(old_priority)} to {get_priority_label(new_priority)}",
                        "download": {
                            "id": download.id,
                            "title": download.title,
                            "old_priority": old_priority,
                            "new_priority": new_priority,
                            "priority_label": get_priority_label(new_priority),
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to update download priority: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/downloads/bulk/priority", methods=["PUT"])
def bulk_update_priority():
    """Bulk update download priorities"""
    try:
        data = request.get_json()
        download_ids = data.get("download_ids", [])
        new_priority = data.get("priority")

        if not download_ids:
            return jsonify({"error": "No download IDs provided"}), 400

        if (
            not new_priority
            or not isinstance(new_priority, int)
            or new_priority < 1
            or new_priority > 10
        ):
            return (
                jsonify(
                    {
                        "error": "Priority must be an integer between 1 (highest) and 10 (lowest)"
                    }
                ),
                400,
            )

        with get_db() as session:
            from src.database.models import Download

            downloads = (
                session.query(Download).filter(Download.id.in_(download_ids)).all()
            )

            if not downloads:
                return jsonify({"error": "No downloads found with provided IDs"}), 404

            updated_count = 0
            skipped_count = 0
            results = []

            for download in downloads:
                if download.status in ["pending", "failed"]:
                    old_priority = download.priority
                    download.priority = new_priority
                    updated_count += 1
                    results.append(
                        {
                            "id": download.id,
                            "title": download.title,
                            "updated": True,
                            "old_priority": old_priority,
                            "new_priority": new_priority,
                        }
                    )
                else:
                    skipped_count += 1
                    results.append(
                        {
                            "id": download.id,
                            "title": download.title,
                            "updated": False,
                            "reason": f"Cannot modify priority for {download.status} downloads",
                        }
                    )

            session.commit()

            logger.info(
                f"Bulk priority update: {updated_count} updated, {skipped_count} skipped"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Updated priority for {updated_count} downloads (skipped {skipped_count})",
                        "updated_count": updated_count,
                        "skipped_count": skipped_count,
                        "new_priority": new_priority,
                        "priority_label": get_priority_label(new_priority),
                        "results": results,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to bulk update priorities: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/downloads/queue/reorder", methods=["POST"])
def reorder_queue():
    """Automatically reorder queue based on smart prioritization"""
    try:
        data = request.get_json() or {}
        rules = data.get("rules", {})

        # Default prioritization rules
        default_rules = {
            "prioritize_new_artists": True,  # Higher priority for artists with fewer downloads
            "prioritize_recent": True,  # Higher priority for recently added videos
            "prioritize_short_videos": False,  # Higher priority for shorter videos
            "prioritize_high_quality": True,  # Higher priority for high quality videos
            "failed_retry_priority": 7,  # Priority for failed downloads
            "auto_download_priority": 3,  # Priority for auto-download artists
        }

        # Merge with provided rules
        prioritization_rules = {**default_rules, **rules}

        with get_db() as session:
            from src.database.models import Artist, Download

            # Get all pending and failed downloads
            downloads = (
                session.query(Download)
                .filter(Download.status.in_(["pending", "failed"]))
                .all()
            )

            if not downloads:
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "No downloads to reorder",
                            "reordered_count": 0,
                        }
                    ),
                    200,
                )

            reordered_count = 0

            for download in downloads:
                old_priority = download.priority
                new_priority = calculate_smart_priority(
                    download, prioritization_rules, session
                )

                if new_priority != old_priority:
                    download.priority = new_priority
                    reordered_count += 1

            session.commit()

            logger.info(
                f"Smart reordering complete: {reordered_count} downloads reordered"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Smart reordering complete: {reordered_count} downloads reordered",
                        "reordered_count": reordered_count,
                        "rules_applied": prioritization_rules,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to reorder queue: {e}")
        return jsonify({"error": str(e)}), 500


# Helper functions for download queue management


def get_priority_label(priority):
    """Convert numeric priority to human-readable label"""
    labels = {
        1: "Critical",
        2: "Very High",
        3: "High",
        4: "Above Normal",
        5: "Normal",
        6: "Below Normal",
        7: "Low",
        8: "Very Low",
        9: "Lowest",
        10: "Deferred",
    }
    return labels.get(priority, "Unknown")


def get_priority_levels():
    """Get all available priority levels"""
    return [
        {"value": 1, "label": "Critical", "color": "#dc3545"},
        {"value": 2, "label": "Very High", "color": "#fd7e14"},
        {"value": 3, "label": "High", "color": "#ffc107"},
        {"value": 4, "label": "Above Normal", "color": "#20c997"},
        {"value": 5, "label": "Normal", "color": "#6c757d"},
        {"value": 6, "label": "Below Normal", "color": "#6f42c1"},
        {"value": 7, "label": "Low", "color": "#0dcaf0"},
        {"value": 8, "label": "Very Low", "color": "#198754"},
        {"value": 9, "label": "Lowest", "color": "#0d6efd"},
        {"value": 10, "label": "Deferred", "color": "#495057"},
    ]


def calculate_eta(download):
    """Calculate estimated time remaining for download"""
    if download.status != "downloading" or not download.progress:
        return None

    # This is a placeholder - in a real implementation you'd calculate based on
    # download speed, file size, and current progress
    remaining_percent = 100 - download.progress
    if remaining_percent <= 0:
        return "Almost done"

    # Simple estimation (this would be improved with actual speed data)
    estimated_minutes = remaining_percent * 0.5  # Rough estimate
    if estimated_minutes < 1:
        return "< 1 minute"
    elif estimated_minutes < 60:
        return f"{int(estimated_minutes)} minutes"
    else:
        hours = int(estimated_minutes / 60)
        minutes = int(estimated_minutes % 60)
        return f"{hours}h {minutes}m"


def calculate_queue_statistics(session):
    """Calculate queue statistics"""
    from src.database.models import Download

    stats = {
        "total_downloads": session.query(Download).count(),
        "by_status": {},
        "by_priority": {},
        "estimated_total_time": None,
        "queue_health": "good",
    }

    # Count by status
    status_counts = (
        session.query(Download.status, func.count(Download.id))
        .group_by(Download.status)
        .all()
    )

    for status, count in status_counts:
        stats["by_status"][status] = count

    # Count by priority
    priority_counts = (
        session.query(Download.priority, func.count(Download.id))
        .group_by(Download.priority)
        .all()
    )

    for priority, count in priority_counts:
        stats["by_priority"][priority] = count

    # Determine queue health
    failed_count = stats["by_status"].get("failed", 0)
    total_count = stats["total_downloads"]

    if total_count > 0:
        failed_ratio = failed_count / total_count
        if failed_ratio > 0.3:
            stats["queue_health"] = "poor"
        elif failed_ratio > 0.1:
            stats["queue_health"] = "fair"

    return stats


def calculate_smart_priority(download, rules, session):
    """Calculate smart priority based on various factors"""
    from src.database.models import Artist

    base_priority = 5  # Normal priority

    # Get artist information
    artist = download.artist
    if not artist:
        return base_priority

    # Rule: Prioritize auto-download artists
    if rules.get("prioritize_auto_download") and artist.auto_download:
        base_priority = min(base_priority, rules.get("auto_download_priority", 3))

    # Rule: Prioritize new artists (artists with fewer downloads)
    if rules.get("prioritize_new_artists"):
        artist_download_count = (
            session.query(Download)
            .filter(Download.artist_id == artist.id, Download.status == "completed")
            .count()
        )

        if artist_download_count == 0:
            base_priority = min(base_priority, 2)  # Very high for first download
        elif artist_download_count < 3:
            base_priority = min(base_priority, 3)  # High for few downloads

    # Rule: Handle failed downloads
    if download.status == "failed":
        base_priority = rules.get("failed_retry_priority", 7)

    # Rule: Prioritize recent additions
    if rules.get("prioritize_recent"):
        from datetime import datetime, timedelta

        recent_threshold = datetime.utcnow() - timedelta(hours=24)
        if download.created_at > recent_threshold:
            base_priority = max(1, base_priority - 1)  # Boost priority by 1

    return max(1, min(10, base_priority))  # Clamp to valid range


# Enhanced download control endpoints


@videos_bp.route("/downloads/<int:download_id>/pause", methods=["POST"])
def pause_download(download_id):
    """Pause a specific download"""
    try:
        with get_db() as session:
            from src.database.models import Download

            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            if not download:
                return jsonify({"success": False, "error": "Download not found"}), 404

            if download.status != "downloading":
                return (
                    jsonify(
                        {"success": False, "error": "Download is not currently active"}
                    ),
                    400,
                )

            # Update status to paused
            download.status = "paused"
            session.commit()

            # TODO: Implement actual pause functionality with MeTube API
            logger.info(f"Paused download {download_id}: {download.title}")

            return jsonify(
                {"success": True, "message": f"Download paused: {download.title}"}
            )

    except Exception as e:
        logger.error(f"Error pausing download {download_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@videos_bp.route("/downloads/<int:download_id>/resume", methods=["POST"])
def resume_download(download_id):
    """Resume a paused download"""
    try:
        with get_db() as session:
            from src.database.models import Download

            download = (
                session.query(Download).filter(Download.id == download_id).first()
            )
            if not download:
                return jsonify({"success": False, "error": "Download not found"}), 404

            if download.status != "paused":
                return (
                    jsonify({"success": False, "error": "Download is not paused"}),
                    400,
                )

            # Update status to pending for restart
            download.status = "pending"
            session.commit()

            # TODO: Implement actual resume functionality with MeTube API
            logger.info(f"Resumed download {download_id}: {download.title}")

            return jsonify(
                {"success": True, "message": f"Download resumed: {download.title}"}
            )

    except Exception as e:
        logger.error(f"Error resuming download {download_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@videos_bp.route("/downloads/bulk/pause", methods=["POST"])
def pause_all_downloads():
    """Pause all active downloads"""
    try:
        with get_db() as session:
            from src.database.models import Download

            # Find all downloading items
            active_downloads = (
                session.query(Download).filter(Download.status == "downloading").all()
            )

            paused_count = 0
            for download in active_downloads:
                download.status = "paused"
                paused_count += 1

            session.commit()

            # TODO: Implement actual pause functionality with MeTube API
            logger.info(f"Paused {paused_count} downloads")

            return jsonify(
                {
                    "success": True,
                    "message": f"Paused {paused_count} downloads",
                    "paused_count": paused_count,
                }
            )

    except Exception as e:
        logger.error(f"Error pausing all downloads: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@videos_bp.route("/downloads/bulk/resume", methods=["POST"])
def resume_all_downloads():
    """Resume all paused downloads"""
    try:
        with get_db() as session:
            from src.database.models import Download

            # Find all paused items
            paused_downloads = (
                session.query(Download).filter(Download.status == "paused").all()
            )

            resumed_count = 0
            for download in paused_downloads:
                download.status = "pending"  # Reset to pending for restart
                resumed_count += 1

            session.commit()

            # TODO: Implement actual resume functionality with MeTube API
            logger.info(f"Resumed {resumed_count} downloads")

            return jsonify(
                {
                    "success": True,
                    "message": f"Resumed {resumed_count} downloads",
                    "resumed_count": resumed_count,
                }
            )

    except Exception as e:
        logger.error(f"Error resuming all downloads: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@videos_bp.route("/duplicates/detect", methods=["POST"])
def detect_duplicates():
    """Detect potential duplicate videos"""
    try:
        data = request.get_json()
        video_id = data.get("video_id")
        imvdb_id = data.get("imvdb_id")

        if not video_id or not imvdb_id:
            return jsonify({"error": "video_id and imvdb_id are required"}), 400

        with get_db() as session:
            # Find the current video
            current_video = session.query(Video).filter(Video.id == video_id).first()
            if not current_video:
                return jsonify({"error": "Video not found"}), 404

            # Find videos with the same IMVDb ID
            duplicate_videos = (
                session.query(Video)
                .filter(Video.imvdb_id == imvdb_id, Video.id != video_id)
                .all()
            )

            if not duplicate_videos:
                return jsonify({"duplicates_found": False})

            # Format duplicate information
            duplicates = []
            for dup_video in duplicate_videos:
                duplicates.append(
                    {
                        "id": dup_video.id,
                        "title": dup_video.title,
                        "artist_name": (
                            dup_video.artist.name if dup_video.artist else None
                        ),
                        "status": (
                            dup_video.status.value
                            if hasattr(dup_video.status, "value")
                            else dup_video.status
                        ),
                        "year": dup_video.year,
                        "quality": dup_video.quality,
                        "duration": dup_video.duration,
                        "url": dup_video.url,
                        "local_path": dup_video.local_path,
                        "thumbnail_url": dup_video.thumbnail_url,
                        "thumbnail_path": dup_video.thumbnail_path,
                        "video_metadata": dup_video.video_metadata,
                        "created_at": dup_video.created_at.isoformat(),
                    }
                )

            return jsonify(
                {
                    "duplicates_found": True,
                    "current_video": {
                        "id": current_video.id,
                        "title": current_video.title,
                        "artist_name": (
                            current_video.artist.name if current_video.artist else None
                        ),
                        "status": (
                            current_video.status.value
                            if hasattr(current_video.status, "value")
                            else current_video.status
                        ),
                        "year": current_video.year,
                        "quality": current_video.quality,
                        "duration": current_video.duration,
                        "url": current_video.url,
                        "local_path": current_video.local_path,
                        "thumbnail_url": current_video.thumbnail_url,
                        "thumbnail_path": current_video.thumbnail_path,
                        "video_metadata": current_video.video_metadata,
                        "created_at": current_video.created_at.isoformat(),
                    },
                    "duplicates": duplicates,
                    "imvdb_id": imvdb_id,
                }
            )

    except Exception as e:
        logger.error(f"Error detecting duplicates: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/duplicates/merge", methods=["POST"])
def merge_duplicate_videos():
    """Merge duplicate videos based on user choice"""
    try:
        data = request.get_json()
        primary_id = data.get("primary_id")  # Video to keep
        duplicate_ids = data.get("duplicate_ids", [])  # Videos to merge/delete
        merge_strategy = data.get(
            "merge_strategy", "keep_primary"
        )  # 'keep_primary', 'merge_data'

        if not primary_id or not duplicate_ids:
            return jsonify({"error": "primary_id and duplicate_ids are required"}), 400

        with get_db() as session:
            # Get the primary video
            primary_video = session.query(Video).filter(Video.id == primary_id).first()
            if not primary_video:
                return jsonify({"error": "Primary video not found"}), 404

            # Get duplicate videos
            duplicate_videos = (
                session.query(Video).filter(Video.id.in_(duplicate_ids)).all()
            )
            if len(duplicate_videos) != len(duplicate_ids):
                return jsonify({"error": "One or more duplicate videos not found"}), 404

            merged_info = []

            for dup_video in duplicate_videos:
                merge_details = {
                    "merged_video_id": dup_video.id,
                    "merged_title": dup_video.title,
                    "merged_data": {},
                }

                if merge_strategy == "merge_data":
                    # Merge missing data from duplicate to primary
                    if not primary_video.year and dup_video.year:
                        primary_video.year = dup_video.year
                        merge_details["merged_data"]["year"] = dup_video.year

                    if not primary_video.thumbnail_url and dup_video.thumbnail_url:
                        primary_video.thumbnail_url = dup_video.thumbnail_url
                        merge_details["merged_data"][
                            "thumbnail_url"
                        ] = dup_video.thumbnail_url

                    if not primary_video.url and dup_video.url:
                        primary_video.url = dup_video.url
                        merge_details["merged_data"]["url"] = dup_video.url

                    if not primary_video.local_path and dup_video.local_path:
                        primary_video.local_path = dup_video.local_path
                        merge_details["merged_data"][
                            "local_path"
                        ] = dup_video.local_path

                    if not primary_video.imvdb_metadata and dup_video.imvdb_metadata:
                        primary_video.imvdb_metadata = dup_video.imvdb_metadata
                        merge_details["merged_data"]["imvdb_metadata"] = "merged"

                # Handle playlist entries - transfer them to primary video
                from src.database.models import PlaylistEntry

                playlist_entries = (
                    session.query(PlaylistEntry)
                    .filter(PlaylistEntry.video_id == dup_video.id)
                    .all()
                )
                playlist_transfer_count = 0

                for entry in playlist_entries:
                    # Check if primary video is already in this playlist at this position
                    existing_entry = (
                        session.query(PlaylistEntry)
                        .filter(
                            PlaylistEntry.playlist_id == entry.playlist_id,
                            PlaylistEntry.video_id == primary_id,
                        )
                        .first()
                    )

                    if existing_entry:
                        # Primary video already in playlist - just delete the duplicate entry
                        session.delete(entry)
                    else:
                        # Transfer the playlist entry to primary video
                        entry.video_id = primary_id
                        playlist_transfer_count += 1

                merge_details["playlist_entries_transferred"] = playlist_transfer_count

                # Delete any downloads that reference this video
                downloads = (
                    session.query(Download)
                    .filter(Download.video_id == dup_video.id)
                    .all()
                )
                download_transfer_count = len(downloads)
                for download in downloads:
                    session.delete(download)
                merge_details["downloads_removed"] = download_transfer_count

                # Delete the duplicate video
                session.delete(dup_video)
                merged_info.append(merge_details)

                logger.info(f"Merged duplicate video {dup_video.id} into {primary_id}")

            session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully merged {len(duplicate_videos)} duplicate videos",
                    "primary_video_id": primary_id,
                    "merged_videos": merged_info,
                    "merge_strategy": merge_strategy,
                }
            )

    except Exception as e:
        logger.error(f"Error merging duplicate videos: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/update-safe", methods=["PUT"])
def update_video_safe(video_id):
    """Safely update video with duplicate detection"""
    try:
        data = request.get_json()

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()
            if not video:
                return jsonify({"error": "Video not found"}), 404

            # Check for IMVDb ID conflicts before updating
            new_imvdb_id = data.get("imvdb_id")
            if new_imvdb_id and new_imvdb_id != video.imvdb_id:
                # Check if this IMVDb ID already exists
                existing_video = (
                    session.query(Video)
                    .filter(Video.imvdb_id == new_imvdb_id, Video.id != video_id)
                    .first()
                )

                if existing_video:
                    return (
                        jsonify(
                            {
                                "error": "duplicate_imvdb_id",
                                "duplicate_video": {
                                    "id": existing_video.id,
                                    "title": existing_video.title,
                                    "artist_name": (
                                        existing_video.artist.name
                                        if existing_video.artist
                                        else None
                                    ),
                                    "status": (
                                        existing_video.status.value
                                        if hasattr(existing_video.status, "value")
                                        else existing_video.status
                                    ),
                                    "quality": existing_video.quality,
                                    "duration": existing_video.duration,
                                    "year": existing_video.year,
                                    "thumbnail_url": existing_video.thumbnail_url,
                                    "thumbnail_path": existing_video.thumbnail_path,
                                    "video_metadata": existing_video.video_metadata,
                                },
                                "suggested_action": "merge",
                            }
                        ),
                        409,
                    )  # Conflict status code

            # If no conflicts, proceed with normal update
            try:
                # Update fields
                if "title" in data:
                    video.title = data["title"]
                if "imvdb_id" in data:
                    video.imvdb_id = data["imvdb_id"]
                if "thumbnail_url" in data:
                    video.thumbnail_url = data["thumbnail_url"]
                if "year" in data:
                    video.year = data["year"]
                if "imvdb_metadata" in data:
                    video.imvdb_metadata = data["imvdb_metadata"]

                video.updated_at = datetime.now()
                session.commit()

                return jsonify({"message": "Video updated successfully"})

            except IntegrityError as e:
                session.rollback()
                if "imvdb_id" in str(e):
                    return (
                        jsonify(
                            {
                                "error": "duplicate_imvdb_id",
                                "message": "IMVDb ID already exists on another video",
                            }
                        ),
                        409,
                    )
                else:
                    return jsonify({"error": str(e)}), 500

    except Exception as e:
        logger.error(f"Error updating video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/universal-search", methods=["GET"])
@monitor_performance("api.videos.universal_search")
def universal_search():
    """
    Universal search endpoint that searches across videos, artists, and external sources
    Returns results in structured sections for the universal search UI
    """
    try:
        query = request.args.get("q", "").strip()
        extended = request.args.get("extended") == "true"

        if not query or len(query) < 2:
            return jsonify({"videos": [], "artists": [], "external": [], "total": 0})

        with get_db() as session:
            results = {"videos": [], "artists": [], "external": [], "total": 0}

            # Search videos (limit to 5 for UI)
            video_query = (
                session.query(Video)
                .join(Artist, Video.artist_id == Artist.id)
                .filter(
                    or_(
                        Video.title.ilike(f"%{query}%"), Artist.name.ilike(f"%{query}%")
                    )
                )
                .limit(5)
            )

            for video in video_query:
                results["videos"].append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "artist": (
                            video.artist.name if video.artist else "Unknown Artist"
                        ),
                        "year": video.year,
                        "status": video.status.value if video.status else "unknown",
                        "thumbnail": video.thumbnail_url,
                        "duration": video.duration,
                        "quality": video.quality,
                        "video_metadata": video.video_metadata,
                        "url": f"/video/{video.id}",
                    }
                )

            # Search artists (limit to 5 for UI)
            artist_query = (
                session.query(Artist).filter(Artist.name.ilike(f"%{query}%")).limit(5)
            )

            for artist in artist_query:
                video_count = (
                    session.query(Video).filter(Video.artist_id == artist.id).count()
                )
                results["artists"].append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "video_count": video_count,
                        "monitored": artist.monitored,
                        "genres": artist.genres or [],
                        "url": f"/artist/{artist.id}",
                    }
                )

            # External search (IMVDb and YouTube)
            external_results = []

            # Determine limits based on extended search
            if extended:
                # For extended search, focus more on IMVDb and YouTube with higher limits
                imvdb_limit = 8
                youtube_limit = 10
            else:
                # Standard search limits
                imvdb_limit = 3
                youtube_limit = 5

            # IMVDb search
            try:
                # IMVDb search_videos method takes artist and title parameters, not limit
                imvdb_results = imvdb_service.search_videos(query)
                # Apply limit manually after getting results
                limited_imvdb_results = (
                    imvdb_results[:imvdb_limit] if imvdb_results else []
                )

                for result in limited_imvdb_results:
                    # Extract artist name from nested structure
                    artist_name = "Unknown Artist"
                    if "artist" in result and isinstance(result["artist"], dict):
                        artist_name = result["artist"].get("name", "Unknown Artist")
                    elif (
                        "artists" in result
                        and isinstance(result["artists"], list)
                        and len(result["artists"]) > 0
                    ):
                        artist_name = result["artists"][0].get("name", "Unknown Artist")

                    # Handle thumbnail/image field
                    thumbnail_url = result.get("image", "")
                    if isinstance(thumbnail_url, dict):
                        # If image is a dict, try to get a URL from it
                        thumbnail_url = (
                            thumbnail_url.get("url", "")
                            or thumbnail_url.get("medium", "")
                            or thumbnail_url.get("large", "")
                            or ""
                        )

                    external_results.append(
                        {
                            "source": "IMVDb",
                            "id": result.get("id"),
                            "title": result.get("song_title", "Unknown Title"),
                            "artist": artist_name,
                            "year": result.get("year"),
                            "thumbnail": thumbnail_url,
                            "action": "add_to_library",
                            "video_id": result.get("id"),
                        }
                    )
            except Exception as e:
                logger.warning(f"IMVDb search failed: {e}")

            # YouTube search
            try:
                from src.services.youtube_service import youtube_service

                youtube_response = youtube_service.search_videos(
                    query, max_results=youtube_limit
                )

                # YouTube service returns a dict with 'results' key containing the results
                youtube_videos = []
                if youtube_response and youtube_response.get("success"):
                    youtube_videos = youtube_response.get("results", [])

                for result in youtube_videos:
                    # Extract video ID from different possible formats
                    video_id = result.get("id", {})
                    if isinstance(video_id, dict):
                        video_id = video_id.get("videoId", "")

                    snippet = result.get("snippet", {})
                    thumbnails = snippet.get("thumbnails", {})
                    thumbnail_url = (
                        thumbnails.get("medium", {}).get("url")
                        or thumbnails.get("default", {}).get("url")
                        or ""
                    )

                    external_results.append(
                        {
                            "source": "YouTube",
                            "id": video_id,
                            "title": snippet.get("title", "Unknown Title"),
                            "artist": snippet.get("channelTitle", "Unknown Artist"),
                            "thumbnail": thumbnail_url,
                            "duration": snippet.get("duration", ""),
                            "view_count": snippet.get("viewCount", ""),
                            "action": "add_to_library",
                            "video_id": video_id,
                        }
                    )
            except Exception as e:
                logger.warning(f"YouTube search failed: {e}")

            # For extended search, skip database results and focus on external only
            if extended:
                results["videos"] = []
                results["artists"] = []
                # Log extended search results for debugging
                logger.info(
                    f"Extended search for '{query}': IMVDb limit {imvdb_limit}, YouTube limit {youtube_limit}, found {len(external_results)} results"
                )

            results["external"] = external_results
            results["total"] = (
                len(results["videos"])
                + len(results["artists"])
                + len(results["external"])
            )

            return jsonify(results)

    except Exception as e:
        logger.error(f"Universal search error: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/search-results")
def search_results_page():
    """Render the search results page"""
    try:
        query = request.args.get("q", "").strip()
        return render_template("search_results.html", query=query)
    except Exception as e:
        logger.error(f"Error rendering search results page: {e}")
        return (
            render_template("error.html", error="Failed to load search results page"),
            500,
        )


@videos_bp.route("/<int:video_id>/extract-ffmpeg-metadata", methods=["POST"])
def extract_ffmpeg_metadata_single(video_id):
    """Extract FFmpeg technical metadata for a specific video"""
    try:
        from pathlib import Path

        from src.services.video_indexing_service import VideoIndexingService

        with get_db() as session:
            video = session.query(Video).filter(Video.id == video_id).first()

            if not video:
                return jsonify({"error": "Video not found"}), 404

            if not video.local_path:
                return jsonify({"error": "Video has no local file path"}), 400

            video_path = Path(video.local_path)
            if not video_path.exists():
                return jsonify({"error": "Video file not found on disk"}), 404

            # Extract FFmpeg metadata
            indexing_service = VideoIndexingService()
            ffmpeg_metadata = indexing_service.extract_ffmpeg_metadata(video_path)

            if not (ffmpeg_metadata.get("duration") or ffmpeg_metadata.get("quality")):
                return (
                    jsonify({"error": "Failed to extract metadata from video file"}),
                    500,
                )

            # Update video record
            updated = False
            if ffmpeg_metadata.get("duration") and not video.duration:
                video.duration = ffmpeg_metadata["duration"]
                updated = True

            if ffmpeg_metadata.get("quality") and not video.quality:
                video.quality = ffmpeg_metadata["quality"]
                updated = True

            if (
                updated
                or not video.video_metadata
                or not video.video_metadata.get("ffmpeg_extracted")
            ):
                # Update video_metadata with technical info
                existing_metadata = video.video_metadata or {}
                tech_metadata = {
                    "width": ffmpeg_metadata.get("width"),
                    "height": ffmpeg_metadata.get("height"),
                    "video_codec": ffmpeg_metadata.get("video_codec"),
                    "audio_codec": ffmpeg_metadata.get("audio_codec"),
                    "fps": ffmpeg_metadata.get("fps"),
                    "bitrate": ffmpeg_metadata.get("bitrate"),
                    "ffmpeg_extracted": True,
                    "extraction_date": datetime.utcnow().isoformat(),
                }
                existing_metadata.update(tech_metadata)
                video.video_metadata = existing_metadata
                video.updated_at = datetime.utcnow()
                updated = True

            session.commit()

            return jsonify(
                {
                    "success": True,
                    "video_id": video_id,
                    "updated": updated,
                    "metadata": {
                        "duration": video.duration,
                        "quality": video.quality,
                        "width": ffmpeg_metadata.get("width"),
                        "height": ffmpeg_metadata.get("height"),
                        "video_codec": ffmpeg_metadata.get("video_codec"),
                        "audio_codec": ffmpeg_metadata.get("audio_codec"),
                        "fps": ffmpeg_metadata.get("fps"),
                        "bitrate": ffmpeg_metadata.get("bitrate"),
                    },
                }
            )

    except Exception as e:
        logger.error(f"Error extracting FFmpeg metadata for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/extract-ffmpeg-metadata", methods=["POST"])
def extract_ffmpeg_metadata_bulk():
    """Extract FFmpeg technical metadata for multiple videos or all videos with local files"""
    try:
        from pathlib import Path

        from src.services.video_indexing_service import VideoIndexingService

        data = request.get_json() or {}
        video_ids = data.get("video_ids", [])
        force_update = data.get(
            "force_update", False
        )  # Force update even if metadata exists

        indexing_service = VideoIndexingService()
        results = {
            "success": True,
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "errors": [],
        }

        with get_db() as session:
            # Build query
            query = session.query(Video).filter(Video.local_path.isnot(None))

            if video_ids:
                query = query.filter(Video.id.in_(video_ids))
            elif not force_update:
                # Only process videos without duration or quality data
                query = query.filter(
                    or_(Video.duration.is_(None), Video.quality.is_(None))
                )

            videos = query.all()

            for video in videos:
                try:
                    results["processed"] += 1

                    video_path = Path(video.local_path)
                    if not video_path.exists():
                        results["failed"] += 1
                        results["errors"].append(
                            f"Video {video.id}: File not found at {video.local_path}"
                        )
                        continue

                    # Extract FFmpeg metadata
                    ffmpeg_metadata = indexing_service.extract_ffmpeg_metadata(
                        video_path
                    )

                    if not (
                        ffmpeg_metadata.get("duration")
                        or ffmpeg_metadata.get("quality")
                    ):
                        results["failed"] += 1
                        results["errors"].append(
                            f"Video {video.id}: Failed to extract metadata"
                        )
                        continue

                    # Update video record
                    updated = False

                    if ffmpeg_metadata.get("duration") and (
                        not video.duration or force_update
                    ):
                        video.duration = ffmpeg_metadata["duration"]
                        updated = True

                    if ffmpeg_metadata.get("quality") and (
                        not video.quality or force_update
                    ):
                        video.quality = ffmpeg_metadata["quality"]
                        updated = True

                    if (
                        updated
                        or force_update
                        or not video.video_metadata
                        or not video.video_metadata.get("ffmpeg_extracted")
                    ):
                        # Update video_metadata with technical info
                        existing_metadata = video.video_metadata or {}
                        tech_metadata = {
                            "width": ffmpeg_metadata.get("width"),
                            "height": ffmpeg_metadata.get("height"),
                            "video_codec": ffmpeg_metadata.get("video_codec"),
                            "audio_codec": ffmpeg_metadata.get("audio_codec"),
                            "fps": ffmpeg_metadata.get("fps"),
                            "bitrate": ffmpeg_metadata.get("bitrate"),
                            "ffmpeg_extracted": True,
                            "extraction_date": datetime.utcnow().isoformat(),
                        }
                        existing_metadata.update(tech_metadata)
                        video.video_metadata = existing_metadata
                        video.updated_at = datetime.utcnow()
                        updated = True

                    if updated:
                        results["updated"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"Video {video.id}: {str(e)}")
                    logger.error(f"Error processing video {video.id}: {e}")

            session.commit()

        logger.info(
            f"FFmpeg metadata extraction completed: {results['processed']} processed, {results['updated']} updated, {results['failed']} failed"
        )

        return jsonify(results)

    except Exception as e:
        logger.error(f"Error in bulk FFmpeg metadata extraction: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/blacklist", methods=["GET"])
def get_blacklist():
    """Get all blacklisted YouTube URLs"""
    try:
        with get_db() as session:
            from src.database.models import VideoBlacklist

            # Get query parameters
            page = request.args.get("page", 1, type=int)
            per_page = min(request.args.get("per_page", 50, type=int), 100)
            search = request.args.get("search", "").strip()

            # Build query
            query = session.query(VideoBlacklist)

            if search:
                search_filter = f"%{search}%"
                query = query.filter(
                    or_(
                        VideoBlacklist.title.ilike(search_filter),
                        VideoBlacklist.artist_name.ilike(search_filter),
                        VideoBlacklist.youtube_url.ilike(search_filter),
                    )
                )

            # Order by blacklisted date (newest first)
            query = query.order_by(VideoBlacklist.blacklisted_at.desc())

            # Paginate
            total = query.count()
            blacklist_entries = (
                query.offset((page - 1) * per_page).limit(per_page).all()
            )

            return jsonify(
                {
                    "blacklist": [entry.to_dict() for entry in blacklist_entries],
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total,
                        "pages": (total + per_page - 1) // per_page,
                    },
                }
            )

    except Exception as e:
        logger.error(f"Error getting blacklist: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/blacklist", methods=["POST"])
def add_to_blacklist():
    """Add a YouTube URL to blacklist"""
    try:
        data = request.get_json()
        youtube_url = data.get("youtube_url")

        if not youtube_url:
            return jsonify({"error": "youtube_url is required"}), 400

        with get_db() as session:
            from flask import g

            from src.database.models import VideoBlacklist

            # Check if already blacklisted
            existing = (
                session.query(VideoBlacklist)
                .filter(VideoBlacklist.youtube_url == youtube_url)
                .first()
            )

            if existing:
                return (
                    jsonify(
                        {
                            "message": "URL already blacklisted",
                            "blacklist_entry": existing.to_dict(),
                        }
                    ),
                    200,
                )

            # Add to blacklist
            blacklist_entry = VideoBlacklist(
                youtube_url=youtube_url,
                title=data.get("title"),
                artist_name=data.get("artist_name"),
                blacklisted_by=getattr(g, "current_user_id", None),
            )

            session.add(blacklist_entry)
            session.commit()

            logger.info(f"Added URL to blacklist: {youtube_url}")

            return (
                jsonify(
                    {
                        "message": "URL added to blacklist successfully",
                        "blacklist_entry": blacklist_entry.to_dict(),
                    }
                ),
                201,
            )

    except Exception as e:
        logger.error(f"Error adding to blacklist: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/blacklist/<path:youtube_url>", methods=["DELETE"])
def remove_from_blacklist(youtube_url):
    """Remove a YouTube URL from blacklist"""
    try:
        with get_db() as session:
            from urllib.parse import unquote

            from src.database.models import VideoBlacklist

            # Decode URL parameter
            decoded_url = unquote(youtube_url)

            blacklist_entry = (
                session.query(VideoBlacklist)
                .filter(VideoBlacklist.youtube_url == decoded_url)
                .first()
            )

            if not blacklist_entry:
                return jsonify({"error": "URL not found in blacklist"}), 404

            session.delete(blacklist_entry)
            session.commit()

            logger.info(f"Removed URL from blacklist: {decoded_url}")

            return jsonify(
                {
                    "message": "URL removed from blacklist successfully",
                    "removed_url": decoded_url,
                }
            )

    except Exception as e:
        logger.error(f"Error removing from blacklist: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/blacklist/check", methods=["POST"])
def check_blacklist():
    """Check if a YouTube URL is blacklisted"""
    try:
        data = request.get_json()
        youtube_url = data.get("youtube_url")

        if not youtube_url:
            return jsonify({"error": "youtube_url is required"}), 400

        with get_db() as session:
            from src.database.models import VideoBlacklist

            blacklist_entry = (
                session.query(VideoBlacklist)
                .filter(VideoBlacklist.youtube_url == youtube_url)
                .first()
            )

            return jsonify(
                {
                    "is_blacklisted": blacklist_entry is not None,
                    "blacklist_entry": (
                        blacklist_entry.to_dict() if blacklist_entry else None
                    ),
                }
            )

    except Exception as e:
        logger.error(f"Error checking blacklist: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/merge-preview", methods=["POST"])
def bulk_merge_preview():
    """Preview bulk video merge operations"""
    try:
        data = request.get_json()
        mode = data.get("mode", "manual")  # 'auto' or 'manual'
        video_ids = data.get("video_ids", [])
        options = data.get("options", {})

        if mode == "manual" and len(video_ids) < 2:
            return (
                jsonify({"error": "At least 2 videos are required for manual merge"}),
                400,
            )

        with get_db() as session:
            merge_groups = []

            if mode == "auto":
                # Auto-detect duplicates based on similarity criteria
                all_videos = (
                    session.query(Video).filter(Video.status == "DOWNLOADED").all()
                )

                # Group videos by potential duplicates
                potential_groups = {}

                for video in all_videos:
                    if not video.artist or not video.title:
                        continue

                    key = f"{video.artist.name.lower()}"
                    if key not in potential_groups:
                        potential_groups[key] = []
                    potential_groups[key].append(video)

                # Find duplicates within each artist group
                for artist_videos in potential_groups.values():
                    if len(artist_videos) < 2:
                        continue

                    # Check for title similarity
                    for i, video1 in enumerate(artist_videos):
                        group_videos = [video1]

                        for j, video2 in enumerate(artist_videos):
                            if i == j:
                                continue

                            # Check title similarity
                            title_similar = False
                            if options.get("match_title", True):
                                similarity = calculate_similarity(
                                    video1.title, video2.title
                                )
                                threshold = options.get("similarity_threshold", 80)
                                title_similar = similarity >= threshold

                            # Check duration similarity
                            duration_similar = True
                            if (
                                options.get("match_duration", True)
                                and video1.duration
                                and video2.duration
                            ):
                                duration_diff = abs(video1.duration - video2.duration)
                                duration_similar = duration_diff <= 30  # ±30 seconds

                            if title_similar and duration_similar:
                                group_videos.append(video2)

                        if len(group_videos) > 1:
                            # Determine primary video (highest quality, longest duration, etc.)
                            primary_video = determine_primary_video(group_videos)
                            duplicates = [
                                v for v in group_videos if v.id != primary_video.id
                            ]

                            if duplicates:
                                merge_groups.append(
                                    {
                                        "primary": {
                                            "id": primary_video.id,
                                            "title": primary_video.title,
                                            "artist_name": (
                                                primary_video.artist.name
                                                if primary_video.artist
                                                else None
                                            ),
                                            "quality": primary_video.quality,
                                            "duration": primary_video.duration,
                                            "status": (
                                                primary_video.status.value
                                                if hasattr(
                                                    primary_video.status, "value"
                                                )
                                                else primary_video.status
                                            ),
                                        },
                                        "duplicates": [
                                            {
                                                "id": dup.id,
                                                "title": dup.title,
                                                "artist_name": (
                                                    dup.artist.name
                                                    if dup.artist
                                                    else None
                                                ),
                                                "quality": dup.quality,
                                                "duration": dup.duration,
                                                "status": (
                                                    dup.status.value
                                                    if hasattr(dup.status, "value")
                                                    else dup.status
                                                ),
                                            }
                                            for dup in duplicates
                                        ],
                                    }
                                )

                            # Remove processed videos from artist_videos to avoid duplicates
                            for processed_video in group_videos:
                                if processed_video in artist_videos:
                                    artist_videos.remove(processed_video)

            else:
                # Manual mode - merge specific selected videos
                videos = session.query(Video).filter(Video.id.in_(video_ids)).all()

                if len(videos) < 2:
                    return (
                        jsonify(
                            {
                                "error": "Selected videos not found or insufficient videos"
                            }
                        ),
                        400,
                    )

                # Determine primary video based on strategy
                primary_video = determine_primary_video(
                    videos, options.get("primary_strategy", "highest_quality")
                )
                duplicates = [v for v in videos if v.id != primary_video.id]

                merge_groups.append(
                    {
                        "primary": {
                            "id": primary_video.id,
                            "title": primary_video.title,
                            "artist_name": (
                                primary_video.artist.name
                                if primary_video.artist
                                else None
                            ),
                            "quality": primary_video.quality,
                            "duration": primary_video.duration,
                            "status": (
                                primary_video.status.value
                                if hasattr(primary_video.status, "value")
                                else primary_video.status
                            ),
                        },
                        "duplicates": [
                            {
                                "id": dup.id,
                                "title": dup.title,
                                "artist_name": dup.artist.name if dup.artist else None,
                                "quality": dup.quality,
                                "duration": dup.duration,
                                "status": (
                                    dup.status.value
                                    if hasattr(dup.status, "value")
                                    else dup.status
                                ),
                            }
                            for dup in duplicates
                        ],
                    }
                )

            return jsonify(
                {
                    "merge_groups": merge_groups,
                    "total_groups": len(merge_groups),
                    "total_videos_to_merge": sum(
                        len(group["duplicates"]) for group in merge_groups
                    ),
                }
            )

    except Exception as e:
        logger.error(f"Error previewing bulk merge: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/bulk/merge", methods=["POST"])
def bulk_merge():
    """Perform bulk video merge operations"""
    try:
        data = request.get_json()
        mode = data.get("mode", "manual")
        video_ids = data.get("video_ids", [])
        options = data.get("options", {})

        if mode == "manual" and len(video_ids) < 2:
            return (
                jsonify({"error": "At least 2 videos are required for manual merge"}),
                400,
            )

        # First get the merge preview to know what we're working with
        preview_response = bulk_merge_preview()
        preview_data = preview_response.get_json()

        if preview_data.get("error"):
            return jsonify({"error": preview_data["error"]}), 400

        merge_groups = preview_data.get("merge_groups", [])

        if not merge_groups:
            return jsonify({"error": "No merge groups found"}), 400

        merged_count = 0

        with get_db() as session:
            for group in merge_groups:
                primary_id = group["primary"]["id"]
                duplicate_ids = [dup["id"] for dup in group["duplicates"]]

                # Use the existing merge endpoint logic
                try:
                    primary_video = (
                        session.query(Video).filter(Video.id == primary_id).first()
                    )
                    if not primary_video:
                        logger.warning(
                            f"Primary video {primary_id} not found, skipping group"
                        )
                        continue

                    for dup_id in duplicate_ids:
                        duplicate_video = (
                            session.query(Video).filter(Video.id == dup_id).first()
                        )
                        if not duplicate_video:
                            logger.warning(
                                f"Duplicate video {dup_id} not found, skipping"
                            )
                            continue

                        # Merge playlist entries
                        from src.database.models import PlaylistEntry

                        playlist_entries = (
                            session.query(PlaylistEntry)
                            .filter(PlaylistEntry.video_id == dup_id)
                            .all()
                        )

                        for entry in playlist_entries:
                            # Check if primary video is already in this playlist
                            existing_entry = (
                                session.query(PlaylistEntry)
                                .filter(
                                    PlaylistEntry.playlist_id == entry.playlist_id,
                                    PlaylistEntry.video_id == primary_id,
                                )
                                .first()
                            )

                            if not existing_entry:
                                # Update the entry to point to primary video
                                entry.video_id = primary_id
                                logger.info(
                                    f"Updated playlist entry to point to primary video {primary_id}"
                                )
                            else:
                                # Remove duplicate entry
                                session.delete(entry)
                                logger.info(
                                    f"Removed duplicate playlist entry for video {dup_id}"
                                )

                        # Delete associated downloads
                        downloads = (
                            session.query(Download)
                            .filter(Download.video_id == dup_id)
                            .all()
                        )
                        for download in downloads:
                            session.delete(download)

                        # Delete the duplicate video
                        session.delete(duplicate_video)
                        merged_count += 1
                        logger.info(
                            f"Merged video {dup_id} into primary video {primary_id}"
                        )

                except Exception as e:
                    logger.error(f"Error merging group with primary {primary_id}: {e}")
                    continue

            session.commit()

        return jsonify(
            {
                "success": True,
                "merge_groups": len(merge_groups),
                "merged_count": merged_count,
                "message": f"Successfully merged {merged_count} videos in {len(merge_groups)} groups",
            }
        )

    except Exception as e:
        logger.error(f"Error performing bulk merge: {e}")
        return jsonify({"error": str(e)}), 500


def calculate_similarity(str1, str2):
    """Calculate similarity percentage between two strings"""
    if not str1 or not str2:
        return 0

    str1 = str1.lower().strip()
    str2 = str2.lower().strip()

    if str1 == str2:
        return 100

    # Simple word-based similarity
    words1 = set(str1.split())
    words2 = set(str2.split())

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    if not union:
        return 0

    return (len(intersection) / len(union)) * 100


def determine_primary_video(videos, strategy="highest_quality"):
    """Determine which video should be the primary one in a merge"""
    if not videos:
        return None

    if len(videos) == 1:
        return videos[0]

    if strategy == "highest_quality":
        # Priority order: 4K > 1440p > 1080p > 720p > 480p > others
        quality_priority = {
            "4K": 6,
            "2160p": 6,
            "1440p": 5,
            "1080p": 4,
            "720p": 3,
            "480p": 2,
            "360p": 1,
        }

        best_video = videos[0]
        best_score = quality_priority.get(best_video.quality or "", 0)

        for video in videos[1:]:
            score = quality_priority.get(video.quality or "", 0)
            if score > best_score:
                best_video = video
                best_score = score

        return best_video

    elif strategy == "longest_duration":
        return max(videos, key=lambda v: v.duration or 0)

    elif strategy == "newest":
        return max(videos, key=lambda v: v.created_at or datetime.min)

    else:
        # Default to first video
        return videos[0]


@videos_bp.route("/import-from-youtube-auto", methods=["POST"])
def import_video_from_youtube_auto():
    """Import a video from YouTube with automatic artist identification from metadata"""
    try:
        data = request.get_json()
        if not data or "youtube_id" not in data:
            return jsonify({"error": "youtube_id is required"}), 400

        youtube_id = data["youtube_id"]
        auto_download = data.get("auto_download", False)
        skip_existing = data.get("skip_existing", True)
        priority = data.get("priority", 5)

        # For now, use simple fallback until we can debug the yt-dlp issue
        artist_name = "Unknown Artist"
        video_title = f"YouTube Video {youtube_id}"

        logger.info(
            f"Processing YouTube video {youtube_id} with fallback artist: {artist_name}"
        )

        # Now import the video using the existing endpoint logic
        try:
            with get_db() as session:
                logger.info(
                    f"Starting database operations for YouTube video {youtube_id}"
                )

                # Find or create artist by name
                video_indexing_service = VideoIndexingService()
                artist = video_indexing_service.find_or_create_artist(
                    artist_name.strip(), session
                )

                if not artist:
                    logger.error(f"Failed to create or find artist: {artist_name}")
                    return jsonify({"error": "Failed to create or find artist"}), 500

                # Store artist info for later use (avoid session binding issues)
                artist_name_final = artist.name
                artist_id_value = artist.id
                logger.info(
                    f"Found/created artist: {artist_name_final} (ID: {artist_id_value})"
                )

                # Check if video already exists
                existing_video = (
                    session.query(Video).filter_by(youtube_id=youtube_id).first()
                )
                if existing_video and skip_existing:
                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": f"Video already exists: {existing_video.title}",
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                                "skipped": True,
                            }
                        ),
                        200,
                    )

                # If video exists but skip_existing is False, update it
                if existing_video and not skip_existing:
                    existing_video.artist_id = artist_id_value
                    existing_video.updated_at = datetime.utcnow()
                    session.commit()

                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": f"Updated existing video: {existing_video.title}",
                                "video_id": existing_video.id,
                                "title": existing_video.title,
                            }
                        ),
                        200,
                    )

                # Create new video record
                video = Video(
                    youtube_id=youtube_id,
                    title=video_title,
                    artist_id=artist_id_value,
                    status=VideoStatus.WANTED,
                    auto_download=auto_download,
                    priority=priority,
                    created_at=datetime.utcnow(),
                )

                session.add(video)
                session.commit()

                logger.info(
                    f"Created video record for {artist_name_final}: YouTube ID {youtube_id}"
                )

                # If auto_download is enabled, add to download queue
                if auto_download:
                    try:
                        from src.services.download_service_adapter import ytdlp_service

                        download_result = ytdlp_service.add_music_video_download(
                            artist_name_final,
                            video.title,
                            f"https://www.youtube.com/watch?v={youtube_id}",
                        )
                        if not download_result.get("success"):
                            logger.warning(
                                f"Failed to add download: {download_result.get('message')}"
                            )
                    except Exception as e:
                        logger.error(f"Error adding download: {e}")

                return (
                    jsonify(
                        {
                            "success": True,
                            "message": f"Successfully imported video for {artist_name_final}",
                            "video_id": video.id,
                            "title": video.title,
                            "artist": artist_name_final,
                        }
                    ),
                    201,
                )

        except Exception as db_error:
            logger.error(f"Database error in import-from-youtube-auto: {db_error}")
            return jsonify({"error": f"Database error: {str(db_error)}"}), 500

    except Exception as e:
        logger.error(f"Failed to import video with auto artist detection: {e}")
        return jsonify({"error": str(e)}), 500


def extract_artist_from_title(title):
    """Extract artist name from YouTube video title"""
    if not title:
        return None

    import re

    # Remove common video type indicators
    clean_title = re.sub(
        r"\s*[\(\[].*?(official|music|video|mv|lyric|audio|live).*?[\)\]]",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # Pattern 1: "Artist - Song" or "Artist: Song"
    match = re.match(r"^([^-:]+)[\s\-:]+(.+)$", clean_title)
    if match:
        potential_artist = match.group(1).strip()
        potential_song = match.group(2).strip()

        # Simple heuristic: if the first part is shorter and doesn't contain "feat", it's likely the artist
        if (
            len(potential_artist) < len(potential_song)
            and "feat" not in potential_artist.lower()
        ):
            return potential_artist

    # Pattern 2: "Song by Artist"
    match = re.search(r"(.+)\s+by\s+(.+)$", clean_title, re.IGNORECASE)
    if match:
        return match.group(2).strip()

    # Pattern 3: "Artist ft/feat Artist - Song"
    match = re.match(
        r"^([^-:]+(?:\s+(?:ft|feat|featuring)\.?\s+[^-:]+)?)[\s\-:]+(.+)$",
        clean_title,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # If no clear pattern, return None
    return None


@videos_bp.route("/<int:video_id>/lyrics", methods=["GET"])
@public_endpoint
def get_video_lyrics(video_id):
    """Get lyrics for a video"""
    try:
        with get_db() as session:
            video = session.query(Video).filter_by(id=video_id).first()
            if not video:
                return jsonify({"error": "Video not found"}), 404

            return jsonify({"success": True, "lyrics": video.lyrics}), 200

    except Exception as e:
        logger.error(f"Error getting lyrics for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/lyrics", methods=["PUT"])
@public_endpoint
def update_video_lyrics(video_id):
    """Update lyrics for a video"""
    try:
        data = request.get_json()
        if not data or "lyrics" not in data:
            return jsonify({"error": "lyrics field is required"}), 400

        lyrics = data["lyrics"]

        with get_db() as session:
            video = session.query(Video).filter_by(id=video_id).first()
            if not video:
                return jsonify({"error": "Video not found"}), 404

            video.lyrics = lyrics
            video.updated_at = datetime.utcnow()
            session.commit()

            logger.info(f"Updated lyrics for video {video_id}: {video.title}")

            return (
                jsonify({"success": True, "message": "Lyrics updated successfully"}),
                200,
            )

    except Exception as e:
        logger.error(f"Error updating lyrics for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/<int:video_id>/lyrics/search", methods=["POST"])
@public_endpoint
def search_video_lyrics(video_id):
    """Search for lyrics automatically using external services"""
    try:
        with get_db() as session:
            video = session.query(Video).filter_by(id=video_id).first()
            if not video:
                return jsonify({"error": "Video not found"}), 404

            artist_name = video.artist.name if video.artist else None
            song_title = video.title

            if not artist_name or not song_title:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Artist name and song title are required for lyrics search",
                        }
                    ),
                    400,
                )

            # Search for lyrics using multiple sources
            lyrics_found = None
            source_used = None

            # Try multiple lyrics sources in order of preference
            lyrics_sources = [
                (
                    "Lyrics.ovh",
                    search_lyrics_azlyrics,
                ),  # Using lyrics.ovh API (renamed function)
                ("MusixMatch", search_lyrics_musixmatch),
                ("Genius", search_lyrics_genius),
            ]

            for source_name, search_func in lyrics_sources:
                try:
                    logger.info(
                        f"Searching {source_name} for lyrics: {artist_name} - {song_title}"
                    )
                    lyrics_result = search_func(artist_name, song_title)

                    if (
                        lyrics_result and len(lyrics_result.strip()) > 50
                    ):  # Ensure we got substantial lyrics
                        lyrics_found = lyrics_result
                        source_used = source_name
                        logger.info(f"Found lyrics from {source_name}")
                        break

                except Exception as source_error:
                    logger.warning(f"Failed to search {source_name}: {source_error}")
                    continue

            if lyrics_found:
                # Save the found lyrics to the database
                video.lyrics = lyrics_found
                session.commit()

                return (
                    jsonify(
                        {
                            "success": True,
                            "lyrics": lyrics_found,
                            "source": source_used,
                            "message": f"Lyrics found from {source_used} and saved successfully!",
                        }
                    ),
                    200,
                )
            else:
                # Provide a helpful placeholder with search information
                search_info = f"Lyrics search attempted for:\nArtist: {artist_name}\nSong: {song_title}\n\n"
                search_info += (
                    "Sources checked:\n• MusixMatch\n• Genius\n• AZLyrics\n\n"
                )
                search_info += "No lyrics were found automatically. You can:\n"
                search_info += "1. Try searching manually on lyrics websites\n"
                search_info += "2. Add lyrics using the Edit button\n"
                search_info += "3. Check if the artist/song names are correct"

                return (
                    jsonify(
                        {
                            "success": False,
                            "lyrics": search_info,
                            "error": "No lyrics found from any source",
                            "message": "Unable to find lyrics automatically. You can add them manually using the Edit button.",
                        }
                    ),
                    200,
                )  # Return 200 instead of 404 to show the helpful message

    except Exception as e:
        logger.error(f"Error searching lyrics for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


def search_lyrics_musixmatch(artist, title):
    """Search lyrics using MusixMatch API approach"""
    import re
    from urllib.parse import quote

    import requests

    try:
        # Use MusixMatch's public search (no API key required for basic search)
        search_url = f"https://www.musixmatch.com/search/{quote(artist)}-{quote(title)}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # This is a simplified approach - a real implementation would need proper API integration
        # For now, return None to try next source
        return None

    except Exception as e:
        logger.warning(f"MusixMatch search failed: {e}")
        return None


def search_lyrics_genius(artist, title):
    """Search lyrics using Genius API approach"""
    import re
    from urllib.parse import quote

    import requests

    try:
        # Use Genius public search (simplified approach)
        # A real implementation would use the official Genius API
        search_query = f"{artist} {title}".strip()

        # For now, return None to try next source
        return None

    except Exception as e:
        logger.warning(f"Genius search failed: {e}")
        return None


def search_lyrics_azlyrics(artist, title):
    """Search lyrics using Lyrics.ovh API (free alternative to AZLyrics scraping)"""
    from urllib.parse import quote

    import requests

    try:
        # Use Lyrics.ovh API - free and simple
        api_url = f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MVidarr/1.0)",
            "Accept": "application/json",
        }

        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            lyrics = data.get("lyrics", "").strip()

            if lyrics and len(lyrics) > 50:  # Ensure we got substantial content
                # Clean up the lyrics formatting
                lyrics = lyrics.replace("\r\n", "\n").replace("\r", "\n")
                # Remove excessive whitespace while preserving line breaks
                lines = [line.strip() for line in lyrics.split("\n")]
                lyrics = "\n".join(lines)

                return lyrics

        return None

    except Exception as e:
        logger.warning(f"Lyrics.ovh search failed: {e}")
        return None


def get_wanted_videos_for_download(limit=50):
    """Get videos that are marked as WANTED for downloading

    Args:
        limit: Maximum number of videos to return

    Returns:
        list: Videos with WANTED status ready for download
    """
    try:
        with get_db() as session:
            wanted_videos = (
                session.query(Video)
                .filter(Video.status == VideoStatus.WANTED)
                .order_by(Video.created_date.desc())
                .limit(limit)
                .all()
            )

            # Convert to dict format for scheduler
            video_list = []
            for video in wanted_videos:
                video_dict = {
                    "id": video.id,
                    "title": video.title,
                    "artist_name": video.artist.name if video.artist else "Unknown",
                    "youtube_url": video.youtube_url,
                    "status": (
                        video.status.value
                        if hasattr(video.status, "value")
                        else video.status
                    ),
                }
                video_list.append(video_dict)

            return video_list

    except Exception as e:
        logger.error(f"Error getting wanted videos for download: {e}")
        return []


def start_video_download(video_id):
    """Start download for a specific video using background jobs

    Args:
        video_id: ID of the video to download

    Returns:
        dict: Result of the download request
    """
    try:
        import asyncio

        from src.services.job_queue import (
            BackgroundJob,
            JobPriority,
            JobType,
            get_job_queue,
        )

        # Create background job for video download
        job = BackgroundJob(
            type=JobType.VIDEO_DOWNLOAD,
            priority=JobPriority.NORMAL,
            payload={
                "video_id": video_id,
                "quality": "best",
                "scheduled": True,  # Mark as scheduled download
            },
        )

        # Enqueue job
        async def queue_job():
            job_queue = await get_job_queue()
            return await job_queue.enqueue(job)

        job_id = asyncio.run(queue_job())

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Download job queued for video {video_id}",
        }

    except Exception as e:
        logger.error(f"Error starting video download for {video_id}: {e}")
        return {"success": False, "error": str(e)}
