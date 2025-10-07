"""
Artists API endpoints
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from src.database.connection import get_db
from src.database.models import Artist, Download, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.search_optimization_service import search_optimization_service
from src.services.settings_service import SettingsService
from src.services.thumbnail_service import thumbnail_service
from src.services.wikipedia_service import wikipedia_service
from src.services.youtube_search_service import youtube_search_service
from src.utils.logger import get_logger
from src.utils.performance_monitor import monitor_performance

artists_bp = Blueprint("artists", __name__, url_prefix="/artists")
logger = get_logger("mvidarr.api.artists")


def ensure_artist_folder_path(artist, session=None):
    """
    Ensure artist has a folder_path set. If missing, generate one.

    This addresses Issue #16 where artists (especially from YouTube imports)
    may not have folder paths set.
    """
    if not artist.folder_path or artist.folder_path.strip() == "":
        from src.utils.filename_cleanup import FilenameCleanup

        artist.folder_path = FilenameCleanup.sanitize_folder_name(artist.name)
        logger.info(
            f"Generated missing folder_path for artist '{artist.name}': '{artist.folder_path}'"
        )

        # If we have a session, commit the change immediately
        if session:
            try:
                session.commit()
                logger.info(f"Saved folder_path to database for artist '{artist.name}'")
            except Exception as e:
                logger.error(
                    f"Failed to save folder_path for artist '{artist.name}': {e}"
                )
                session.rollback()

    return artist.folder_path


@artists_bp.route("/", methods=["GET"])
@monitor_performance("api.artists.list")
def get_artists():
    """Get all tracked artists with search and filtering - OPTIMIZED"""
    import time

    start_time = time.time()

    try:
        with get_db() as session:
            # Use optimized query builder if available
            try:
                from src.database.performance_optimizations import (
                    DatabasePerformanceOptimizer,
                )

                optimizer = DatabasePerformanceOptimizer()
                query = optimizer.get_optimized_artist_video_counts(
                    session, monitored_only=False
                )

                # Convert to the expected format (Artist, video_count)
                results_raw = query.all()

            except ImportError:
                logger.warning(
                    "Performance optimizer not available, using fallback query"
                )
                # Fallback to optimized subquery approach
                video_count_subquery = (
                    session.query(
                        Video.artist_id, func.count(Video.id).label("video_count")
                    )
                    .filter(Video.status.in_(["DOWNLOADED", "WANTED", "DOWNLOADING"]))
                    .group_by(Video.artist_id)
                    .subquery()
                )

                query = (
                    session.query(Artist)
                    .outerjoin(
                        video_count_subquery,
                        Artist.id == video_count_subquery.c.artist_id,
                    )
                    .add_columns(
                        func.coalesce(video_count_subquery.c.video_count, 0).label(
                            "video_count"
                        )
                    )
                )
                results_raw = None

            # Apply filters to the query
            search_term = request.args.get("search", "").strip()
            monitored = request.args.get("monitored")
            auto_download = request.args.get("auto_download")
            has_thumbnail = request.args.get("has_thumbnail")
            has_imvdb_id = request.args.get("has_imvdb_id")
            genre = request.args.get("genre", "").strip()
            min_videos = request.args.get("min_videos")
            max_videos = request.args.get("max_videos")
            date_from = request.args.get("date_from")
            date_to = request.args.get("date_to")
            keywords = request.args.get("keywords", "").strip()

            # If using optimized query, we need to handle filters differently
            if results_raw is not None:
                # Apply filters to the results in memory (still efficient for reasonable dataset sizes)
                filtered_results = results_raw

                if search_term:
                    filtered_results = [
                        r
                        for r in filtered_results
                        if search_term.lower() in r[0].name.lower()
                    ]

                if monitored is not None:
                    monitored_bool = monitored.lower() in ["true", "1", "yes"]
                    filtered_results = [
                        r for r in filtered_results if r[0].monitored == monitored_bool
                    ]

                if auto_download is not None:
                    auto_download_bool = auto_download.lower() in ["true", "1", "yes"]
                    filtered_results = [
                        r
                        for r in filtered_results
                        if r[0].auto_download == auto_download_bool
                    ]

                if has_thumbnail is not None:
                    has_thumbnail_bool = has_thumbnail.lower() in ["true", "1", "yes"]
                    filtered_results = [
                        r
                        for r in filtered_results
                        if bool(r[0].thumbnail_url) == has_thumbnail_bool
                    ]

                if has_imvdb_id is not None:
                    has_imvdb_bool = has_imvdb_id.lower() in ["true", "1", "yes"]
                    filtered_results = [
                        r
                        for r in filtered_results
                        if bool(r[0].imvdb_id) == has_imvdb_bool
                    ]

                if genre:
                    filtered_results = [
                        r
                        for r in filtered_results
                        if r[0].genre and genre.lower() in r[0].genre.lower()
                    ]

                if min_videos and min_videos.strip():
                    try:
                        min_videos_int = int(min_videos)
                        filtered_results = [
                            r for r in filtered_results if r[1] >= min_videos_int
                        ]
                    except ValueError:
                        logger.warning(f"Invalid min_videos value: {min_videos}")

                if max_videos and max_videos.strip():
                    try:
                        max_videos_int = int(max_videos)
                        filtered_results = [
                            r for r in filtered_results if r[1] <= max_videos_int
                        ]
                    except ValueError:
                        logger.warning(f"Invalid max_videos value: {max_videos}")

                if date_from:
                    from datetime import datetime

                    date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
                    filtered_results = [
                        r
                        for r in filtered_results
                        if r[0].created_at
                        and r[0].created_at.date() >= date_from_dt.date()
                    ]

                if date_to:
                    from datetime import datetime

                    date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
                    filtered_results = [
                        r
                        for r in filtered_results
                        if r[0].created_at
                        and r[0].created_at.date() <= date_to_dt.date()
                    ]

                if keywords:
                    keyword_list = [
                        k.strip().lower() for k in keywords.split(",") if k.strip()
                    ]
                    filtered_results = [
                        r
                        for r in filtered_results
                        if any(
                            keyword in r[0].name.lower()
                            or (
                                r[0].keywords
                                and any(
                                    keyword in str(kw).lower() for kw in r[0].keywords
                                )
                            )
                            or (
                                r[0].genres
                                and any(
                                    keyword in str(genre).lower()
                                    for genre in r[0].genres
                                )
                            )
                            for keyword in keyword_list
                        )
                    ]

                results_raw = filtered_results
            else:
                # Apply filters to the query (fallback mode)
                if search_term:
                    query = query.filter(Artist.name.ilike(f"%{search_term}%"))

                if monitored is not None:
                    monitored_bool = monitored.lower() in ["true", "1", "yes"]
                    query = query.filter(Artist.monitored == monitored_bool)

                if auto_download is not None:
                    auto_download_bool = auto_download.lower() in ["true", "1", "yes"]
                    query = query.filter(Artist.auto_download == auto_download_bool)

                if has_thumbnail is not None:
                    has_thumbnail_bool = has_thumbnail.lower() in ["true", "1", "yes"]
                    if has_thumbnail_bool:
                        query = query.filter(Artist.thumbnail_url.isnot(None))
                    else:
                        query = query.filter(Artist.thumbnail_url.is_(None))

                if has_imvdb_id is not None:
                    has_imvdb_bool = has_imvdb_id.lower() in ["true", "1", "yes"]
                    if has_imvdb_bool:
                        query = query.filter(Artist.imvdb_id.isnot(None))
                    else:
                        query = query.filter(Artist.imvdb_id.is_(None))

                if genre:
                    query = query.filter(Artist.genre.ilike(f"%{genre}%"))

                if min_videos and min_videos.strip():
                    try:
                        min_videos_int = int(min_videos)
                        query = query.filter(
                            func.coalesce(video_count_subquery.c.video_count, 0)
                            >= min_videos_int
                        )
                    except ValueError:
                        logger.warning(f"Invalid min_videos value: {min_videos}")

                if max_videos and max_videos.strip():
                    try:
                        max_videos_int = int(max_videos)
                        query = query.filter(
                            func.coalesce(video_count_subquery.c.video_count, 0)
                            <= max_videos_int
                        )
                    except ValueError:
                        logger.warning(f"Invalid max_videos value: {max_videos}")

                if date_from:
                    from datetime import datetime

                    date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
                    query = query.filter(Artist.created_at >= date_from_dt)

                if date_to:
                    from datetime import datetime

                    date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
                    # Add one day to include the entire date_to day
                    date_to_dt = date_to_dt.replace(hour=23, minute=59, second=59)
                    query = query.filter(Artist.created_at <= date_to_dt)

                if keywords:
                    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
                    if keyword_list:  # Only apply filter if we have actual keywords
                        keyword_filters = []
                        for keyword in keyword_list:
                            keyword_filters.append(Artist.name.ilike(f"%{keyword}%"))
                            # Search in JSON keywords field
                            keyword_filters.append(Artist.keywords.contains(keyword))
                            # Search in JSON genres field
                            keyword_filters.append(Artist.genres.contains(keyword))
                        query = query.filter(or_(*keyword_filters))

            # Sorting
            sort_by = request.args.get("sort", "name")
            sort_order = request.args.get("order", "asc")

            if sort_by == "name":
                sort_column = Artist.name
            elif sort_by == "created_at":
                sort_column = Artist.created_at
            elif sort_by == "updated_at":
                sort_column = Artist.updated_at
            elif sort_by == "video_count":
                # For video_count, we need to use the subquery column
                sort_column = func.coalesce(video_count_subquery.c.video_count, 0)
            else:
                sort_column = Artist.name

            if sort_order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

            # Handle sorting and pagination
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 50))
            sort_by = request.args.get("sort", "name")
            sort_order = request.args.get("order", "asc")

            if results_raw is not None:
                # Handle sorting and pagination in memory for optimized query
                if sort_by == "name":
                    results_raw.sort(
                        key=lambda x: x[0].name.lower(),
                        reverse=(sort_order.lower() == "desc"),
                    )
                elif sort_by == "video_count":
                    results_raw.sort(
                        key=lambda x: x[1], reverse=(sort_order.lower() == "desc")
                    )
                elif sort_by == "created_at":
                    results_raw.sort(
                        key=lambda x: x[0].created_at,
                        reverse=(sort_order.lower() == "desc"),
                    )
                elif sort_by == "updated_at":
                    results_raw.sort(
                        key=lambda x: x[0].updated_at,
                        reverse=(sort_order.lower() == "desc"),
                    )

                total_count = len(results_raw)
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                results = results_raw[start_idx:end_idx]
            else:
                # Handle sorting and pagination in database (fallback mode)
                if sort_by == "name":
                    sort_column = Artist.name
                elif sort_by == "created_at":
                    sort_column = Artist.created_at
                elif sort_by == "updated_at":
                    sort_column = Artist.updated_at
                elif sort_by == "video_count":
                    sort_column = func.coalesce(video_count_subquery.c.video_count, 0)
                else:
                    sort_column = Artist.name

                if sort_order.lower() == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())

                total_count = query.count()
                results = query.offset((page - 1) * per_page).limit(per_page).all()

            artists_list = []
            for result in results:
                artist = result[0]  # Artist object
                video_count = result[1]  # video_count from subquery

                artists_list.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "imvdb_id": artist.imvdb_id,
                        "thumbnail_url": artist.thumbnail_url,
                        "auto_download": artist.auto_download,
                        "keywords": artist.keywords,
                        "monitored": artist.monitored,
                        "created_at": artist.created_at.isoformat(),
                        "video_count": video_count,
                        "folder_path": ensure_artist_folder_path(artist, session),
                        "has_thumbnail": bool(
                            artist.thumbnail_url or artist.thumbnail_path
                        ),
                        "has_imvdb_data": bool(artist.imvdb_id),
                    }
                )

            # Add performance monitoring
            query_time = time.time() - start_time
            logger.info(
                f"Artists query completed in {query_time:.3f}s (total: {total_count}, page: {page})"
            )

            return (
                jsonify(
                    {
                        "artists": artists_list,
                        "count": len(artists_list),
                        "total": total_count,
                        "page": page,
                        "per_page": per_page,
                        "pages": (total_count + per_page - 1) // per_page,
                        "query_time": query_time,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/search/advanced", methods=["GET"])
@monitor_performance("api.artists.advanced_search")
def advanced_search():
    """Advanced artist search with comprehensive filters and analytics - OPTIMIZED"""
    try:
        # Extract query parameters for caching
        query_params = {
            "search": request.args.get("search", "").strip(),
            "monitored": request.args.get("monitored"),
            "auto_download": request.args.get("auto_download"),
            "has_imvdb_id": request.args.get("has_imvdb_id"),
            "genre": request.args.get("genre", "").strip(),
            "min_videos": request.args.get("min_videos", type=int),
            "max_videos": request.args.get("max_videos", type=int),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "keywords": request.args.get("keywords", "").strip(),
            "sort": request.args.get("sort", "name"),
            "order": request.args.get("order", "asc"),
            "page": request.args.get("page", 1, type=int),
            "per_page": min(request.args.get("per_page", 50, type=int), 200),
        }

        # Use cached search if available
        def execute_search(params):
            return _execute_advanced_search(params)

        return search_optimization_service.cached_artist_search(
            query_params, execute_search
        )

    except Exception as e:
        logger.error(f"Failed to perform advanced search: {e}")
        return jsonify({"error": str(e)}), 500


def _execute_advanced_search(query_params):
    """Execute the actual advanced search query"""
    with get_db() as session:
        # Build base query with video count subquery - OPTIMIZED
        video_count_subquery = (
            session.query(Video.artist_id, func.count(Video.id).label("video_count"))
            .group_by(Video.artist_id)
            .subquery()
        )

        # Use optimized query with index hints
        query = (
            session.query(Artist)
            .outerjoin(
                video_count_subquery, Artist.id == video_count_subquery.c.artist_id
            )
            .add_columns(
                func.coalesce(video_count_subquery.c.video_count, 0).label(
                    "video_count"
                )
            )
        )

        # Text search - enhanced to search in multiple fields
        search_term = query_params.get("search", "").strip()
        if search_term:
            search_filters = []
            search_filters.append(Artist.name.ilike(f"%{search_term}%"))
            # For now, just search artist names since JSON syntax varies by database
            query = query.filter(or_(*search_filters))

        # Filter by monitoring status
        monitored = query_params.get("monitored")
        if monitored is not None:
            monitored_bool = monitored.lower() in ["true", "1", "yes"]
            query = query.filter(Artist.monitored == monitored_bool)

        # Filter by auto-download
        auto_download = query_params.get("auto_download")
        if auto_download is not None:
            auto_download_bool = auto_download.lower() in ["true", "1", "yes"]
            query = query.filter(Artist.auto_download == auto_download_bool)

        # Filter by presence of thumbnail
        has_thumbnail = query_params.get("has_thumbnail")
        if has_thumbnail is not None:
            has_thumbnail_bool = has_thumbnail.lower() in ["true", "1", "yes"]
            if has_thumbnail_bool:
                query = query.filter(
                    or_(
                        Artist.thumbnail_url.isnot(None),
                        Artist.thumbnail_path.isnot(None),
                    )
                )
            else:
                query = query.filter(
                    and_(
                        Artist.thumbnail_url.is_(None), Artist.thumbnail_path.is_(None)
                    )
                )

        # Filter by presence of IMVDb ID
        has_imvdb_id = query_params.get("has_imvdb_id")
        if has_imvdb_id is not None:
            has_imvdb_id_bool = has_imvdb_id.lower() in ["true", "1", "yes"]
            if has_imvdb_id_bool:
                query = query.filter(Artist.imvdb_id.isnot(None))
            else:
                query = query.filter(Artist.imvdb_id.is_(None))

        # Filter by genre
        genre = query_params.get("genre", "").strip()
        if genre:
            # Use JSON contains for genre filtering
            query = query.filter(Artist.genres.contains(f'"{genre}"'))

        # Filter by video count range - simplified to avoid HAVING clause issues
        min_videos = query_params.get("min_videos")
        max_videos = query_params.get("max_videos")
        # Skip video count filtering for now to avoid SQL issues
        # These filters will be implemented post-query

        # Filter by date range
        date_from = query_params.get("date_from")
        date_to = query_params.get("date_to")
        if date_from:
            try:
                date_from_obj = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                query = query.filter(Artist.created_at >= date_from_obj)
            except ValueError:
                pass
        if date_to:
            try:
                date_to_obj = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                query = query.filter(Artist.created_at <= date_to_obj)
            except ValueError:
                pass

        # Filter by keywords
        keywords = query_params.get("keywords", "").strip()
        if keywords:
            keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
            for keyword in keyword_list:
                query = query.filter(Artist.keywords.contains(keyword))

        # Advanced sorting options
        sort_by = query_params.get("sort", "name")
        sort_order = query_params.get("order", "asc")

        if sort_by == "name":
            sort_column = Artist.name
        elif sort_by == "created_at":
            sort_column = Artist.created_at
        elif sort_by == "updated_at":
            sort_column = Artist.updated_at
        elif sort_by == "video_count":
            sort_column = func.coalesce(video_count_subquery.c.video_count, 0)
        else:
            sort_column = Artist.name

        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)

        # Pagination with enhanced limits
        page = query_params.get("page", 1)
        per_page = query_params.get("per_page", 50)

        # Get total count before applying pagination
        total_count = query.count()

        # Apply pagination
        results = query.offset((page - 1) * per_page).limit(per_page).all()

        # Format results with enhanced metadata
        artists_list = []
        for artist, video_count in results:
            # Apply post-query video count filtering
            actual_video_count = video_count or 0
            if min_videos is not None and actual_video_count < min_videos:
                continue
            if max_videos is not None and actual_video_count > max_videos:
                continue

            artist_data = {
                "id": artist.id,
                "name": artist.name,
                "sort_name": artist.name,
                "imvdb_id": artist.imvdb_id,
                "thumbnail_url": artist.thumbnail_url,
                "thumbnail_path": artist.thumbnail_path,
                "auto_download": artist.auto_download,
                "keywords": artist.keywords or [],
                "monitored": artist.monitored,
                "folder_path": ensure_artist_folder_path(artist, session),
                "last_discovery": (
                    artist.last_discovery.isoformat() if artist.last_discovery else None
                ),
                "created_at": artist.created_at.isoformat(),
                "updated_at": artist.updated_at.isoformat(),
                "video_count": actual_video_count,
                "has_thumbnail": bool(artist.thumbnail_url or artist.thumbnail_path),
                "has_imvdb_data": bool(artist.imvdb_id),
                "imvdb_metadata": artist.imvdb_metadata,
            }
            artists_list.append(artist_data)

        # Calculate additional analytics
        analytics = {
            "total_artists": total_count,
            "page_count": (total_count + per_page - 1) // per_page,
            "has_next": page < (total_count + per_page - 1) // per_page,
            "has_prev": page > 1,
            "filters_applied": {
                "search": bool(search_term),
                "monitored": monitored is not None,
                "auto_download": auto_download is not None,
                "has_thumbnail": has_thumbnail is not None,
                "has_imvdb_id": has_imvdb_id is not None,
                "video_count_range": min_videos is not None or max_videos is not None,
                "date_range": date_from is not None or date_to is not None,
                "keywords": bool(keywords),
            },
        }

        return (
            jsonify(
                {
                    "artists": artists_list,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total_count,
                        "pages": analytics["page_count"],
                        "has_next": analytics["has_next"],
                        "has_prev": analytics["has_prev"],
                    },
                    "analytics": analytics,
                    "count": len(artists_list),
                }
            ),
            200,
        )


@artists_bp.route("/<int:artist_id>", methods=["GET"])
def get_artist(artist_id):
    """Get specific artist by ID"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Get video count for this artist
            video_count = session.query(Video).filter_by(artist_id=artist_id).count()

            # Safely serialize metadata
            metadata = None
            if artist.metadata:
                try:
                    # If metadata is already a dict, use it; if it's a JSON string, parse it
                    if isinstance(artist.metadata, str):
                        import json

                        metadata = json.loads(artist.metadata)
                    elif isinstance(artist.metadata, dict):
                        metadata = artist.metadata
                    else:
                        # For any other type (like SQLAlchemy objects), convert to string
                        metadata = str(artist.metadata)
                except Exception as meta_e:
                    logger.warning(
                        f"Failed to serialize metadata for artist {artist_id}: {meta_e}"
                    )
                    metadata = None

            # Safely serialize imvdb_metadata (where enrichment data is stored)
            imvdb_metadata = None
            if artist.imvdb_metadata:
                try:
                    # If imvdb_metadata is already a dict, use it; if it's a JSON string, parse it
                    if isinstance(artist.imvdb_metadata, str):
                        import json

                        imvdb_metadata = json.loads(artist.imvdb_metadata)
                    elif isinstance(artist.imvdb_metadata, dict):
                        imvdb_metadata = artist.imvdb_metadata
                    else:
                        # For any other type (like SQLAlchemy objects), convert to string
                        imvdb_metadata = str(artist.imvdb_metadata)
                except Exception as imvdb_e:
                    logger.warning(
                        f"Failed to serialize imvdb_metadata for artist {artist_id}: {imvdb_e}"
                    )
                    imvdb_metadata = None

            return (
                jsonify(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "imvdb_id": artist.imvdb_id,
                        "spotify_id": artist.spotify_id,
                        "lastfm_name": artist.lastfm_name,
                        "thumbnail_url": artist.thumbnail_url,
                        "auto_download": artist.auto_download,
                        "keywords": artist.keywords,
                        "monitored": artist.monitored,
                        "metadata": metadata,
                        "imvdb_metadata": imvdb_metadata,
                        "genres": artist.genres,
                        "overview": artist.overview,
                        "biography": getattr(artist, "biography", None),
                        "video_count": video_count,
                        "created_at": artist.created_at.isoformat(),
                        "updated_at": (
                            artist.updated_at.isoformat() if artist.updated_at else None
                        ),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/", methods=["POST"])
def add_artist():
    """Add new artist to tracking"""
    try:
        data = request.get_json()
        if not data or "name" not in data:
            return jsonify({"error": "Artist name is required"}), 400

        with get_db() as session:
            # Check if artist already exists
            existing = session.query(Artist).filter_by(name=data["name"]).first()
            if existing:
                return jsonify({"error": "Artist already exists"}), 409

            # Ensure empty strings are converted to None for unique constraints
            imvdb_id = data.get("imvdb_id")
            if imvdb_id == "":
                imvdb_id = None

            # Generate default folder path if not provided
            folder_path = data.get("folder_path")
            if not folder_path:
                from src.utils.filename_cleanup import FilenameCleanup

                folder_path = FilenameCleanup.sanitize_folder_name(data["name"])

            artist = Artist(
                name=data["name"],
                imvdb_id=imvdb_id,
                auto_download=data.get("auto_download", False),
                keywords=data.get("keywords", []),
                monitored=data.get("monitored", True),
                folder_path=folder_path,
            )

            session.add(artist)
            session.commit()

            artist_id = artist.id
            artist_name = artist.name

            # Run auto-match and metadata enrichment for newly added artist
            from src.services.artist_auto_processing_service import (
                artist_auto_processing_service,
            )

            # Refresh the artist instance to ensure it's bound to the session
            session.refresh(artist)
            auto_processing_results = artist_auto_processing_service.process_new_artist(
                artist, session
            )

            # Get a fresh artist instance after auto-processing to get metadata enrichment updates
            # Don't try to refresh the original object as it may have been invalidated by metadata enrichment
            fresh_artist = session.query(Artist).filter_by(id=artist_id).first()
            if fresh_artist:
                artist = fresh_artist

            return (
                jsonify(
                    {
                        "id": artist_id,
                        "name": artist_name,
                        "message": "Artist added successfully",
                        "auto_processing": auto_processing_results,
                    }
                ),
                201,
            )

    except Exception as e:
        logger.error(f"Failed to add artist: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/discover", methods=["GET"])
def discover_artists():
    """Discover artists from IMVDb by search term"""
    try:
        search_term = request.args.get("q", "").strip()
        if not search_term:
            return jsonify({"error": "Search term is required"}), 400

        limit = int(request.args.get("limit", 50))

        # Search IMVDb for artists
        results = imvdb_service.search_artists(search_term, limit=limit)

        if not results:
            return jsonify({"artists": [], "count": 0, "search_term": search_term}), 200

        # Format results for frontend
        artists_list = []
        for artist_data in results:
            # Extract name from slug if name is None
            name = artist_data.get("name")
            # Ensure name is a string if it exists (fix for integer name issue)
            if name:
                name = str(name)
            if not name and artist_data.get("slug"):
                # Convert slug to readable name (replace dashes with spaces, title case)
                slug = str(artist_data.get("slug"))
                name = slug.replace("-", " ").title()
            elif not name:
                # Skip artists without name or slug
                continue

            # Add all results but prioritize those with videos
            video_count = artist_data.get("artist_video_count", 0)
            # Extract thumbnail URL from image data
            thumbnail_url = None
            if artist_data.get("image"):
                if isinstance(artist_data["image"], dict):
                    thumbnail_url = (
                        artist_data["image"].get("l")
                        or artist_data["image"].get("m")
                        or artist_data["image"].get("s")
                        or artist_data["image"].get("t")
                    )
                elif isinstance(artist_data["image"], str):
                    thumbnail_url = artist_data["image"]

            # Enhanced metadata extraction
            artist_metadata = {
                "imvdb_id": artist_data.get("id"),
                "name": name,
                "slug": artist_data.get("slug"),
                "thumbnail_url": thumbnail_url,
                "biography": artist_data.get("bio"),
                "formed_year": artist_data.get("formed_year"),
                "origin_country": artist_data.get("origin_country"),
                "genres": artist_data.get("genres", []),
                "external_links": {
                    "imvdb_url": artist_data.get("url"),
                    "website": artist_data.get("website"),
                    "spotify": artist_data.get("spotify_url"),
                    "apple_music": artist_data.get("apple_music_url"),
                    "youtube": artist_data.get("youtube_url"),
                    "twitter": artist_data.get("twitter_url"),
                    "facebook": artist_data.get("facebook_url"),
                    "instagram": artist_data.get("instagram_url"),
                },
                "image": artist_data.get("image"),
                "video_count": video_count,
                "byline": artist_data.get("byline"),
                "popularity_score": artist_data.get("popularity_score", 0),
                "last_updated": artist_data.get("last_updated"),
                "verified": artist_data.get("verified", False),
                # Store raw metadata for future use
                "raw_metadata": artist_data,
            }

            artists_list.append(artist_metadata)

        # Sort by video count (artists with videos first) and then by name
        artists_list.sort(key=lambda x: (-x["video_count"], x["name"] or ""))

        return (
            jsonify(
                {
                    "artists": artists_list,
                    "count": len(artists_list),
                    "search_term": search_term,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to discover artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/import-from-imvdb", methods=["POST"])
def import_artist_from_imvdb():
    """Import artist directly from IMVDb with metadata"""
    try:
        data = request.get_json()
        if not data or "imvdb_id" not in data:
            return jsonify({"error": "IMVDb ID is required"}), 400

        imvdb_id = data["imvdb_id"]

        with get_db() as session:
            # Check if artist already exists
            existing = session.query(Artist).filter_by(imvdb_id=imvdb_id).first()
            if existing:
                return jsonify({"error": "Artist already exists"}), 409

            # Fetch detailed artist data from IMVDb
            artist_data = imvdb_service.get_artist(imvdb_id)
            if not artist_data:
                return (
                    jsonify(
                        {
                            "error": "Unable to retrieve artist from IMVDb. This could be due to an invalid ID or IMVDb service issues. Please try again later or verify the IMVDb ID."
                        }
                    ),
                    404,
                )

            # Skip IMVDb thumbnail extraction per user requirements
            # IMVDb should only be used for searching, not as a metadata or thumbnail source
            thumbnail_url = None

            # Extract and validate artist name - handle nested structures
            artist_name = None

            # Try multiple possible locations for the artist name
            name_candidates = [
                artist_data.get("name"),  # Direct name field
                (
                    artist_data.get("artist", {}).get("name")
                    if isinstance(artist_data.get("artist"), dict)
                    else None
                ),  # Nested in artist object
                (
                    artist_data.get("entity", {}).get("name")
                    if isinstance(artist_data.get("entity"), dict)
                    else None
                ),  # Nested in entity object
                (
                    artist_data.get("data", {}).get("name")
                    if isinstance(artist_data.get("data"), dict)
                    else None
                ),  # Nested in data object
            ]

            # Find the first non-empty name
            for candidate in name_candidates:
                if candidate:
                    artist_name = str(candidate).strip()
                    if artist_name:
                        break

            if not artist_name:
                # Try to extract from slug if name is not available
                slug_candidates = [
                    artist_data.get("slug"),
                    (
                        artist_data.get("artist", {}).get("slug")
                        if isinstance(artist_data.get("artist"), dict)
                        else None
                    ),
                    (
                        artist_data.get("entity", {}).get("slug")
                        if isinstance(artist_data.get("entity"), dict)
                        else None
                    ),
                ]

                for slug in slug_candidates:
                    if slug:
                        artist_name = str(slug).replace("-", " ").title()
                        break

                if not artist_name:
                    return (
                        jsonify(
                            {
                                "error": "Artist name not available from IMVDb data structure"
                            }
                        ),
                        400,
                    )

            # Generate default folder path
            from src.utils.filename_cleanup import FilenameCleanup

            folder_path = FilenameCleanup.sanitize_folder_name(artist_name)

            # Create new artist
            artist = Artist(
                name=artist_name,
                imvdb_id=imvdb_id,
                thumbnail_url=thumbnail_url,
                auto_download=data.get("auto_download", False),
                monitored=data.get("monitored", True),
                keywords=data.get("keywords", []),
                folder_path=folder_path,
            )

            session.add(artist)
            session.flush()  # Get the ID for auto-processing

            # Run auto-processing for newly imported artist
            try:
                from src.services.artist_auto_processing_service import (
                    artist_auto_processing_service,
                )

                # Ensure artist is bound to session for auto-processing
                session.refresh(artist)
                auto_processing_results = (
                    artist_auto_processing_service.process_new_artist(artist, session)
                )
                match_count = auto_processing_results.get("auto_match", {}).get(
                    "match_count", 0
                )
                logger.info(
                    f"Auto-processing completed for imported artist {artist_name} - {match_count} services matched"
                )

                # Get a fresh artist instance after auto-processing to get metadata enrichment updates
                # Don't try to refresh the original object as it may have been invalidated by metadata enrichment
                artist = session.query(Artist).filter_by(imvdb_id=imvdb_id).first()
                if not artist:
                    logger.error(
                        f"Could not find artist after auto-processing for IMVDb ID {imvdb_id}"
                    )
                    return jsonify({"error": "Artist lost during processing"}), 500

            except Exception as e:
                logger.error(
                    f"Auto-processing failed for imported artist {artist_name}: {e}"
                )
                logger.error(
                    f"Auto-processing traceback for {artist_name}:", exc_info=True
                )

            # Capture artist data before commits - artist should be fresh from query above
            artist_id = artist.id
            artist_name_final = artist.name
            artist_imvdb_id = artist.imvdb_id

            session.commit()

            # Download thumbnail if available
            if thumbnail_url:
                try:
                    # Refresh artist to ensure it's bound to session after commit
                    session.refresh(artist)
                    thumbnail_path = thumbnail_service.download_artist_thumbnail(
                        artist.name, thumbnail_url
                    )
                    if thumbnail_path:
                        artist.thumbnail_path = thumbnail_path
                        session.commit()
                except Exception as e:
                    logger.warning(
                        f"Failed to download thumbnail for {artist_name_final}: {e}"
                    )

            return (
                jsonify(
                    {
                        "artist_id": artist_id,
                        "id": artist_id,
                        "name": artist_name_final,
                        "imvdb_id": artist_imvdb_id,
                        "message": "Artist imported successfully",
                    }
                ),
                201,
            )

    except Exception as e:
        logger.error(f"Failed to import artist from IMVDb: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/preview/<imvdb_id>", methods=["GET"])
def get_artist_preview(imvdb_id):
    """Get detailed artist preview with videos from IMVDb"""
    try:
        # Get detailed artist data from IMVDb
        artist_data = imvdb_service.get_artist(imvdb_id)
        if not artist_data:
            return jsonify({"error": "Artist not found on IMVDb"}), 404

        # Get artist's videos from IMVDb
        artist_name = artist_data.get("name", "")
        videos_data = imvdb_service.search_artist_videos(
            artist_name, limit=50
        )  # Increased from 20 to improve discovery

        # Process video data
        videos_list = []
        if videos_data and videos_data.get("videos"):
            for video in videos_data["videos"]:
                video_metadata = imvdb_service.extract_metadata(video)
                videos_list.append(
                    {
                        "imvdb_id": video_metadata["imvdb_id"],
                        "title": video_metadata["title"],
                        "year": video_metadata["year"],
                        "directors": video_metadata["directors"],
                        "producers": video_metadata["producers"],
                        "thumbnail_url": video_metadata["thumbnail_url"],
                        "duration": video_metadata["duration"],
                        "genre": video_metadata["genre"],
                        "label": video_metadata["label"],
                        "album": video_metadata["album"],
                        "imvdb_url": video_metadata["imvdb_url"],
                    }
                )

        # Extract enhanced artist metadata
        thumbnail_url = None
        if artist_data.get("image"):
            if isinstance(artist_data["image"], dict):
                thumbnail_url = (
                    artist_data["image"].get("l")
                    or artist_data["image"].get("m")
                    or artist_data["image"].get("s")
                    or artist_data["image"].get("t")
                )
            elif isinstance(artist_data["image"], str):
                thumbnail_url = artist_data["image"]

        artist_preview = {
            "imvdb_id": artist_data.get("id"),
            "name": artist_data.get("name"),
            "slug": artist_data.get("slug"),
            "biography": artist_data.get("bio"),
            "formed_year": artist_data.get("formed_year"),
            "origin_country": artist_data.get("origin_country"),
            "genres": artist_data.get("genres", []),
            "thumbnail_url": thumbnail_url,
            "external_links": {
                "imvdb_url": artist_data.get("url"),
                "website": artist_data.get("website"),
                "spotify": artist_data.get("spotify_url"),
                "apple_music": artist_data.get("apple_music_url"),
                "youtube": artist_data.get("youtube_url"),
                "twitter": artist_data.get("twitter_url"),
                "facebook": artist_data.get("facebook_url"),
                "instagram": artist_data.get("instagram_url"),
            },
            "popularity_score": artist_data.get("popularity_score", 0),
            "verified": artist_data.get("verified", False),
            "videos": videos_list,
            "video_count": len(videos_list),
            "raw_metadata": artist_data,
        }

        return (
            jsonify(
                {
                    "artist": artist_preview,
                    "summary": {
                        "total_videos": len(videos_list),
                        "genres": artist_preview["genres"],
                        "has_biography": bool(artist_preview["biography"]),
                        "has_external_links": any(
                            artist_preview["external_links"].values()
                        ),
                        "verified": artist_preview["verified"],
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get artist preview for {imvdb_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-import", methods=["POST"])
def bulk_import_artists():
    """Import multiple artists from IMVDb in batch"""
    try:
        data = request.get_json()
        if not data or "artists" not in data:
            return jsonify({"error": "Artist list is required"}), 400

        artist_list = data["artists"]
        if not isinstance(artist_list, list) or len(artist_list) == 0:
            return jsonify({"error": "Artist list must be a non-empty array"}), 400

        if len(artist_list) > 50:  # Limit batch size
            return jsonify({"error": "Maximum 50 artists can be imported at once"}), 400

        results = {
            "successful": [],
            "failed": [],
            "skipped": [],
            "summary": {
                "total_requested": len(artist_list),
                "successful_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
            },
        }

        with get_db() as session:
            for artist_request in artist_list:
                try:
                    imvdb_id = artist_request.get("imvdb_id")
                    if not imvdb_id:
                        results["failed"].append(
                            {"artist": artist_request, "error": "IMVDb ID is required"}
                        )
                        continue

                    # Check if artist already exists
                    existing = (
                        session.query(Artist).filter_by(imvdb_id=imvdb_id).first()
                    )
                    if existing:
                        results["skipped"].append(
                            {
                                "artist": artist_request,
                                "reason": f'Artist "{existing.name}" already exists',
                                "existing_id": existing.id,
                            }
                        )
                        continue

                    # Fetch detailed artist data from IMVDb
                    artist_data = imvdb_service.get_artist(imvdb_id)
                    if not artist_data:
                        results["failed"].append(
                            {
                                "artist": artist_request,
                                "error": "Artist not found on IMVDb",
                            }
                        )
                        continue

                    # Extract and validate artist name
                    artist_name = artist_data.get("name")
                    # Ensure artist_name is a string if it exists (fix for integer name issue)
                    if artist_name:
                        artist_name = str(artist_name)
                    if not artist_name:
                        if artist_data.get("slug"):
                            slug = str(artist_data.get("slug"))
                            artist_name = slug.replace("-", " ").title()
                        else:
                            results["failed"].append(
                                {
                                    "artist": artist_request,
                                    "error": "Artist name not available from IMVDb",
                                }
                            )
                            continue

                    # Extract thumbnail URL
                    thumbnail_url = None
                    if artist_data.get("image"):
                        if isinstance(artist_data["image"], dict):
                            thumbnail_url = (
                                artist_data["image"].get("l")
                                or artist_data["image"].get("m")
                                or artist_data["image"].get("s")
                            )
                        elif isinstance(artist_data["image"], str):
                            thumbnail_url = artist_data["image"]

                    # Generate default folder path
                    from src.utils.filename_cleanup import FilenameCleanup

                    folder_path = FilenameCleanup.sanitize_folder_name(artist_name)

                    # Create new artist with enhanced metadata
                    artist = Artist(
                        name=artist_name,
                        imvdb_id=imvdb_id,
                        thumbnail_url=thumbnail_url,
                        auto_download=artist_request.get("auto_download", False),
                        monitored=artist_request.get("monitored", True),
                        keywords=artist_request.get("keywords", []),
                        imvdb_metadata=artist_data,  # Store full metadata
                        folder_path=folder_path,
                    )

                    session.add(artist)
                    session.flush()  # Get the ID without committing

                    # Download thumbnail if available
                    thumbnail_path = None
                    if thumbnail_url:
                        try:
                            thumbnail_path = (
                                thumbnail_service.download_artist_thumbnail(
                                    artist.name, thumbnail_url
                                )
                            )
                            if thumbnail_path:
                                artist.thumbnail_path = thumbnail_path
                        except Exception as e:
                            logger.warning(
                                f"Failed to download thumbnail for {artist.name}: {e}"
                            )

                    results["successful"].append(
                        {
                            "artist_id": artist.id,
                            "name": artist.name,
                            "imvdb_id": artist.imvdb_id,
                            "thumbnail_downloaded": bool(thumbnail_path),
                            "metadata_stored": bool(artist.imvdb_metadata),
                        }
                    )

                except Exception as e:
                    logger.error(f"Failed to import artist {artist_request}: {e}")
                    results["failed"].append(
                        {"artist": artist_request, "error": str(e)}
                    )
                    continue

            # Update summary counts
            results["summary"]["successful_count"] = len(results["successful"])
            results["summary"]["failed_count"] = len(results["failed"])
            results["summary"]["skipped_count"] = len(results["skipped"])

            # Only commit if we have successful imports
            if results["summary"]["successful_count"] > 0:
                session.commit()
                logger.info(
                    f"Bulk import completed: {results['summary']['successful_count']} successful, "
                    f"{results['summary']['failed_count']} failed, {results['summary']['skipped_count']} skipped"
                )
            else:
                session.rollback()
                logger.warning(
                    "Bulk import failed: no artists were successfully imported"
                )

            return jsonify(results), 200

    except Exception as e:
        logger.error(f"Failed to perform bulk import: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/detailed", methods=["GET"])
def get_artist_detailed(artist_id):
    """Get comprehensive artist details including videos and statistics"""
    try:
        with get_db() as session:
            # Get artist with video count
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Get all videos for this artist
            videos = session.query(Video).filter_by(artist_id=artist_id).all()

            # Calculate statistics
            stats = {
                "total_videos": len(videos),
                "downloaded_videos": len(
                    [v for v in videos if v.status == VideoStatus.DOWNLOADED]
                ),
                "wanted_videos": len(
                    [v for v in videos if v.status == VideoStatus.WANTED]
                ),
                "downloading_videos": len(
                    [v for v in videos if v.status == VideoStatus.DOWNLOADING]
                ),
                "failed_videos": len(
                    [v for v in videos if v.status == VideoStatus.FAILED]
                ),
                "ignored_videos": len(
                    [v for v in videos if v.status == VideoStatus.IGNORED]
                ),
                "monitored_videos": len(
                    [v for v in videos if v.status == VideoStatus.MONITORED]
                ),
                "latest_video_date": None,
                "earliest_video_date": None,
                "total_duration": 0,
                "average_duration": 0,
            }

            # Calculate date and duration statistics
            video_dates = [v.release_date for v in videos if v.release_date]
            if video_dates:
                stats["latest_video_date"] = max(video_dates).isoformat()
                stats["earliest_video_date"] = min(video_dates).isoformat()

            durations = [v.duration for v in videos if v.duration]
            if durations:
                stats["total_duration"] = sum(durations)
                stats["average_duration"] = stats["total_duration"] / len(durations)

            # Format videos data
            videos_list = []
            for video in videos:
                videos_list.append(
                    {
                        "id": video.id,
                        "title": video.title,
                        "imvdb_id": video.imvdb_id,
                        "youtube_id": video.youtube_id,
                        "url": video.url,
                        "thumbnail_url": video.thumbnail_url,
                        "thumbnail_path": video.thumbnail_path,
                        "local_path": video.local_path,
                        "duration": video.duration,
                        "year": video.year,
                        "release_date": (
                            video.release_date.isoformat()
                            if video.release_date
                            else None
                        ),
                        "description": video.description,
                        "view_count": video.view_count,
                        "directors": video.directors,
                        "producers": video.producers,
                        "status": video.status.value if video.status else None,
                        "quality": video.quality,
                        "video_metadata": video.video_metadata,
                        "discovered_date": (
                            video.discovered_date.isoformat()
                            if video.discovered_date
                            else None
                        ),
                        "created_at": video.created_at.isoformat(),
                        "updated_at": video.updated_at.isoformat(),
                    }
                )

            # Get downloads for this artist
            downloads = session.query(Download).filter_by(artist_id=artist_id).all()
            downloads_list = []
            for download in downloads:
                downloads_list.append(
                    {
                        "id": download.id,
                        "video_id": download.video_id,
                        "title": download.title,
                        "original_url": download.original_url,
                        "file_path": download.file_path,
                        "file_size": download.file_size,
                        "download_date": (
                            download.download_date.isoformat()
                            if download.download_date
                            else None
                        ),
                        "status": download.status,
                        "progress": download.progress,
                        "error_message": download.error_message,
                        "quality": download.quality,
                        "format": download.format,
                    }
                )

            # Compile comprehensive artist data
            artist_detailed = {
                "id": artist.id,
                "name": artist.name,
                "sort_name": artist.name,
                "imvdb_id": artist.imvdb_id,
                "spotify_id": artist.spotify_id,
                "lastfm_name": artist.lastfm_name,
                "thumbnail_url": artist.thumbnail_url,
                "thumbnail_path": artist.thumbnail_path,
                "auto_download": artist.auto_download,
                "keywords": artist.keywords or [],
                "genres": (
                    artist.genres
                    if isinstance(artist.genres, list)
                    else (
                        artist.genres.split(", ")
                        if isinstance(artist.genres, str) and artist.genres.strip()
                        else []
                    )
                ),
                "labels": artist.labels or [],
                "members": artist.members,
                "monitored": artist.monitored,
                "folder_path": ensure_artist_folder_path(artist, session),
                "last_discovery": (
                    artist.last_discovery.isoformat() if artist.last_discovery else None
                ),
                "created_at": artist.created_at.isoformat(),
                "updated_at": artist.updated_at.isoformat(),
                "imvdb_metadata": artist.imvdb_metadata,
                "videos": videos_list,
                "downloads": downloads_list,
                "statistics": stats,
            }

            return jsonify(artist_detailed), 200

    except Exception as e:
        logger.error(f"Failed to get detailed artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/videos/discover", methods=["POST"])
def discover_artist_videos(artist_id):
    """Enhanced video discovery with filtering, sorting, and bulk operations"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Get enhanced discovery options from request
            data = request.get_json() or {}
            limit = min(int(data.get("limit", 50)), 200)  # Increased max limit
            auto_import = data.get("auto_import", False)

            # New filtering options
            filter_options = data.get("filters", {})
            year_from = filter_options.get("year_from")
            year_to = filter_options.get("year_to")
            include_existing = filter_options.get("include_existing", True)
            directors_filter = filter_options.get("directors", [])

            # Sorting options
            sort_by = data.get("sort_by", "year")  # year, title, directors
            sort_order = data.get("sort_order", "desc")  # desc, asc

            # Extract artist data for use outside session
            artist_name = artist.name
            artist_imvdb_id = artist.imvdb_id

            # Search for videos on IMVDb - use IMVDb ID if available for better accuracy
            imvdb_videos = []
            if artist_imvdb_id:
                logger.info(
                    f"Using IMVDb ID {artist_imvdb_id} for video discovery for artist {artist_name}"
                )
                videos_data = imvdb_service.get_artist_videos_by_id(
                    artist_imvdb_id, limit=limit
                )
            else:
                logger.info(
                    f"Using name search for video discovery for artist {artist_name}"
                )
                videos_data = imvdb_service.search_artist_videos(
                    artist_name, limit=limit
                )

            if videos_data and videos_data.get("videos"):
                imvdb_videos = videos_data["videos"]

            # Search for videos on YouTube (top 50 results)
            youtube_videos = []
            try:
                youtube_data = youtube_search_service.search_artist_videos(
                    artist_name, limit=50  # Increased from 20 to YouTube API maximum
                )
                if youtube_data and youtube_data.get("videos"):
                    youtube_videos = youtube_data["videos"]
                    logger.info(
                        f"Found {len(youtube_videos)} YouTube videos for artist {artist_name}"
                    )
            except Exception as e:
                logger.warning(f"YouTube search failed for artist {artist_name}: {e}")

            # Combine results - if no IMVDb videos found, we still have YouTube results
            if not imvdb_videos and not youtube_videos:
                return (
                    jsonify(
                        {
                            "discovered_videos": [],
                            "total_discovered": 0,
                            "imported_count": 0,
                            "skipped_count": 0,
                            "message": "No videos found on IMVDb or YouTube for this artist",
                        }
                    ),
                    200,
                )

            discovered_videos = []
            imported_count = 0
            skipped_count = 0
            filtered_count = 0

            # Process and filter IMVDb videos
            for video_data in imvdb_videos:
                video_metadata = imvdb_service.extract_metadata(video_data)

                # Apply year filtering
                video_year = video_metadata.get("year")
                if year_from and video_year and video_year < year_from:
                    filtered_count += 1
                    continue
                if year_to and video_year and video_year > year_to:
                    filtered_count += 1
                    continue

                # Apply director filtering
                if directors_filter:
                    video_directors = video_metadata.get("directors", [])
                    if not any(
                        director.lower() in [d.lower() for d in directors_filter]
                        for director in video_directors
                    ):
                        filtered_count += 1
                        continue

                # Check if video already exists
                existing_video = (
                    session.query(Video)
                    .filter(Video.imvdb_id == video_metadata["imvdb_id"])
                    .first()
                )

                # Apply existing video filter
                if not include_existing and existing_video:
                    filtered_count += 1
                    continue

                # Enhanced video info with additional metadata
                video_info = {
                    "source": "imvdb",
                    "imvdb_id": video_metadata["imvdb_id"],
                    "title": video_metadata["title"],
                    "artist_name": artist_name,  # Add artist name for display
                    "year": video_metadata["year"],
                    "directors": video_metadata["directors"],
                    "producers": video_metadata["producers"],
                    "thumbnail_url": video_metadata["thumbnail_url"],
                    "genre": video_metadata["genre"],
                    "label": video_metadata["label"],
                    "album": video_metadata["album"],
                    "imvdb_url": video_metadata["imvdb_url"],
                    "already_exists": bool(existing_video),
                    "existing_video_id": existing_video.id if existing_video else None,
                    "existing_status": (
                        existing_video.status.value if existing_video else None
                    ),
                    "duration": video_metadata.get("duration"),
                    "description": video_metadata.get("description", ""),
                    "search_score": video_metadata.get("search_score", 1.0),
                    "featured_artists": video_metadata.get("featured_artists", []),
                }

                discovered_videos.append(video_info)

                if existing_video:
                    skipped_count += 1
                elif auto_import:
                    # Import the video automatically with enhanced metadata
                    try:
                        new_video = Video(
                            artist_id=artist_id,
                            title=str(video_metadata["title"]),
                            imvdb_id=video_metadata["imvdb_id"],
                            thumbnail_url=video_metadata["thumbnail_url"],
                            year=video_metadata["year"],
                            directors=video_metadata["directors"],
                            producers=video_metadata["producers"],
                            duration=video_metadata.get("duration"),
                            description=video_metadata.get("description", ""),
                            video_metadata=video_metadata.get("raw_metadata", {}),
                            imvdb_metadata=video_metadata.get("raw_metadata", {}),
                            status=VideoStatus.WANTED,
                            source="imvdb",
                            discovered_date=datetime.utcnow(),
                        )
                        session.add(new_video)
                        imported_count += 1
                        video_info["imported"] = True
                        video_info["new_video_id"] = new_video.id
                    except Exception as e:
                        logger.error(
                            f"Failed to import video {video_metadata['title']}: {e}"
                        )
                        video_info["import_error"] = str(e)

            # Process and filter YouTube videos
            for youtube_video in youtube_videos:
                # Apply year filtering (extract year from published date)
                published_at = youtube_video.get("published_at")
                video_year = None
                if published_at:
                    try:
                        video_year = int(published_at[:4])
                    except:
                        pass

                if year_from and video_year and video_year < year_from:
                    filtered_count += 1
                    continue
                if year_to and video_year and video_year > year_to:
                    filtered_count += 1
                    continue

                # Check if video already exists (by YouTube ID)
                existing_video = (
                    session.query(Video)
                    .filter(Video.youtube_id == youtube_video["youtube_id"])
                    .first()
                )

                # Apply existing video filter
                if not include_existing and existing_video:
                    filtered_count += 1
                    continue

                # Enhanced YouTube video info
                video_info = {
                    "source": "youtube",
                    "youtube_id": youtube_video["youtube_id"],
                    "youtube_url": youtube_video["youtube_url"],
                    "title": youtube_video["title"],
                    "artist_name": artist_name,  # Add artist name for display
                    "year": video_year,
                    "channel_title": youtube_video.get("channel_title"),
                    "channel_id": youtube_video.get("channel_id"),
                    "published_at": youtube_video.get("published_at"),
                    "thumbnail_url": youtube_video.get("thumbnail_url"),
                    "duration": youtube_video.get("duration"),
                    "view_count": youtube_video.get("view_count"),
                    "like_count": youtube_video.get("like_count"),
                    "description": youtube_video.get("description", ""),
                    "tags": youtube_video.get("tags", []),
                    "search_score": youtube_video.get("search_score", 1.0),
                    "already_exists": bool(existing_video),
                    "existing_video_id": existing_video.id if existing_video else None,
                    "existing_status": (
                        existing_video.status.value if existing_video else None
                    ),
                }

                discovered_videos.append(video_info)

                if existing_video:
                    skipped_count += 1
                elif auto_import:
                    # Import YouTube video automatically
                    try:
                        # Prepare video metadata
                        video_metadata = {
                            "youtube_data": {
                                "like_count": youtube_video.get("like_count"),
                                "published_at": youtube_video.get("published_at"),
                                "channel_title": youtube_video.get("channel_title"),
                                "imported_at": datetime.utcnow().isoformat(),
                            }
                        }

                        new_video = Video(
                            artist_id=artist_id,
                            title=str(youtube_video["title"]),
                            youtube_id=youtube_video["youtube_id"],
                            youtube_url=youtube_video["youtube_url"],
                            thumbnail_url=youtube_video.get("thumbnail_url"),
                            year=video_year,
                            duration=youtube_video.get("duration"),
                            description=youtube_video.get("description", ""),
                            view_count=youtube_video.get("view_count"),
                            video_metadata=video_metadata,
                            status=VideoStatus.WANTED,
                            source="youtube_search",
                            discovered_date=datetime.utcnow(),
                        )
                        session.add(new_video)
                        imported_count += 1
                        video_info["imported"] = True
                        video_info["new_video_id"] = new_video.id
                    except Exception as e:
                        logger.error(
                            f"Failed to import video {youtube_video['title']}: {e}"
                        )
                        video_info["import_error"] = str(e)

            # Apply sorting
            if discovered_videos:
                reverse_order = sort_order == "desc"

                if sort_by == "year":
                    discovered_videos.sort(
                        key=lambda x: x.get("year") or 0, reverse=reverse_order
                    )
                elif sort_by == "title":
                    discovered_videos.sort(
                        key=lambda x: x.get("title", "").lower(), reverse=reverse_order
                    )
                elif sort_by == "directors":
                    discovered_videos.sort(
                        key=lambda x: ", ".join(x.get("directors", [])).lower(),
                        reverse=reverse_order,
                    )
                elif sort_by == "search_score":
                    discovered_videos.sort(
                        key=lambda x: x.get("search_score", 0), reverse=reverse_order
                    )

            # Update artist's last discovery time
            artist.last_discovery = datetime.utcnow()

            # Always commit to update last_discovery time
            session.commit()

            if auto_import and imported_count > 0:
                logger.info(
                    f"Auto-imported {imported_count} videos for artist {artist_name}"
                )

            return (
                jsonify(
                    {
                        "discovered_videos": discovered_videos,
                        "total_discovered": len(discovered_videos),
                        "imported_count": imported_count,
                        "skipped_count": skipped_count,
                        "filtered_count": filtered_count,
                        "artist_name": artist_name,
                        "discovery_date": datetime.utcnow().isoformat(),
                        "filters_applied": {
                            "year_from": year_from,
                            "year_to": year_to,
                            "include_existing": include_existing,
                            "directors_filter": directors_filter,
                        },
                        "sorting": {"sort_by": sort_by, "sort_order": sort_order},
                        "statistics": {
                            "total_fetched": len(imvdb_videos) + len(youtube_videos),
                            "imvdb_videos": len(imvdb_videos),
                            "youtube_videos": len(youtube_videos),
                            "after_filtering": len(discovered_videos),
                            "new_videos": len(discovered_videos) - skipped_count,
                            "existing_videos": skipped_count,
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to discover videos for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/search/filters", methods=["GET"])
def get_search_filters():
    """Get available filter options for advanced search"""
    try:
        with get_db() as session:
            # Get unique keywords
            keywords_query = (
                session.query(Artist.keywords).filter(Artist.keywords.isnot(None)).all()
            )
            all_keywords = set()
            for keywords_row in keywords_query:
                if keywords_row[0]:  # keywords is a JSON field
                    for keyword in keywords_row[0]:
                        if keyword and isinstance(keyword, str):
                            all_keywords.add(keyword.strip())

            # Get date ranges
            date_range = session.query(
                func.min(Artist.created_at).label("earliest"),
                func.max(Artist.created_at).label("latest"),
            ).first()

            # Get video count ranges
            video_stats = (
                session.query(func.count(Video.id).label("count"), Video.artist_id)
                .group_by(Video.artist_id)
                .subquery()
            )

            video_count_stats = session.query(
                func.min(video_stats.c.count).label("min_videos"),
                func.max(video_stats.c.count).label("max_videos"),
                func.avg(video_stats.c.count).label("avg_videos"),
            ).first()

            # Get general statistics
            total_artists = session.query(Artist).count()
            monitored_artists = (
                session.query(Artist).filter(Artist.monitored == True).count()
            )
            auto_download_artists = (
                session.query(Artist).filter(Artist.auto_download == True).count()
            )
            artists_with_thumbnails = (
                session.query(Artist)
                .filter(
                    or_(
                        Artist.thumbnail_url.isnot(None),
                        Artist.thumbnail_path.isnot(None),
                    )
                )
                .count()
            )
            artists_with_imvdb = (
                session.query(Artist).filter(Artist.imvdb_id.isnot(None)).count()
            )

            return (
                jsonify(
                    {
                        "filters": {
                            "keywords": sorted(list(all_keywords)),
                            "date_range": {
                                "earliest": (
                                    date_range.earliest.isoformat()
                                    if date_range.earliest
                                    else None
                                ),
                                "latest": (
                                    date_range.latest.isoformat()
                                    if date_range.latest
                                    else None
                                ),
                            },
                            "video_count_range": {
                                "min": (
                                    int(video_count_stats.min_videos)
                                    if video_count_stats.min_videos
                                    else 0
                                ),
                                "max": (
                                    int(video_count_stats.max_videos)
                                    if video_count_stats.max_videos
                                    else 0
                                ),
                                "average": (
                                    float(video_count_stats.avg_videos)
                                    if video_count_stats.avg_videos
                                    else 0
                                ),
                            },
                        },
                        "statistics": {
                            "total_artists": total_artists,
                            "monitored_artists": monitored_artists,
                            "auto_download_artists": auto_download_artists,
                            "artists_with_thumbnails": artists_with_thumbnails,
                            "artists_with_imvdb": artists_with_imvdb,
                            "monitoring_percentage": (
                                round((monitored_artists / total_artists * 100), 2)
                                if total_artists > 0
                                else 0
                            ),
                            "thumbnail_coverage": (
                                round(
                                    (artists_with_thumbnails / total_artists * 100), 2
                                )
                                if total_artists > 0
                                else 0
                            ),
                            "imvdb_coverage": (
                                round((artists_with_imvdb / total_artists * 100), 2)
                                if total_artists > 0
                                else 0
                            ),
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get search filters: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/search/suggestions", methods=["GET"])
def get_search_suggestions():
    """Get search suggestions based on partial input"""
    try:
        query_term = request.args.get("q", "").strip()
        limit = min(int(request.args.get("limit", 10)), 50)

        if not query_term or len(query_term) < 2:
            return jsonify({"suggestions": []}), 200

        with get_db() as session:
            # Search in artist names
            suggestions = (
                session.query(Artist.name)
                .filter(Artist.name.ilike(f"%{query_term}%"))
                .order_by(Artist.name)
                .limit(limit)
                .all()
            )

            suggestion_list = [
                {"text": suggestion[0], "type": "artist_name"}
                for suggestion in suggestions
            ]

            # Also search in keywords if we have room
            if len(suggestion_list) < limit:
                remaining_limit = limit - len(suggestion_list)
                keyword_suggestions = []

                keywords_query = (
                    session.query(Artist.keywords)
                    .filter(Artist.keywords.isnot(None))
                    .all()
                )

                for keywords_row in keywords_query:
                    if keywords_row[0]:
                        for keyword in keywords_row[0]:
                            if (
                                keyword
                                and isinstance(keyword, str)
                                and query_term.lower() in keyword.lower()
                            ):
                                if keyword not in [
                                    s["text"] for s in keyword_suggestions
                                ]:
                                    keyword_suggestions.append(
                                        {"text": keyword, "type": "keyword"}
                                    )
                                    if len(keyword_suggestions) >= remaining_limit:
                                        break

                suggestion_list.extend(keyword_suggestions[:remaining_limit])

            return (
                jsonify(
                    {
                        "suggestions": suggestion_list,
                        "query": query_term,
                        "count": len(suggestion_list),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get search suggestions: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/metadata/search", methods=["POST"])
def search_imvdb_matches(artist_id):
    """Search for multiple IMVDb matches for an artist"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name

        # Debug: Force settings reload and check API key
        from src.services.settings_service import SettingsService

        SettingsService.reload_cache()
        api_key = SettingsService.get("imvdb_api_key", "")
        logger.info(
            f"IMVDb API key for {artist_name}: {'SET' if api_key else 'NOT SET'}"
        )

        # Search for multiple matches using IMVDb service
        matches = imvdb_service.search_artist(artist_name, return_multiple=True)

        if matches is None:
            return (
                jsonify(
                    {
                        "error": "IMVDb API key not configured",
                        "message": "Please configure your IMVDb API key in Settings to use this feature",
                        "action": "Go to Settings > External Services and add your IMVDb API key",
                        "help_url": "https://imvdb.com/developers/api",
                    }
                ),
                400,
            )

        if not matches:
            return (
                jsonify(
                    {"matches": [], "message": f'No matches found for "{artist_name}"'}
                ),
                200,
            )

        # Format the matches for frontend display
        formatted_matches = []
        for match in matches:
            # Handle cases where name is null by using slug or other fields
            display_name = match.get("name")
            # Ensure display_name is a string if it exists (fix for integer name issue)
            if display_name:
                display_name = str(display_name)
            if not display_name:
                # Try to use slug or other identifiers
                slug = match.get("slug", "")
                if slug:
                    # Ensure slug is a string (fix for integer slug issue)
                    slug = str(slug)
                    # Convert slug to readable name (e.g., "damn-yankees" -> "Damn Yankees")
                    display_name = " ".join(
                        word.capitalize() for word in slug.split("-")
                    )
                else:
                    display_name = f"Artist ID {match.get('id', 'Unknown')}"

            formatted_match = {
                "id": match.get("id"),
                "name": display_name,
                "bio": match.get("bio", ""),
                "birth_date": match.get("birth_date"),
                "death_date": match.get("death_date"),
                "origin": match.get("origin"),
                "genres": match.get("genres", []),
                "image": match.get("image"),
                "url": match.get("url"),
                "disambiguation": match.get("disambiguation"),
                "type": match.get("type"),
                "slug": match.get("slug"),
                "confidence": (
                    "high"
                    if (display_name and display_name.lower() == artist_name.lower())
                    else "medium"
                ),
            }
            formatted_matches.append(formatted_match)

        return (
            jsonify(
                {
                    "matches": formatted_matches,
                    "artist_name": artist_name,
                    "count": len(formatted_matches),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to search IMVDb matches for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/metadata/update-from-match", methods=["PUT"])
def update_metadata_from_match(artist_id):
    """Update artist metadata from selected IMVDb match"""
    try:
        data = request.get_json()
        if not data or "imvdb_id" not in data:
            return jsonify({"error": "IMVDb ID is required"}), 400

        imvdb_id = data["imvdb_id"]

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name
            existing_thumbnail_path = artist.thumbnail_path

        # Get detailed artist data from IMVDb
        artist_data = imvdb_service.get_artist(str(imvdb_id))

        if not artist_data:
            return jsonify({"error": "Failed to retrieve artist data from IMVDb"}), 404

        # Process thumbnail if available
        thumbnail_url = None
        new_thumbnail_path = existing_thumbnail_path

        if "image" in artist_data:
            image_data = artist_data["image"]
            if isinstance(image_data, dict):
                thumbnail_url = (
                    image_data.get("o")
                    or image_data.get("l")
                    or image_data.get("b")
                    or image_data.get("m")
                    or image_data.get("s")
                )
            elif isinstance(image_data, str) and image_data != "https://imvdb.com/":
                thumbnail_url = image_data

        if thumbnail_url:
            try:
                new_thumbnail_path = thumbnail_service.download_artist_thumbnail(
                    artist_name, thumbnail_url
                )
                if new_thumbnail_path:
                    logger.info(
                        f"Updated thumbnail for {artist_name}: {new_thumbnail_path}"
                    )
            except Exception as e:
                logger.warning(f"Failed to download thumbnail for {artist_name}: {e}")

        # Update artist metadata
        updated_fields = []

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            # Update IMVDb ID
            if str(imvdb_id) != str(artist.imvdb_id):
                artist.imvdb_id = str(imvdb_id)
                updated_fields.append("IMVDb ID")

            # Get current metadata or create empty dict
            current_metadata = artist.imvdb_metadata or {}

            # Update metadata fields in the JSON metadata
            metadata_updated = False

            if artist_data.get("bio") and artist_data["bio"] != current_metadata.get(
                "bio"
            ):
                current_metadata["bio"] = artist_data["bio"]
                updated_fields.append("biography")
                metadata_updated = True

            if artist_data.get("birth_date") and artist_data[
                "birth_date"
            ] != current_metadata.get("birth_date"):
                current_metadata["birth_date"] = artist_data["birth_date"]
                updated_fields.append("birth date")
                metadata_updated = True

            if artist_data.get("death_date") and artist_data[
                "death_date"
            ] != current_metadata.get("death_date"):
                current_metadata["death_date"] = artist_data["death_date"]
                updated_fields.append("death date")
                metadata_updated = True

            if artist_data.get("origin") and artist_data[
                "origin"
            ] != current_metadata.get("origin"):
                current_metadata["origin"] = artist_data["origin"]
                updated_fields.append("origin")
                metadata_updated = True

            # Update genres
            if artist_data.get("genres"):
                new_genres = artist_data["genres"]
                if isinstance(new_genres, list):
                    genres_str = ",".join(new_genres)
                else:
                    genres_str = str(new_genres)

                if genres_str != current_metadata.get("genres"):
                    current_metadata["genres"] = new_genres  # Store original format
                    updated_fields.append("genres")
                    metadata_updated = True

            # Update thumbnail
            if new_thumbnail_path != existing_thumbnail_path:
                artist.thumbnail_path = new_thumbnail_path
                if new_thumbnail_path:
                    artist.thumbnail_url = f"/api/artists/{artist_id}/thumbnail"
                    updated_fields.append("thumbnail")

            # Store full metadata and update with current metadata
            if metadata_updated:
                current_metadata.update(artist_data)
                artist.imvdb_metadata = current_metadata
            else:
                artist.imvdb_metadata = artist_data

            artist.updated_at = datetime.utcnow()

            # Collect artist data while still in session
            artist_response_data = {
                "id": artist.id,
                "name": artist.name,
                "imvdb_id": artist.imvdb_id,
                "bio": current_metadata.get("bio"),
                "genres": current_metadata.get("genres"),
                "origin": current_metadata.get("origin"),
                "thumbnail_url": artist.thumbnail_url,
            }

            session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "message": f'Successfully updated metadata for "{artist_name}"',
                    "updated_fields": updated_fields,
                    "artist_data": artist_response_data,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(
            f"Failed to update metadata from match for artist {artist_id}: {e}"
        )
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/thumbnail-test", methods=["GET"])
def test_thumbnail():
    """Test thumbnail serving functionality"""
    try:
        # Try to serve the placeholder directly
        placeholder_paths = [
            Path("frontend/static/placeholder-artist.png"),
            Path("/home/mike/mvidarr/frontend/static/placeholder-artist.png"),
            Path("frontend/static/placeholder-video.png"),
            Path("/home/mike/mvidarr/frontend/static/placeholder-video.png"),
        ]

        for placeholder_path in placeholder_paths:
            if placeholder_path.exists():
                logger.info(f"Test: Found placeholder at {placeholder_path}")
                return send_file(str(placeholder_path), mimetype="image/png")

        # If no placeholder found, generate one
        try:
            import io

            from PIL import Image

            img = Image.new("RGB", (200, 200), (255, 0, 0))  # Red test image
            img_io = io.BytesIO()
            img.save(img_io, "PNG")
            img_io.seek(0)
            logger.info("Test: Generated red test image")
            return send_file(img_io, mimetype="image/png")
        except ImportError:
            logger.error("Test: PIL not available")
            return "PIL not available", 500

    except Exception as e:
        logger.error(f"Test thumbnail error: {e}")
        return f"Error: {e}", 500


# Legacy endpoint - redirect to new settings endpoint
@artists_bp.route("/<int:artist_id>", methods=["PUT"])
def update_artist(artist_id):
    """Update artist settings (legacy endpoint)"""
    return update_artist_settings(artist_id)


@artists_bp.route("/populate-thumbnails", methods=["POST"])
def populate_artist_thumbnails():
    """Populate artist thumbnails from multiple sources (Wikipedia, YouTube) per user priority settings"""
    try:
        # Get optional limit from request
        data = request.get_json() or {}
        limit = data.get("limit", 10)  # Default to 10 artists per request

        with get_db() as session:
            # Get artist IDs without thumbnails first
            artist_ids_query = (
                session.query(Artist.id, Artist.name)
                .filter(Artist.thumbnail_url.is_(None))
                .distinct()
            )

            if limit:
                artist_ids_query = artist_ids_query.limit(limit)

            artist_data_list = artist_ids_query.all()

            if not artist_data_list:
                return (
                    jsonify(
                        {
                            "message": "No artists found without thumbnails",
                            "updated_count": 0,
                            "processed_count": 0,
                        }
                    ),
                    200,
                )

            logger.info(
                f"Processing {len(artist_data_list)} artists for thumbnail population using priority sources (Wikipedia, YouTube)"
            )

            updated_count = 0
            processed_count = 0
            results = []
            processed_artist_ids = set()  # Track processed artists to avoid duplicates

            # Process each artist by ID to avoid session binding issues
            for artist_id, artist_name in artist_data_list:
                # Skip if already processed (avoid duplicates)
                if artist_id in processed_artist_ids:
                    continue
                processed_artist_ids.add(artist_id)
                processed_count += 1
                try:
                    logger.info(f"Processing artist: {artist_name}")

                    # Search for thumbnails using priority sources (no IMVDb per user requirements)
                    thumbnail_url = None
                    thumbnail_source = None

                    # 1. Try Wikipedia (highest priority for thumbnails)
                    try:
                        wiki_thumbnail_url = wikipedia_service.search_artist_thumbnail(
                            artist_name
                        )
                        if wiki_thumbnail_url:
                            thumbnail_url = wiki_thumbnail_url
                            thumbnail_source = "Wikipedia"
                            logger.info(
                                f"Found Wikipedia thumbnail for {artist_name}: {thumbnail_url}"
                            )
                    except Exception as wiki_e:
                        logger.warning(
                            f"Wikipedia thumbnail search failed for {artist_name}: {wiki_e}"
                        )

                    # 2. Try YouTube as fallback if no Wikipedia thumbnail
                    if not thumbnail_url:
                        try:
                            from src.services.youtube_search_service import (
                                search_artist_channel_thumbnail,
                            )

                            youtube_thumbnail = search_artist_channel_thumbnail(
                                artist_name
                            )
                            if youtube_thumbnail:
                                thumbnail_url = youtube_thumbnail
                                thumbnail_source = "YouTube"
                                logger.info(
                                    f"Found YouTube thumbnail for {artist_name}: {thumbnail_url}"
                                )
                        except Exception as youtube_e:
                            logger.warning(
                                f"YouTube thumbnail search failed for {artist_name}: {youtube_e}"
                            )

                    if thumbnail_url:
                        # Download and save thumbnail
                        thumbnail_path = thumbnail_service.download_artist_thumbnail(
                            artist_name, thumbnail_url
                        )

                        if thumbnail_path:
                            # Update artist with thumbnail info - use fresh query to ensure session binding
                            try:
                                artist_to_update = (
                                    session.query(Artist)
                                    .filter_by(id=artist_id)
                                    .first()
                                )
                                if artist_to_update:
                                    artist_to_update.thumbnail_url = thumbnail_url
                                    artist_to_update.thumbnail_path = thumbnail_path
                                    artist_to_update.thumbnail_source = (
                                        thumbnail_source.lower()
                                    )  # Track source
                                    session.flush()  # Flush immediately to catch any issues
                                    updated_count += 1
                            except Exception as update_error:
                                logger.error(
                                    f"Failed to update artist {artist_name} in database: {update_error}"
                                )
                                results.append(
                                    {
                                        "artist_id": artist_id,
                                        "artist_name": artist_name,
                                        "status": "db_error",
                                        "error": f"Database update failed: {str(update_error)}",
                                    }
                                )
                                continue

                            results.append(
                                {
                                    "artist_id": artist_id,
                                    "artist_name": artist_name,
                                    "status": "success",
                                    "thumbnail_url": thumbnail_url,
                                    "thumbnail_source": thumbnail_source,
                                }
                            )

                            logger.info(
                                f"Updated thumbnail for {artist_name} from {thumbnail_source}"
                            )
                        else:
                            results.append(
                                {
                                    "artist_id": artist_id,
                                    "artist_name": artist_name,
                                    "status": "failed",
                                    "error": "Failed to download thumbnail",
                                }
                            )
                            logger.warning(
                                f"Failed to download thumbnail for {artist_name}"
                            )
                    else:
                        results.append(
                            {
                                "artist_id": artist_id,
                                "artist_name": artist_name,
                                "status": "no_thumbnail",
                                "error": "No thumbnail found from Wikipedia or YouTube",
                            }
                        )
                        logger.info(
                            f"No thumbnail available for {artist_name} from priority sources"
                        )

                except Exception as e:
                    results.append(
                        {
                            "artist_id": artist_id,
                            "artist_name": artist_name,
                            "status": "error",
                            "error": str(e),
                        }
                    )
                    logger.error(f"Failed to process artist {artist_name}: {e}")
                    continue

            session.commit()

            return (
                jsonify(
                    {
                        "message": f"Processed {processed_count} artists, updated {updated_count} thumbnails",
                        "updated_count": updated_count,
                        "processed_count": processed_count,
                        "results": results,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to populate artist thumbnails: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail", methods=["GET"])
def get_artist_thumbnail(artist_id):
    """Serve artist thumbnail image"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                logger.warning(f"Artist {artist_id} not found for thumbnail request")
                abort(404)

            logger.debug(f"Thumbnail request for artist {artist_id} ({artist.name})")
            logger.debug(f"  thumbnail_path: {artist.thumbnail_path}")
            logger.debug(f"  thumbnail_url: {artist.thumbnail_url}")

            # Check if artist has a local thumbnail
            if artist.thumbnail_path and os.path.exists(artist.thumbnail_path):
                logger.debug(f"Serving local thumbnail: {artist.thumbnail_path}")
                return send_file(artist.thumbnail_path, mimetype="image/jpeg")

            # If no local thumbnail, try to download from URL if available
            if artist.thumbnail_url:
                try:
                    logger.debug(
                        f"Attempting to download thumbnail from: {artist.thumbnail_url}"
                    )
                    # Try to download the thumbnail
                    downloaded_path = thumbnail_service.download_artist_thumbnail(
                        artist.name, artist.thumbnail_url
                    )

                    if downloaded_path and os.path.exists(downloaded_path):
                        # Update the artist record with the new path
                        artist.thumbnail_path = downloaded_path
                        session.commit()
                        logger.debug(
                            f"Downloaded and serving thumbnail: {downloaded_path}"
                        )
                        return send_file(downloaded_path, mimetype="image/jpeg")

                except Exception as e:
                    logger.warning(
                        f"Failed to download thumbnail for artist {artist_id}: {e}"
                    )

            logger.debug("No thumbnail available, trying placeholder images")

            # Return placeholder if no thumbnail available
            # Try multiple possible placeholder paths
            placeholder_paths = [
                Path("frontend/static/placeholder-artist.png"),
                Path("/home/mike/mvidarr/frontend/static/placeholder-artist.png"),
                Path("frontend/static/placeholder-video.png"),
                Path("/home/mike/mvidarr/frontend/static/placeholder-video.png"),
            ]

            for placeholder_path in placeholder_paths:
                if placeholder_path.exists():
                    return send_file(str(placeholder_path), mimetype="image/png")

            # Generate a simple placeholder as fallback
            try:
                import io

                from PIL import Image

                img = Image.new("RGB", (200, 200), (128, 128, 128))
                img_io = io.BytesIO()
                img.save(img_io, "PNG")
                img_io.seek(0)
                return send_file(img_io, mimetype="image/png")
            except ImportError:
                # If PIL not available, return a basic response
                logger.warning("PIL not available, returning 404 for missing thumbnail")
                abort(404)

    except Exception as e:
        logger.error(f"Failed to serve thumbnail for artist {artist_id}: {e}")
        abort(500)


@artists_bp.route("/<int:artist_id>/settings", methods=["PUT"])
def update_artist_settings(artist_id):
    """Update artist settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data is required"}), 400

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Update fields if provided
            if "name" in data:
                new_name = data["name"].strip()
                if new_name:
                    artist.name = new_name
                else:
                    return jsonify({"error": "Artist name cannot be empty"}), 400

            if "folder_path" in data:
                artist.folder_path = (
                    data["folder_path"].strip() if data["folder_path"] else None
                )

            if "keywords" in data:
                if isinstance(data["keywords"], str):
                    # Convert comma-separated string to list
                    keywords = [
                        k.strip() for k in data["keywords"].split(",") if k.strip()
                    ]
                elif isinstance(data["keywords"], list):
                    keywords = data["keywords"]
                else:
                    keywords = []
                artist.keywords = keywords

            if "monitored" in data:
                artist.monitored = bool(data["monitored"])

            if "auto_download" in data:
                artist.auto_download = bool(data["auto_download"])

            if "imvdb_id" in data:
                new_imvdb_id = data["imvdb_id"]

                # Handle empty string or None
                if new_imvdb_id == "" or new_imvdb_id is None:
                    artist.imvdb_id = None
                else:
                    # Validate it's a positive integer
                    try:
                        imvdb_id_int = int(new_imvdb_id)
                        if imvdb_id_int <= 0:
                            return (
                                jsonify(
                                    {"error": "IMVDb ID must be a positive integer"}
                                ),
                                400,
                            )

                        # Check for duplicate IMVDb ID (excluding current artist)
                        existing_artist = (
                            session.query(Artist)
                            .filter(
                                Artist.imvdb_id == str(imvdb_id_int),
                                Artist.id != artist_id,
                            )
                            .first()
                        )

                        if existing_artist:
                            return (
                                jsonify(
                                    {
                                        "error": f'IMVDb ID {imvdb_id_int} is already assigned to artist "{existing_artist.name}"',
                                        "duplicate_conflict": True,
                                        "existing_artist": {
                                            "id": existing_artist.id,
                                            "name": existing_artist.name,
                                            "imvdb_id": existing_artist.imvdb_id,
                                            "video_count": len(existing_artist.videos),
                                            "monitored": existing_artist.monitored,
                                            "auto_download": existing_artist.auto_download,
                                        },
                                        "current_artist": {
                                            "id": artist.id,
                                            "name": artist.name,
                                            "imvdb_id": artist.imvdb_id,
                                            "video_count": len(artist.videos),
                                            "monitored": artist.monitored,
                                            "auto_download": artist.auto_download,
                                        },
                                    }
                                ),
                                409,
                            )  # 409 Conflict status code

                        artist.imvdb_id = str(imvdb_id_int)
                        logger.info(
                            f"Updated IMVDb ID for artist {artist.name} to {imvdb_id_int}"
                        )

                    except (ValueError, TypeError):
                        return (
                            jsonify({"error": "IMVDb ID must be a valid integer"}),
                            400,
                        )

            # Handle MusicBrainz ID (stored in imvdb_metadata JSON field)
            if "musicbrainz_id" in data:
                new_mbid = data["musicbrainz_id"]
                if not isinstance(artist.imvdb_metadata, dict):
                    artist.imvdb_metadata = {}
                if new_mbid == "" or new_mbid is None:
                    if "musicbrainz_id" in artist.imvdb_metadata:
                        del artist.imvdb_metadata["musicbrainz_id"]
                else:
                    artist.imvdb_metadata["musicbrainz_id"] = str(new_mbid).strip()
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(artist, "imvdb_metadata")

            # Handle Spotify ID updates
            if "spotify_id" in data:
                new_spotify_id = data["spotify_id"]
                if new_spotify_id == "" or new_spotify_id is None:
                    artist.spotify_id = None
                else:
                    artist.spotify_id = str(new_spotify_id).strip()

            # Handle Last.fm name updates
            if "lastfm_name" in data:
                new_lastfm_name = data["lastfm_name"]
                if new_lastfm_name == "" or new_lastfm_name is None:
                    artist.lastfm_name = None
                else:
                    artist.lastfm_name = str(new_lastfm_name).strip()

            # Handle AllMusic ID (stored in imvdb_metadata JSON field like MusicBrainz)
            if "allmusic_id" in data:
                new_allmusic_id = data["allmusic_id"]
                if not isinstance(artist.imvdb_metadata, dict):
                    artist.imvdb_metadata = {}
                if new_allmusic_id == "" or new_allmusic_id is None:
                    if "allmusic_id" in artist.imvdb_metadata:
                        del artist.imvdb_metadata["allmusic_id"]
                else:
                    artist.imvdb_metadata["allmusic_id"] = str(new_allmusic_id).strip()
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(artist, "imvdb_metadata")

            # Handle AllMusic metadata
            if "allmusic_metadata" in data:
                if not isinstance(artist.imvdb_metadata, dict):
                    artist.imvdb_metadata = {}
                artist.imvdb_metadata["allmusic_metadata"] = data["allmusic_metadata"]
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(artist, "imvdb_metadata")

            # Handle Wikipedia URL (stored in imvdb_metadata JSON field)
            if "wikipedia_url" in data:
                new_wikipedia_url = data["wikipedia_url"]
                if not isinstance(artist.imvdb_metadata, dict):
                    artist.imvdb_metadata = {}
                if new_wikipedia_url == "" or new_wikipedia_url is None:
                    if "wikipedia_url" in artist.imvdb_metadata:
                        del artist.imvdb_metadata["wikipedia_url"]
                else:
                    artist.imvdb_metadata["wikipedia_url"] = str(
                        new_wikipedia_url
                    ).strip()
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(artist, "imvdb_metadata")

            # Handle Wikipedia metadata
            if "wikipedia_metadata" in data:
                if not isinstance(artist.imvdb_metadata, dict):
                    artist.imvdb_metadata = {}
                artist.imvdb_metadata["wikipedia_metadata"] = data["wikipedia_metadata"]
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(artist, "imvdb_metadata")

            # Handle genres
            if "genres" in data:
                if isinstance(data["genres"], str):
                    # Convert comma-separated string to list
                    genres = [g.strip() for g in data["genres"].split(",") if g.strip()]
                elif isinstance(data["genres"], list):
                    genres = data["genres"]
                else:
                    genres = []
                artist.genres = genres

            # Handle labels (record labels)
            if "labels" in data:
                if isinstance(data["labels"], str):
                    # Convert comma-separated string to list
                    labels = [l.strip() for l in data["labels"].split(",") if l.strip()]
                elif isinstance(data["labels"], list):
                    labels = data["labels"]
                else:
                    labels = []
                artist.labels = labels

            # Handle members (band members)
            if "members" in data:
                artist.members = data["members"].strip() if data["members"] else None

            # Update the updated_at timestamp
            artist.updated_at = datetime.utcnow()

            session.commit()

            logger.info(f"Updated settings for artist {artist.name}")

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Artist settings updated successfully",
                        "artist": {
                            "id": artist.id,
                            "name": artist.name,
                            "imvdb_id": artist.imvdb_id,
                            "spotify_id": artist.spotify_id,
                            "lastfm_name": artist.lastfm_name,
                            "imvdb_metadata": artist.imvdb_metadata,
                            "folder_path": ensure_artist_folder_path(artist, session),
                            "keywords": artist.keywords or [],
                            "genres": artist.genres or [],
                            "labels": artist.labels or [],
                            "members": artist.members,
                            "monitored": artist.monitored,
                            "auto_download": artist.auto_download,
                            "updated_at": artist.updated_at.isoformat(),
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to update artist settings: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail", methods=["PUT"])
def update_artist_thumbnail(artist_id):
    """Update/edit individual artist thumbnail"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data is required"}), 400

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            thumbnail_url = data.get("thumbnail_url")
            remove_thumbnail = data.get("remove_thumbnail", False)

            if remove_thumbnail:
                # Remove existing thumbnail
                if artist.thumbnail_path and os.path.exists(artist.thumbnail_path):
                    try:
                        os.remove(artist.thumbnail_path)
                        logger.info(f"Removed thumbnail file: {artist.thumbnail_path}")
                    except Exception as e:
                        logger.warning(f"Failed to remove thumbnail file: {e}")

                artist.thumbnail_url = None
                artist.thumbnail_path = None
                artist.updated_at = datetime.utcnow()
                session.commit()

                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "Thumbnail removed successfully",
                            "artist": {
                                "id": artist.id,
                                "name": artist.name,
                                "thumbnail_url": None,
                                "thumbnail_path": None,
                            },
                        }
                    ),
                    200,
                )

            elif thumbnail_url:
                # Validate URL format
                if not (
                    thumbnail_url.startswith("http://")
                    or thumbnail_url.startswith("https://")
                ):
                    return jsonify({"error": "Invalid thumbnail URL format"}), 400

                # Download and save new thumbnail
                try:
                    downloaded_path = thumbnail_service.download_artist_thumbnail(
                        artist.name, thumbnail_url
                    )

                    if downloaded_path and os.path.exists(downloaded_path):
                        # Remove old thumbnail if exists
                        if artist.thumbnail_path and os.path.exists(
                            artist.thumbnail_path
                        ):
                            try:
                                os.remove(artist.thumbnail_path)
                            except Exception as e:
                                logger.warning(f"Failed to remove old thumbnail: {e}")

                        # Update artist with new thumbnail
                        artist.thumbnail_url = thumbnail_url
                        artist.thumbnail_path = downloaded_path
                        artist.updated_at = datetime.utcnow()
                        session.commit()

                        logger.info(f"Updated thumbnail for artist {artist.name}")

                        return (
                            jsonify(
                                {
                                    "success": True,
                                    "message": "Thumbnail updated successfully",
                                    "artist": {
                                        "id": artist.id,
                                        "name": artist.name,
                                        "thumbnail_url": thumbnail_url,
                                        "thumbnail_path": downloaded_path,
                                    },
                                }
                            ),
                            200,
                        )
                    else:
                        return (
                            jsonify({"error": "Failed to download thumbnail from URL"}),
                            400,
                        )

                except Exception as e:
                    logger.error(f"Failed to download thumbnail: {e}")
                    return (
                        jsonify({"error": f"Failed to download thumbnail: {str(e)}"}),
                        400,
                    )
            else:
                return (
                    jsonify(
                        {
                            "error": "Either thumbnail_url or remove_thumbnail must be provided"
                        }
                    ),
                    400,
                )

    except Exception as e:
        logger.error(f"Failed to update artist thumbnail: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail/search", methods=["POST"])
def search_artist_thumbnail(artist_id):
    """Search for artist thumbnail using multiple sources (Wikipedia, YouTube)"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name

        # Search all sources simultaneously
        results = []

        # Skip IMVDb thumbnail search per user requirements
        # IMVDb should only be used for searching artists and videos, not as metadata or thumbnail source

        # Search Wikipedia
        try:
            thumbnail_url = wikipedia_service.search_artist_thumbnail(artist_name)
            if thumbnail_url:
                results.append(
                    {"url": thumbnail_url, "source": "Wikipedia", "quality": "high"}
                )
                logger.info(
                    f"Found thumbnail for {artist_name} from Wikipedia: {thumbnail_url}"
                )
        except Exception as wiki_e:
            logger.warning(f"Wikipedia search failed for {artist_name}: {wiki_e}")

        # Search YouTube (try to find artist's channel thumbnail)
        try:
            from src.services.youtube_search_service import (
                search_artist_channel_thumbnail,
            )

            youtube_thumbnail = search_artist_channel_thumbnail(artist_name)
            if youtube_thumbnail:
                results.append(
                    {"url": youtube_thumbnail, "source": "YouTube", "quality": "medium"}
                )
                logger.info(
                    f"Found thumbnail for {artist_name} from YouTube: {youtube_thumbnail}"
                )
        except Exception as youtube_e:
            logger.warning(f"YouTube search failed for {artist_name}: {youtube_e}")

        if results:
            return (
                jsonify(
                    {
                        "success": True,
                        "results": results,
                        "artist_name": artist_name,
                        "total_found": len(results),
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f'No thumbnail found for "{artist_name}" from any source',
                        "results": [],
                    }
                ),
                404,
            )

    except Exception as e:
        logger.error(f"Failed to search thumbnail for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/scan-missing-thumbnails", methods=["POST"])
def scan_missing_thumbnails():
    """Scan all artists missing thumbnails and try to find images"""
    try:
        # First get the list of artist IDs and names to avoid session issues
        artist_data_list = []
        with get_db() as session:
            artists_without_thumbnails = (
                session.query(Artist.id, Artist.name)
                .filter(
                    or_(
                        Artist.thumbnail_url.is_(None),
                        Artist.thumbnail_url == "",
                        Artist.thumbnail_path.is_(None),
                        Artist.thumbnail_path == "",
                    )
                )
                .all()
            )

            # Convert to list of tuples to avoid session dependency
            artist_data_list = [
                (artist.id, artist.name) for artist in artists_without_thumbnails
            ]

        missing_count = len(artist_data_list)
        updated_count = 0

        logger.info(
            f"Starting thumbnail scan for {missing_count} artists without thumbnails"
        )

        for artist_id, artist_name in artist_data_list:
            try:
                thumbnail_url = None
                source = None

                # Try IMVDb first
                try:
                    artist_data = imvdb_service.search_artist(artist_name)
                    if artist_data and "image" in artist_data:
                        image_data = artist_data["image"]
                        if isinstance(image_data, dict):
                            thumbnail_url = (
                                image_data.get("o")
                                or image_data.get("l")
                                or image_data.get("b")
                                or image_data.get("m")
                                or image_data.get("s")
                            )
                        elif (
                            isinstance(image_data, str)
                            and image_data != "https://imvdb.com/"
                        ):
                            thumbnail_url = image_data

                        if thumbnail_url:
                            source = "IMVDb"
                except Exception as imvdb_e:
                    logger.warning(f"IMVDb search failed for {artist_name}: {imvdb_e}")

                # If IMVDb didn't work, try Wikipedia
                if not thumbnail_url:
                    try:
                        thumbnail_url = wikipedia_service.search_artist_thumbnail(
                            artist_name
                        )
                        if thumbnail_url:
                            source = "Wikipedia"
                    except Exception as wiki_e:
                        logger.warning(
                            f"Wikipedia search failed for {artist_name}: {wiki_e}"
                        )

                # If we found a thumbnail, download and save it
                if thumbnail_url and source:
                    try:
                        downloaded_path = thumbnail_service.download_artist_thumbnail(
                            artist_name, thumbnail_url
                        )

                        if downloaded_path and os.path.exists(downloaded_path):
                            # Update artist with new thumbnail in a fresh session
                            with get_db() as session:
                                artist = (
                                    session.query(Artist)
                                    .filter_by(id=artist_id)
                                    .first()
                                )
                                if artist:
                                    artist.thumbnail_url = thumbnail_url
                                    artist.thumbnail_path = downloaded_path
                                    artist.updated_at = datetime.utcnow()
                                    session.commit()
                                    updated_count += 1
                                    logger.info(
                                        f"Found and downloaded thumbnail for {artist_name} from {source}"
                                    )

                    except Exception as download_e:
                        logger.warning(
                            f"Failed to download thumbnail for {artist_name}: {download_e}"
                        )

            except Exception as artist_e:
                logger.warning(f"Error processing artist {artist_name}: {artist_e}")
                continue

        logger.info(
            f"Thumbnail scan completed: {updated_count}/{missing_count} artists updated"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "missing_count": missing_count,
                    "updated_count": updated_count,
                    "message": f"Scan completed! Found thumbnails for {updated_count} out of {missing_count} artists.",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to scan missing thumbnails: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-thumbnail-scan", methods=["POST"])
def bulk_thumbnail_scan():
    """Scan thumbnails for specific artist IDs"""
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids required"}), 400

        artist_ids = data["artist_ids"]
        if not isinstance(artist_ids, list) or not artist_ids:
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        # Get artist data for the specified IDs
        artist_data_list = []
        with get_db() as session:
            artists = (
                session.query(Artist.id, Artist.name)
                .filter(Artist.id.in_(artist_ids))
                .all()
            )

            # Convert to list of tuples to avoid session dependency
            artist_data_list = [(artist.id, artist.name) for artist in artists]

        scanned_count = len(artist_data_list)
        found_count = 0

        logger.info(f"Starting bulk thumbnail scan for {scanned_count} artists")

        for artist_id, artist_name in artist_data_list:
            try:
                thumbnail_url = None
                source = None

                # Try IMVDb first
                try:
                    artist_data = imvdb_service.search_artist(artist_name)
                    if artist_data and "image" in artist_data:
                        image_data = artist_data["image"]
                        if isinstance(image_data, dict):
                            thumbnail_url = (
                                image_data.get("o")
                                or image_data.get("l")
                                or image_data.get("m")
                                or image_data.get("s")
                            )
                        elif isinstance(image_data, str):
                            thumbnail_url = image_data

                        if thumbnail_url:
                            source = "IMVDb"
                except Exception as e:
                    logger.debug(f"IMVDb search failed for {artist_name}: {e}")

                # Update artist if thumbnail found
                if thumbnail_url:
                    with get_db() as session:
                        artist = session.query(Artist).filter_by(id=artist_id).first()
                        if artist:
                            artist.thumbnail_url = thumbnail_url
                            session.commit()
                            found_count += 1
                            logger.info(
                                f"Updated thumbnail for {artist_name} from {source}"
                            )

            except Exception as e:
                logger.error(
                    f"Error scanning thumbnail for artist {artist_id} ({artist_name}): {e}"
                )
                continue

        logger.info(
            f"Bulk thumbnail scan completed: {found_count}/{scanned_count} thumbnails found"
        )

        return jsonify(
            {
                "success": True,
                "scanned_count": scanned_count,
                "found_count": found_count,
                "message": f"Found thumbnails for {found_count} out of {scanned_count} artists",
            }
        )

    except Exception as e:
        logger.error(f"Failed to bulk scan thumbnails: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>", methods=["DELETE"])
def delete_artist(artist_id):
    """Remove/delete individual artist"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name  # Store for logging

            # Get related data counts for confirmation
            video_count = session.query(Video).filter_by(artist_id=artist_id).count()
            download_count = (
                session.query(Download)
                .join(Video)
                .filter(Video.artist_id == artist_id)
                .count()
            )

            # Check if force delete is requested
            force_delete = request.args.get("force", "false").lower() in [
                "true",
                "1",
                "yes",
            ]

            if (video_count > 0 or download_count > 0) and not force_delete:
                return (
                    jsonify(
                        {
                            "error": "Artist has associated videos or downloads",
                            "details": {
                                "video_count": video_count,
                                "download_count": download_count,
                                "message": "Use force=true parameter to delete anyway",
                            },
                        }
                    ),
                    409,
                )

            # Remove thumbnail file if exists
            if artist.thumbnail_path and os.path.exists(artist.thumbnail_path):
                try:
                    os.remove(artist.thumbnail_path)
                    logger.info(f"Removed thumbnail file: {artist.thumbnail_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove thumbnail file: {e}")

            # Delete related data if force delete
            if force_delete:
                # Use a safer approach - delete records individually to avoid join issues

                # First get all video IDs for this artist
                video_records = (
                    session.query(Video).filter_by(artist_id=artist_id).all()
                )
                video_ids = [v.id for v in video_records]

                downloads_deleted = 0
                videos_deleted = 0

                if video_ids:
                    # Delete downloads one by one to avoid query join issues
                    for video_id in video_ids:
                        download_count = (
                            session.query(Download)
                            .filter_by(video_id=video_id)
                            .delete()
                        )
                        downloads_deleted += download_count

                    # Delete videos one by one
                    for video_record in video_records:
                        session.delete(video_record)
                        videos_deleted += 1

                logger.info(
                    f"Force delete: removed {videos_deleted} videos and {downloads_deleted} downloads"
                )

            # Delete the artist
            session.delete(artist)
            session.commit()

            logger.info(f"Deleted artist: {artist_name} (ID: {artist_id})")

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f'Artist "{artist_name}" deleted successfully',
                        "deleted_data": {
                            "artist_id": artist_id,
                            "artist_name": artist_name,
                            "videos_deleted": video_count if force_delete else 0,
                            "downloads_deleted": download_count if force_delete else 0,
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to delete artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/merge", methods=["POST"])
def merge_artists(artist_id):
    """Merge two artists with duplicate IMVDb ID"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data is required"}), 400

        target_artist_id = data.get("target_artist_id")
        if not target_artist_id:
            return jsonify({"error": "target_artist_id is required"}), 400

        with get_db() as session:
            # Get both artists
            source_artist = session.query(Artist).filter_by(id=artist_id).first()
            target_artist = session.query(Artist).filter_by(id=target_artist_id).first()

            if not source_artist:
                return jsonify({"error": "Source artist not found"}), 404

            if not target_artist:
                return jsonify({"error": "Target artist not found"}), 404

            if source_artist.id == target_artist.id:
                return jsonify({"error": "Cannot merge artist with itself"}), 400

            # Collect stats before merge
            source_videos = (
                session.query(Video).filter_by(artist_id=source_artist.id).all()
            )
            source_downloads = (
                session.query(Download).filter_by(artist_id=source_artist.id).all()
            )

            stats = {
                "source_artist": {
                    "name": source_artist.name,
                    "video_count": len(source_videos),
                    "download_count": len(source_downloads),
                },
                "target_artist": {
                    "name": target_artist.name,
                    "video_count": len(target_artist.videos),
                    "download_count": len(target_artist.downloads),
                },
            }

            # Transfer videos from source to target
            videos_transferred = 0
            for video in source_videos:
                # Check for duplicate titles to avoid conflicts
                existing_video = (
                    session.query(Video)
                    .filter(
                        Video.artist_id == target_artist.id, Video.title == video.title
                    )
                    .first()
                )

                if existing_video:
                    # If duplicate title exists, append source artist name to distinguish
                    video.title = f"{video.title} ({source_artist.name})"

                video.artist_id = target_artist.id
                videos_transferred += 1

            # Transfer downloads from source to target
            downloads_transferred = 0
            for download in source_downloads:
                download.artist_id = target_artist.id
                downloads_transferred += 1

            # Merge metadata - prefer target artist but update with source data if target is missing
            merged_changes = []

            if not target_artist.imvdb_id and source_artist.imvdb_id:
                target_artist.imvdb_id = source_artist.imvdb_id
                merged_changes.append("IMVDb ID")

            if not target_artist.thumbnail_url and source_artist.thumbnail_url:
                target_artist.thumbnail_url = source_artist.thumbnail_url
                target_artist.thumbnail_path = source_artist.thumbnail_path
                merged_changes.append("thumbnail")

            # Merge keywords
            if source_artist.keywords:
                target_keywords = set(target_artist.keywords or [])
                source_keywords = set(source_artist.keywords)
                combined_keywords = list(target_keywords.union(source_keywords))
                if len(combined_keywords) > len(target_artist.keywords or []):
                    target_artist.keywords = combined_keywords
                    merged_changes.append("keywords")

            # Update monitoring status (OR operation - if either is monitored, target should be monitored)
            if source_artist.monitored and not target_artist.monitored:
                target_artist.monitored = True
                merged_changes.append("monitoring status")

            # Update auto-download status (OR operation)
            if source_artist.auto_download and not target_artist.auto_download:
                target_artist.auto_download = True
                merged_changes.append("auto-download")

            # Remove source artist thumbnail file if different from target
            if (
                source_artist.thumbnail_path
                and source_artist.thumbnail_path != target_artist.thumbnail_path
                and os.path.exists(source_artist.thumbnail_path)
            ):
                try:
                    os.remove(source_artist.thumbnail_path)
                    logger.info(
                        f"Removed source artist thumbnail: {source_artist.thumbnail_path}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to remove source thumbnail: {e}")

            # Update target artist timestamp
            target_artist.updated_at = datetime.utcnow()

            # Delete the source artist (now empty)
            source_artist_name = source_artist.name
            session.delete(source_artist)

            session.commit()

            logger.info(
                f"Merged artist '{source_artist_name}' into '{target_artist.name}': "
                f"{videos_transferred} videos, {downloads_transferred} downloads transferred"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f'Successfully merged "{source_artist_name}" into "{target_artist.name}"',
                        "merge_stats": {
                            "videos_transferred": videos_transferred,
                            "downloads_transferred": downloads_transferred,
                            "metadata_merged": merged_changes,
                            "before": stats,
                            "after": {
                                "name": target_artist.name,
                                "video_count": len(target_artist.videos),
                                "download_count": len(target_artist.downloads),
                                "imvdb_id": target_artist.imvdb_id,
                            },
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to merge artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/metadata/update", methods=["PUT"])
def update_artist_metadata_from_imvdb(artist_id):
    """Update individual artist metadata from IMVDb"""
    try:
        # Check if IMVDb API key is configured before proceeding
        from src.services.settings_service import SettingsService

        SettingsService.reload_cache()
        api_key = SettingsService.get("imvdb_api_key", "")

        if not api_key:
            logger.warning("IMVDb API key not configured for metadata update")
            return (
                jsonify(
                    {
                        "error": "IMVDb API key not configured",
                        "message": "Please configure your IMVDb API key in Settings to use this feature",
                        "action": "Go to Settings > External Services and add your IMVDb API key",
                        "help_url": "https://imvdb.com/developers/api",
                    }
                ),
                400,
            )

        # First, get the artist data we need before any external calls
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name
            existing_imvdb_id = artist.imvdb_id
            existing_thumbnail_url = artist.thumbnail_url
            existing_thumbnail_path = artist.thumbnail_path

        logger.info(f"Updating artist metadata from IMVDb for: {artist_name}")

        # Make external API calls outside of any session context
        artist_data = None

        if existing_imvdb_id:
            # Try to get by existing IMVDb ID first
            artist_data = imvdb_service.get_artist(str(existing_imvdb_id))
            if not artist_data:
                logger.warning(
                    f"Artist not found by existing IMVDb ID {existing_imvdb_id}, trying name search"
                )

        if not artist_data:
            # Search by name
            artist_data = imvdb_service.search_artist(artist_name)

        if not artist_data:
            return (
                jsonify(
                    {
                        "error": "Artist not found on IMVDb",
                        "message": f'No metadata available for "{artist_name}". This artist may not exist in IMVDb\'s database or may have a different name.',
                        "suggestion": 'Try searching for the artist without suffixes like "VEVO" or "Official" if they are YouTube channel names.',
                        "help_url": "https://imvdb.com/search",
                    }
                ),
                404,
            )

        # Process thumbnail outside of session if needed
        thumbnail_url = None
        new_thumbnail_path = existing_thumbnail_path

        if "image" in artist_data:
            image_data = artist_data["image"]
            if isinstance(image_data, dict):
                # Prefer larger images: o (original) > l (large) > b (big) > m (medium) > s (small)
                thumbnail_url = (
                    image_data.get("o")
                    or image_data.get("l")
                    or image_data.get("b")
                    or image_data.get("m")
                    or image_data.get("s")
                )
                if thumbnail_url:
                    logger.debug(
                        f"Found valid thumbnail URL from IMVDb image dict: {thumbnail_url}"
                    )
                else:
                    logger.debug(
                        f"No valid thumbnail URLs found in IMVDb image dict: {image_data}"
                    )
            elif isinstance(image_data, str) and image_data != "https://imvdb.com/":
                thumbnail_url = image_data
                logger.debug(f"Found valid thumbnail URL from IMVDb: {thumbnail_url}")
            elif isinstance(image_data, str):
                logger.info(f"Skipped invalid IMVDb thumbnail URL: {image_data}")
            else:
                logger.debug(
                    f"Unknown image data format from IMVDb: {type(image_data)}"
                )
        else:
            logger.debug(f"No image field in IMVDb artist data for {artist_name}")

        # Download thumbnail if needed (outside session)
        if thumbnail_url and thumbnail_url != existing_thumbnail_url:
            try:
                logger.info(
                    f"Downloading new thumbnail for {artist_name}: {thumbnail_url}"
                )
                downloaded_path = thumbnail_service.download_artist_thumbnail(
                    artist_name, thumbnail_url
                )

                if downloaded_path and os.path.exists(downloaded_path):
                    # Remove old thumbnail if exists
                    if existing_thumbnail_path and os.path.exists(
                        existing_thumbnail_path
                    ):
                        try:
                            os.remove(existing_thumbnail_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove old thumbnail: {e}")

                    new_thumbnail_path = downloaded_path
                    logger.info(f"Successfully updated thumbnail for {artist_name}")
                else:
                    logger.warning(f"Failed to download thumbnail for {artist_name}")
            except Exception as e:
                logger.warning(f"Failed to update thumbnail: {e}")
                thumbnail_url = (
                    existing_thumbnail_url  # Keep existing URL if download failed
                )
        elif thumbnail_url == existing_thumbnail_url:
            logger.debug(f"Thumbnail URL unchanged for {artist_name}: {thumbnail_url}")
        else:
            logger.info(
                f"No valid thumbnail URL available for {artist_name} from IMVDb, trying Wikipedia fallback"
            )

            # Try Wikipedia as fallback source
            try:
                wiki_thumbnail_url = wikipedia_service.search_artist_thumbnail(
                    artist_name
                )
                if wiki_thumbnail_url and wiki_thumbnail_url != existing_thumbnail_url:
                    try:
                        logger.info(
                            f"Downloading Wikipedia thumbnail for {artist_name}: {wiki_thumbnail_url}"
                        )
                        downloaded_path = thumbnail_service.download_artist_thumbnail(
                            artist_name, wiki_thumbnail_url
                        )

                        if downloaded_path and os.path.exists(downloaded_path):
                            # Remove old thumbnail if exists
                            if existing_thumbnail_path and os.path.exists(
                                existing_thumbnail_path
                            ):
                                try:
                                    os.remove(existing_thumbnail_path)
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to remove old thumbnail: {e}"
                                    )

                            new_thumbnail_path = downloaded_path
                            thumbnail_url = wiki_thumbnail_url
                            logger.info(
                                f"Successfully updated thumbnail for {artist_name} from Wikipedia"
                            )
                        else:
                            logger.warning(
                                f"Failed to download Wikipedia thumbnail for {artist_name}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to download Wikipedia thumbnail: {e}")
                elif wiki_thumbnail_url == existing_thumbnail_url:
                    logger.debug(
                        f"Wikipedia thumbnail URL unchanged for {artist_name}: {wiki_thumbnail_url}"
                    )
                else:
                    logger.info(f"No thumbnail found on Wikipedia for {artist_name}")
            except Exception as e:
                logger.warning(
                    f"Wikipedia thumbnail search failed for {artist_name}: {e}"
                )

        # Now update the database with a fresh session
        with get_db() as session:
            updated_fields = []

            # Prepare update data
            update_data = {
                "imvdb_metadata": artist_data,
                "updated_at": datetime.utcnow(),
            }

            # Add IMVDb ID if different
            new_imvdb_id = artist_data.get("id")
            if new_imvdb_id and existing_imvdb_id != new_imvdb_id:
                update_data["imvdb_id"] = new_imvdb_id
                updated_fields.append("imvdb_id")

            # Add thumbnail fields if updated
            if thumbnail_url and thumbnail_url != existing_thumbnail_url:
                update_data["thumbnail_url"] = thumbnail_url
                update_data["thumbnail_path"] = new_thumbnail_path
                updated_fields.append("thumbnail")

            updated_fields.append("metadata")

            # Perform the update
            try:
                session.query(Artist).filter_by(id=artist_id).update(update_data)
                session.commit()

                # Get the updated artist for response
                updated_artist = session.query(Artist).filter_by(id=artist_id).first()
            except IntegrityError as e:
                session.rollback()

                # Check if this is a duplicate IMVDb ID error
                if "imvdb_id" in str(e) and "Duplicate entry" in str(e):
                    # Find the conflicting artist
                    conflicting_artist = (
                        session.query(Artist).filter_by(imvdb_id=new_imvdb_id).first()
                    )

                    if conflicting_artist:
                        return (
                            jsonify(
                                {
                                    "error": "duplicate_imvdb_id",
                                    "message": f"IMVDb ID {new_imvdb_id} is already assigned to another artist",
                                    "current_artist": {
                                        "id": artist_id,
                                        "name": artist_name,
                                    },
                                    "conflicting_artist": {
                                        "id": conflicting_artist.id,
                                        "name": conflicting_artist.name,
                                    },
                                    "imvdb_id": new_imvdb_id,
                                    "merge_required": True,
                                    "merge_suggestion": f'You may want to merge "{artist_name}" with "{conflicting_artist.name}" since they share the same IMVDb ID',
                                }
                            ),
                            409,
                        )
                    else:
                        # Generic duplicate error
                        return (
                            jsonify(
                                {
                                    "error": "duplicate_constraint",
                                    "message": "A database constraint was violated during the update",
                                    "details": str(e),
                                }
                            ),
                            409,
                        )
                else:
                    # Re-raise other integrity errors
                    raise e

            logger.info(
                f"Updated metadata for artist {artist_name}, fields: {updated_fields}"
            )

            # Return updated artist data
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f'Metadata updated successfully for "{artist_name}"',
                        "updated_fields": updated_fields,
                        "artist": {
                            "id": updated_artist.id,
                            "name": updated_artist.name,
                            "imvdb_id": updated_artist.imvdb_id,
                            "thumbnail_url": updated_artist.thumbnail_url,
                            "thumbnail_path": updated_artist.thumbnail_path,
                            "imvdb_metadata": updated_artist.imvdb_metadata,
                            "updated_at": updated_artist.updated_at.isoformat(),
                        },
                        "imvdb_data": {
                            "name": artist_data.get("name"),
                            "slug": artist_data.get("slug"),
                            "bio": artist_data.get("bio"),
                            "formed_year": artist_data.get("formed_year"),
                            "origin_country": artist_data.get("origin_country"),
                            "genres": artist_data.get("genres", []),
                            "verified": artist_data.get("verified", False),
                            "artist_video_count": artist_data.get(
                                "artist_video_count", 0
                            ),
                            "featured_video_count": artist_data.get(
                                "featured_video_count", 0
                            ),
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to update artist metadata from IMVDb: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-edit", methods=["POST"])
def bulk_edit_artists():
    """Update multiple artists with bulk changes"""
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data or "updates" not in data:
            return jsonify({"error": "artist_ids and updates required"}), 400

        artist_ids = data["artist_ids"]
        updates = data["updates"]

        if not isinstance(artist_ids, list) or not artist_ids:
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        updated_count = 0

        with get_db() as session:
            # Get artists to update
            artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()

            for artist in artists:
                # Update monitoring status
                if "monitored" in updates:
                    artist.monitored = updates["monitored"]

                # Update auto-download
                if "auto_download" in updates:
                    artist.auto_download = updates["auto_download"]

                # Update keywords
                if "keywords" in updates:
                    artist.keywords = updates["keywords"]

                updated_count += 1

            session.commit()

            logger.info(f"Bulk updated {updated_count} artists")

            return jsonify({"updated_count": updated_count, "error": None}), 200

    except Exception as e:
        logger.error(f"Failed to bulk update artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete_artists():
    """Delete multiple artists"""
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids required"}), 400

        artist_ids = data["artist_ids"]
        if not isinstance(artist_ids, list) or not artist_ids:
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        deleted_count = 0
        deleted_names = []

        with get_db() as session:
            # Get artist names before deletion for logging
            artists_to_delete = (
                session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
            )

            for artist in artists_to_delete:
                artist_name = artist.name
                artist_id = artist.id

                try:
                    # Delete associated downloads first
                    session.query(Download).filter_by(artist_id=artist_id).delete()

                    # Delete associated videos
                    session.query(Video).filter_by(artist_id=artist_id).delete()

                    # Delete the artist
                    session.delete(artist)

                    deleted_names.append(artist_name)
                    deleted_count += 1
                    logger.info(f"Deleted artist: {artist_name} (ID: {artist_id})")

                except Exception as e:
                    logger.error(
                        f"Failed to delete artist {artist_name} (ID: {artist_id}): {e}"
                    )
                    # Continue with other deletions
                    continue

            session.commit()

            return (
                jsonify(
                    {
                        "success": True,
                        "deleted_count": deleted_count,
                        "deleted_artists": deleted_names,
                        "message": f"Successfully deleted {deleted_count} artist(s)",
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to bulk delete artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-validate-metadata", methods=["POST"])
def bulk_validate_metadata():
    """Validate metadata for multiple artists"""
    try:
        logger.info("Starting bulk metadata validation")

        # Validate request data
        data = request.get_json()
        if not data:
            logger.warning("No JSON data received in request")
            return jsonify({"error": "No data provided"}), 400

        if "artist_ids" not in data:
            logger.warning("Missing artist_ids in request data")
            return jsonify({"error": "artist_ids required"}), 400

        artist_ids = data["artist_ids"]
        if not isinstance(artist_ids, list) or not artist_ids:
            logger.warning(f"Invalid artist_ids provided: {artist_ids}")
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        logger.info(f"Processing validation for {len(artist_ids)} artists")

        # Check if IMVDb API key is configured
        try:
            SettingsService.reload_cache()
            api_key = SettingsService.get("imvdb_api_key", "")
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            return jsonify({"error": "Failed to load configuration"}), 500

        if not api_key:
            logger.warning("IMVDb API key not configured")
            return (
                jsonify(
                    {
                        "error": "IMVDb API key not configured",
                        "message": "Please configure your IMVDb API key in Settings to use this feature",
                    }
                ),
                400,
            )

        validation_issues = []
        validated_count = 0

        try:
            with get_db() as session:
                logger.info("Database session opened successfully")

                # Fetch artists from database
                artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
                logger.info(f"Found {len(artists)} artists in database")

                for artist in artists:
                    validated_count += 1
                    issues = []

                    # Check for missing IMVDb ID
                    if not artist.imvdb_id:
                        issues.append("Missing IMVDb ID")

                    # Check for missing thumbnail
                    if not artist.thumbnail_url and not artist.thumbnail_path:
                        issues.append("Missing thumbnail")

                    # Check for minimal metadata (can be expanded)
                    if not artist.bio or artist.bio.strip() == "":
                        issues.append("Missing biography")

                    # Check if IMVDb ID is accessible (basic validation)
                    if artist.imvdb_id:
                        try:
                            # Quick validation - check if IMVDb ID is valid format
                            if not str(artist.imvdb_id).isdigit():
                                issues.append("Invalid IMVDb ID format")
                        except Exception:
                            issues.append("Invalid IMVDb ID")

                    # Add to validation issues if any problems found
                    if issues:
                        validation_issues.append(
                            {
                                "artist_id": artist.id,
                                "artist_name": artist.name,
                                "issues": issues,
                            }
                        )

        except Exception as e:
            logger.error(f"Database error during validation: {e}")
            return jsonify({"error": f"Database error: {str(e)}"}), 500

        logger.info(
            f"Validation complete: {validated_count} artists validated, {len(validation_issues)} issues found"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "validated_count": validated_count,
                    "validation_issues": validation_issues,
                    "issues_count": len(validation_issues),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk validate metadata: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-organize-folders", methods=["POST"])
def bulk_organize_folders():
    """Organize folder paths for multiple artists"""
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids required"}), 400

        artist_ids = data["artist_ids"]
        if not isinstance(artist_ids, list) or not artist_ids:
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        organized_count = 0
        organized_artists = []

        with get_db() as session:
            artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()

            for artist in artists:
                old_folder_path = artist.folder_path

                # Use the existing ensure_artist_folder_path function
                new_folder_path = ensure_artist_folder_path(artist, session)

                if old_folder_path != new_folder_path:
                    organized_count += 1
                    organized_artists.append(
                        {
                            "artist_id": artist.id,
                            "artist_name": artist.name,
                            "old_folder_path": old_folder_path,
                            "new_folder_path": new_folder_path,
                        }
                    )
                    logger.info(
                        f"Organized folder path for {artist.name}: '{old_folder_path}' -> '{new_folder_path}'"
                    )
                else:
                    # Even if no change, still count as processed
                    organized_count += 1

            # Commit all changes at once
            session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "organized_count": organized_count,
                    "organized_artists": organized_artists,
                    "message": f"Successfully organized folders for {organized_count} artist(s)",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk organize folders: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/bulk-imvdb-link", methods=["POST"])
def bulk_imvdb_link():
    """Link multiple artists to IMVDb entries"""
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids required"}), 400

        artist_ids = data["artist_ids"]
        if not isinstance(artist_ids, list) or not artist_ids:
            return jsonify({"error": "artist_ids must be a non-empty list"}), 400

        # Check if IMVDb API key is configured
        SettingsService.reload_cache()
        api_key = SettingsService.get("imvdb_api_key", "")

        if not api_key:
            return (
                jsonify(
                    {
                        "error": "IMVDb API key not configured",
                        "message": "Please configure your IMVDb API key in Settings to use this feature",
                    }
                ),
                400,
            )

        linked_count = 0
        linked_artists = []
        errors = []

        with get_db() as session:
            artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()

            for artist in artists:
                try:
                    # Skip if already has IMVDb ID
                    if artist.imvdb_id:
                        continue

                    # Try to find IMVDb match
                    imvdb_data = imvdb_service.search_artist(artist.name)
                    if imvdb_data and len(imvdb_data) > 0:
                        # Use the first match
                        match = imvdb_data[0]
                        artist.imvdb_id = match.get("id")

                        # Update additional metadata if available
                        if match.get("url"):
                            artist.imvdb_url = match["url"]
                        if match.get("image") and not artist.thumbnail_url:
                            artist.thumbnail_url = match["image"]

                        linked_count += 1
                        linked_artists.append(
                            {
                                "artist_id": artist.id,
                                "artist_name": artist.name,
                                "imvdb_id": artist.imvdb_id,
                                "imvdb_url": artist.imvdb_url,
                            }
                        )
                        logger.info(
                            f"Linked artist {artist.name} to IMVDb ID: {artist.imvdb_id}"
                        )
                    else:
                        errors.append(
                            {
                                "artist_id": artist.id,
                                "artist_name": artist.name,
                                "error": "No IMVDb match found",
                            }
                        )

                except Exception as e:
                    logger.error(f"Failed to link artist {artist.name} to IMVDb: {e}")
                    errors.append(
                        {
                            "artist_id": artist.id,
                            "artist_name": artist.name,
                            "error": str(e),
                        }
                    )

            session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "linked_count": linked_count,
                    "linked_artists": linked_artists,
                    "errors": errors,
                    "message": f"Successfully linked {linked_count} artist(s) to IMVDb",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to bulk link artists to IMVDb: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/cleanup-zero-videos", methods=["POST"])
def cleanup_artists_with_zero_videos():
    """Delete all artists with 0 videos associated"""
    try:
        with get_db() as session:
            # Find artists with 0 videos using a subquery
            video_count_subquery = (
                session.query(
                    Artist.id.label("artist_id"),
                    func.count(Video.id).label("video_count"),
                )
                .outerjoin(Video, Artist.id == Video.artist_id)
                .group_by(Artist.id)
                .subquery()
            )

            artists_with_zero_videos = (
                session.query(Artist)
                .join(
                    video_count_subquery, Artist.id == video_count_subquery.c.artist_id
                )
                .filter(video_count_subquery.c.video_count == 0)
                .all()
            )

            if not artists_with_zero_videos:
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "No artists with 0 videos found",
                            "deleted_count": 0,
                            "deleted_artists": [],
                        }
                    ),
                    200,
                )

            deleted_names = []
            deleted_count = 0

            for artist in artists_with_zero_videos:
                # Store values we need before operations (capture outside try block)
                artist_name = artist.name
                thumbnail_path = artist.thumbnail_path

                try:
                    # Remove thumbnail files if they exist
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        os.remove(thumbnail_path)
                        logger.info(f"Deleted thumbnail file: {thumbnail_path}")

                    deleted_names.append(artist_name)
                    session.delete(artist)
                    deleted_count += 1
                    logger.info(f"Deleted artist with 0 videos: {artist_name}")

                except Exception as e:
                    logger.error(f"Failed to delete artist {artist_name}: {e}")
                    continue

            session.commit()

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Successfully deleted {deleted_count} artists with 0 videos",
                        "deleted_count": deleted_count,
                        "deleted_artists": deleted_names,
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to cleanup artists with zero videos: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/merge", methods=["POST"])
def merge_multiple_artists():
    """Merge multiple artists into one primary artist"""
    try:
        data = request.get_json()
        if (
            not data
            or "primary_artist_id" not in data
            or "secondary_artist_ids" not in data
        ):
            return (
                jsonify(
                    {"error": "primary_artist_id and secondary_artist_ids required"}
                ),
                400,
            )

        primary_artist_id = data["primary_artist_id"]
        secondary_artist_ids = data["secondary_artist_ids"]

        if not isinstance(secondary_artist_ids, list) or not secondary_artist_ids:
            return (
                jsonify({"error": "secondary_artist_ids must be a non-empty list"}),
                400,
            )

        if primary_artist_id in secondary_artist_ids:
            return (
                jsonify(
                    {"error": "primary_artist_id cannot be in secondary_artist_ids"}
                ),
                400,
            )

        with get_db() as session:
            # Get primary artist
            primary_artist = (
                session.query(Artist).filter_by(id=primary_artist_id).first()
            )
            if not primary_artist:
                return jsonify({"error": "Primary artist not found"}), 404

            # Get secondary artists
            secondary_artists = (
                session.query(Artist).filter(Artist.id.in_(secondary_artist_ids)).all()
            )
            if len(secondary_artists) != len(secondary_artist_ids):
                return (
                    jsonify({"error": "One or more secondary artists not found"}),
                    404,
                )

            merged_count = 0
            merged_names = []

            for secondary_artist in secondary_artists:
                try:
                    # First, handle IMVDb ID conflicts by clearing from secondary artist
                    if secondary_artist.imvdb_id:
                        # Always clear secondary artist's IMVDb ID first to avoid any conflicts
                        secondary_imvdb_id = secondary_artist.imvdb_id
                        secondary_imvdb_metadata = secondary_artist.imvdb_metadata
                        secondary_artist.imvdb_id = None
                        secondary_artist.imvdb_metadata = None
                        session.flush()  # Apply the clear immediately
                        logger.info(
                            f"Cleared IMVDb ID {secondary_imvdb_id} from secondary artist {secondary_artist.name}"
                        )

                        # Keep IMVDb data if primary doesn't have it
                        if not primary_artist.imvdb_id:
                            primary_artist.imvdb_id = secondary_imvdb_id
                            primary_artist.imvdb_metadata = secondary_imvdb_metadata
                            logger.info(
                                f"Assigned IMVDb ID {secondary_imvdb_id} to primary artist {primary_artist.name}"
                            )

                    # Move videos from secondary to primary
                    session.query(Video).filter_by(
                        artist_id=secondary_artist.id
                    ).update({"artist_id": primary_artist_id})

                    # Move downloads from secondary to primary
                    session.query(Download).filter_by(
                        artist_id=secondary_artist.id
                    ).update({"artist_id": primary_artist_id})

                    # Merge keywords
                    if secondary_artist.keywords:
                        primary_keywords = set(primary_artist.keywords or [])
                        secondary_keywords = set(secondary_artist.keywords)
                        merged_keywords = list(
                            primary_keywords.union(secondary_keywords)
                        )
                        primary_artist.keywords = merged_keywords

                    # Keep the better thumbnail if primary doesn't have one
                    if (
                        not primary_artist.thumbnail_url
                        and secondary_artist.thumbnail_url
                    ):
                        primary_artist.thumbnail_url = secondary_artist.thumbnail_url
                        primary_artist.thumbnail_path = secondary_artist.thumbnail_path

                    # Update monitoring settings (keep most permissive)
                    if secondary_artist.monitored and not primary_artist.monitored:
                        primary_artist.monitored = True

                    if (
                        secondary_artist.auto_download
                        and not primary_artist.auto_download
                    ):
                        primary_artist.auto_download = True

                    # Delete the secondary artist
                    session.delete(secondary_artist)

                    merged_names.append(secondary_artist.name)
                    merged_count += 1
                    logger.info(
                        f"Merged artist {secondary_artist.name} into {primary_artist.name}"
                    )

                except Exception as e:
                    logger.error(f"Failed to merge artist {secondary_artist.name}: {e}")
                    # Continue with other merges
                    continue

            # Update primary artist's updated_at timestamp
            primary_artist.updated_at = datetime.utcnow()

            session.commit()

            return (
                jsonify(
                    {
                        "success": True,
                        "merged_count": merged_count,
                        "merged_artists": merged_names,
                        "primary_artist_name": primary_artist.name,
                        "primary_artist_id": primary_artist.id,
                        "message": f"Successfully merged {merged_count} artist(s) into {primary_artist.name}",
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to merge artists: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/import-metadata", methods=["POST"])
def import_artist_metadata(artist_id):
    """
    Import/update artist metadata from IMVDb and YouTube

    This is a convenience endpoint that provides enhanced metadata retrieval
    as requested in Issue #18. It calls the existing comprehensive metadata
    update functionality.
    """
    try:
        # Simply call the existing comprehensive metadata update function
        return update_artist_metadata_from_imvdb(artist_id)

    except Exception as e:
        logger.error(f"Failed to import metadata for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/navigation", methods=["GET"])
def get_artist_navigation(artist_id):
    """Get navigation info for next/previous artist in sorted list"""
    try:
        with get_db() as session:
            # Get current artist
            current_artist = session.query(Artist).filter_by(id=artist_id).first()
            if not current_artist:
                return jsonify({"error": "Artist not found"}), 404

            # Get sort parameters (default to name ascending)
            sort_by = request.args.get("sort", "name")
            sort_order = request.args.get("order", "asc")

            # Build base query with video count subquery for sorting
            video_count_subquery = (
                session.query(
                    Video.artist_id, func.count(Video.id).label("video_count")
                )
                .group_by(Video.artist_id)
                .subquery()
            )

            query = (
                session.query(Artist)
                .outerjoin(
                    video_count_subquery, Artist.id == video_count_subquery.c.artist_id
                )
                .add_columns(
                    func.coalesce(video_count_subquery.c.video_count, 0).label(
                        "video_count"
                    )
                )
            )

            # Apply sorting
            if sort_by == "name":
                sort_column = Artist.name
            elif sort_by == "created_at":
                sort_column = Artist.created_at
            elif sort_by == "updated_at":
                sort_column = Artist.updated_at
            elif sort_by == "video_count":
                sort_column = func.coalesce(video_count_subquery.c.video_count, 0)
            else:
                sort_column = Artist.name

            # Determine sort direction
            if sort_order.lower() == "desc":
                sort_column = desc(sort_column)

            # Get all artists sorted
            all_artists = query.order_by(sort_column).all()

            # Find current artist position
            current_position = None
            for i, (artist, video_count) in enumerate(all_artists):
                if artist.id == artist_id:
                    current_position = i
                    break

            if current_position is None:
                return jsonify({"error": "Artist not found in sorted list"}), 404

            # Get previous and next artists
            prev_artist = None
            next_artist = None

            if current_position > 0:
                prev_artist_data, prev_video_count = all_artists[current_position - 1]
                prev_artist = {
                    "id": prev_artist_data.id,
                    "name": prev_artist_data.name,
                    "video_count": prev_video_count or 0,
                }

            if current_position < len(all_artists) - 1:
                next_artist_data, next_video_count = all_artists[current_position + 1]
                next_artist = {
                    "id": next_artist_data.id,
                    "name": next_artist_data.name,
                    "video_count": next_video_count or 0,
                }

            return (
                jsonify(
                    {
                        "current_artist": {
                            "id": current_artist.id,
                            "name": current_artist.name,
                            "position": current_position + 1,
                            "total_artists": len(all_artists),
                        },
                        "prev_artist": prev_artist,
                        "next_artist": next_artist,
                        "navigation": {
                            "has_prev": prev_artist is not None,
                            "has_next": next_artist is not None,
                            "sort_by": sort_by,
                            "sort_order": sort_order,
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get artist navigation for {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


# Enhanced Thumbnail Management Endpoints


@artists_bp.route("/<int:artist_id>/thumbnail/upload", methods=["POST"])
def upload_artist_thumbnail(artist_id):
    """Upload a manual thumbnail for an artist"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Check if file was uploaded
            if "thumbnail" not in request.files:
                return jsonify({"error": "No thumbnail file provided"}), 400

            file = request.files["thumbnail"]
            if file.filename == "":
                return jsonify({"error": "No file selected"}), 400

            # Validate file type
            allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                return (
                    jsonify(
                        {
                            "error": f"Invalid file type. Allowed: {list(allowed_extensions)}"
                        }
                    ),
                    400,
                )

            # Validate file size (max 10MB)
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning

            if file_size > 10 * 1024 * 1024:  # 10MB
                return jsonify({"error": "File too large. Maximum size is 10MB"}), 400

            # Read file data
            file_data = file.read()

            # Store current thumbnail info for cleanup
            old_thumbnail_path = artist.thumbnail_path
            old_thumbnail_metadata = artist.thumbnail_metadata

            # Upload and process the thumbnail
            upload_result = thumbnail_service.upload_manual_thumbnail(
                file_data=file_data,
                filename=secure_filename(file.filename),
                entity_type="artist",
                entity_id=artist_id,
                entity_name=artist.name,
            )

            if not upload_result:
                return jsonify({"error": "Failed to process thumbnail"}), 500

            # Clean up old thumbnail files if they exist
            if old_thumbnail_path and old_thumbnail_metadata:
                thumbnail_service.delete_thumbnail_files(
                    old_thumbnail_path, old_thumbnail_metadata
                )
            elif old_thumbnail_path and os.path.exists(old_thumbnail_path):
                try:
                    os.remove(old_thumbnail_path)
                except Exception as e:
                    logger.warning(f"Failed to remove old thumbnail: {e}")

            # Update artist with new thumbnail info
            artist.thumbnail_url = None  # No URL for manual uploads
            artist.thumbnail_path = upload_result["primary_path"]
            artist.thumbnail_source = "manual"
            artist.thumbnail_metadata = upload_result["metadata"]
            artist.thumbnail_uploaded_at = datetime.utcnow()
            artist.updated_at = datetime.utcnow()

            session.commit()

            logger.info(
                f"Successfully uploaded manual thumbnail for artist {artist.name}"
            )

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Thumbnail uploaded successfully for {artist.name}",
                        "thumbnail_path": upload_result["primary_path"],
                        "upload_id": upload_result["upload_id"],
                        "sizes_generated": list(upload_result["all_paths"].keys()),
                        "metadata": upload_result["metadata"],
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to upload artist thumbnail: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail/crop", methods=["POST"])
def crop_artist_thumbnail(artist_id):
    """Crop an existing artist thumbnail"""
    try:
        data = request.get_json()
        if not data or "crop_box" not in data:
            return jsonify({"error": "crop_box is required"}), 400

        crop_box = data["crop_box"]
        if not isinstance(crop_box, list) or len(crop_box) != 4:
            return (
                jsonify({"error": "crop_box must be [left, top, right, bottom]"}),
                400,
            )

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            if not artist.thumbnail_path or not os.path.exists(artist.thumbnail_path):
                return jsonify({"error": "No thumbnail to crop"}), 400

            # Store current thumbnail info for cleanup
            old_thumbnail_path = artist.thumbnail_path
            old_thumbnail_metadata = artist.thumbnail_metadata

            # Determine source image path (use original size if available)
            source_path = artist.thumbnail_path
            if artist.thumbnail_metadata and "sizes" in artist.thumbnail_metadata:
                if "original" in artist.thumbnail_metadata["sizes"]:
                    source_path = artist.thumbnail_metadata["sizes"]["original"]["path"]

            # Crop the thumbnail
            crop_result = thumbnail_service.crop_thumbnail(
                image_path=source_path,
                crop_box=tuple(crop_box),
                entity_type="artist",
                entity_id=artist_id,
                entity_name=artist.name,
            )

            if not crop_result:
                return jsonify({"error": "Failed to crop thumbnail"}), 500

            # Clean up old thumbnail files
            if old_thumbnail_metadata:
                thumbnail_service.delete_thumbnail_files(
                    old_thumbnail_path, old_thumbnail_metadata
                )
            elif old_thumbnail_path and os.path.exists(old_thumbnail_path):
                try:
                    os.remove(old_thumbnail_path)
                except Exception as e:
                    logger.warning(f"Failed to remove old thumbnail: {e}")

            # Update artist with cropped thumbnail
            artist.thumbnail_path = crop_result["primary_path"]
            artist.thumbnail_source = "manual_crop"
            artist.thumbnail_metadata = crop_result["metadata"]
            artist.thumbnail_uploaded_at = datetime.utcnow()
            artist.updated_at = datetime.utcnow()

            session.commit()

            logger.info(f"Successfully cropped thumbnail for artist {artist.name}")

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Thumbnail cropped successfully for {artist.name}",
                        "thumbnail_path": crop_result["primary_path"],
                        "upload_id": crop_result["upload_id"],
                        "crop_box": crop_box,
                        "metadata": crop_result["metadata"],
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to crop artist thumbnail: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail/info", methods=["GET"])
def get_artist_thumbnail_info(artist_id):
    """Get detailed information about an artist's thumbnail"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            thumbnail_info = {
                "has_thumbnail": bool(artist.thumbnail_path or artist.thumbnail_url),
                "thumbnail_url": artist.thumbnail_url,
                "thumbnail_path": artist.thumbnail_path,
                "thumbnail_source": artist.thumbnail_source,
                "thumbnail_uploaded_at": (
                    artist.thumbnail_uploaded_at.isoformat()
                    if artist.thumbnail_uploaded_at
                    else None
                ),
                "metadata": artist.thumbnail_metadata,
                "file_info": None,
            }

            # Get file information if thumbnail exists
            if artist.thumbnail_path:
                file_info = thumbnail_service.get_thumbnail_info(artist.thumbnail_path)
                if file_info:
                    thumbnail_info["file_info"] = file_info

            return jsonify(thumbnail_info), 200

    except Exception as e:
        logger.error(f"Failed to get artist thumbnail info: {e}")
        return jsonify({"error": str(e)}), 500


@artists_bp.route("/<int:artist_id>/thumbnail/<size>", methods=["GET"])
def get_artist_thumbnail_size(artist_id, size):
    """Serve a specific size of artist thumbnail"""
    try:
        # Validate size parameter
        valid_sizes = ["small", "medium", "large", "original"]
        if size not in valid_sizes:
            return jsonify({"error": f"Invalid size. Valid sizes: {valid_sizes}"}), 400

        with get_db() as session:
            artist = session.query(Artist).filter_by(id=artist_id).first()
            if not artist:
                logger.warning(f"Artist {artist_id} not found for thumbnail request")
                return abort(404)

            # Check if we have metadata with size information
            if artist.thumbnail_metadata and "sizes" in artist.thumbnail_metadata:
                if size in artist.thumbnail_metadata["sizes"]:
                    size_path = artist.thumbnail_metadata["sizes"][size]["path"]
                    if os.path.exists(size_path):
                        logger.debug(f"Serving {size} thumbnail: {size_path}")
                        return send_file(size_path, mimetype="image/jpeg")

            # Fallback to primary thumbnail path
            if artist.thumbnail_path and os.path.exists(artist.thumbnail_path):
                logger.debug(
                    f"Serving primary thumbnail as {size}: {artist.thumbnail_path}"
                )
                return send_file(artist.thumbnail_path, mimetype="image/jpeg")

            # If no local thumbnail, try to download from URL if available (for backward compatibility)
            if artist.thumbnail_url:
                try:
                    logger.debug(
                        f"Attempting to download thumbnail from: {artist.thumbnail_url}"
                    )
                    downloaded_path = thumbnail_service.download_artist_thumbnail(
                        artist.name, artist.thumbnail_url
                    )

                    if downloaded_path:
                        artist.thumbnail_path = downloaded_path
                        artist.thumbnail_source = (
                            "imvdb"  # Assume IMVDb for URL downloads
                        )
                        session.commit()
                        logger.debug(
                            f"Downloaded and serving thumbnail: {downloaded_path}"
                        )
                        return send_file(downloaded_path, mimetype="image/jpeg")

                except Exception as e:
                    logger.warning(
                        f"Failed to download thumbnail for artist {artist_id}: {e}"
                    )

            # Return 404 if no thumbnail available
            logger.debug(f"No {size} thumbnail available for artist {artist_id}")
            return abort(404)

    except Exception as e:
        logger.error(f"Failed to serve {size} thumbnail for artist {artist_id}: {e}")
        return abort(500)


@artists_bp.route("/thumbnail-stats", methods=["GET"])
def get_thumbnail_statistics():
    """Get comprehensive thumbnail statistics"""
    try:
        # Get storage stats from thumbnail service
        storage_stats = thumbnail_service.get_storage_stats()

        with get_db() as session:
            # Get database stats
            total_artists = session.query(Artist).count()
            artists_with_thumbnails = (
                session.query(Artist)
                .filter(
                    or_(
                        Artist.thumbnail_url.isnot(None),
                        Artist.thumbnail_path.isnot(None),
                    )
                )
                .count()
            )

            artists_by_source = {
                "imvdb": session.query(Artist)
                .filter(Artist.thumbnail_source == "imvdb")
                .count(),
                "wikipedia": session.query(Artist)
                .filter(Artist.thumbnail_source == "wikipedia")
                .count(),
                "manual": session.query(Artist)
                .filter(Artist.thumbnail_source == "manual")
                .count(),
                "manual_crop": session.query(Artist)
                .filter(Artist.thumbnail_source == "manual_crop")
                .count(),
            }

            total_videos = session.query(Video).count()
            videos_with_thumbnails = (
                session.query(Video)
                .filter(
                    or_(
                        Video.thumbnail_url.isnot(None),
                        Video.thumbnail_path.isnot(None),
                    )
                )
                .count()
            )

            database_stats = {
                "artists": {
                    "total": total_artists,
                    "with_thumbnails": artists_with_thumbnails,
                    "coverage_percentage": (
                        round((artists_with_thumbnails / total_artists * 100), 2)
                        if total_artists > 0
                        else 0
                    ),
                    "by_source": artists_by_source,
                },
                "videos": {
                    "total": total_videos,
                    "with_thumbnails": videos_with_thumbnails,
                    "coverage_percentage": (
                        round((videos_with_thumbnails / total_videos * 100), 2)
                        if total_videos > 0
                        else 0
                    ),
                },
            }

            return (
                jsonify(
                    {
                        "storage": storage_stats,
                        "database": database_stats,
                        "last_updated": datetime.utcnow().isoformat(),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get thumbnail statistics: {e}")
        return jsonify({"error": str(e)}), 500
