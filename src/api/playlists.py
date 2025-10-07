"""
Playlist API endpoints for MVidarr
Provides CRUD operations and playlist management functionality.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from src.database.connection import get_db
from src.database.models import Artist, Playlist, PlaylistEntry, User, UserRole, Video
from src.services.thumbnail_service import ThumbnailService
from src.utils.logger import get_logger

# login_required not needed - dynamic auth middleware handles authentication globally
from src.utils.performance_monitor import monitor_performance

logger = get_logger("mvidarr.api.playlists")

playlists_bp = Blueprint("playlists", __name__, url_prefix="/playlists")


@playlists_bp.route("/test", methods=["GET"])
def test_endpoint():
    """Simple test endpoint to check if route works"""
    return jsonify({"success": True, "message": "Test endpoint working"})


def get_current_user_from_session():
    """Get current user from session for simple auth system"""
    from dataclasses import dataclass

    from flask import session

    from src.database.models import UserRole

    username = session.get("username")
    if not username:
        return None

    # Get the actual User object from database and create a session-independent user info object
    with get_db() as session_db:
        user = session_db.query(User).filter(User.username == username).first()
        if user:
            # Create a simple user info object with pre-loaded data to avoid session issues
            @dataclass
            class UserInfo:
                id: int
                username: str
                role: str

                def can_access_admin(self):
                    return self.role in [UserRole.ADMIN.value, UserRole.MANAGER.value]

                def can_modify(self):
                    return self.role in [
                        UserRole.ADMIN.value,
                        UserRole.MANAGER.value,
                        UserRole.USER.value,
                    ]

            return UserInfo(
                id=user.id,
                username=user.username,
                role=user.role.value if user.role else UserRole.USER.value,
            )
        return None


@playlists_bp.route("/", methods=["GET"])
@monitor_performance("api.playlists.list")
def get_playlists():
    """Get paginated list of playlists accessible to current user"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401

        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 50)), 200)

        offset = (page - 1) * per_page

        with get_db() as session:
            # Get playlists accessible to current user
            query = session.query(Playlist).filter(
                or_(
                    Playlist.user_id == user.id,  # User's own playlists
                    Playlist.is_public == True,  # Public playlists
                    and_(
                        user.can_access_admin(), Playlist.is_featured == True
                    ),  # Featured playlists for admins
                )
            )

            total_count = query.count()

            playlists = (
                query.options(joinedload(Playlist.user))
                .order_by(Playlist.updated_at.desc())
                .offset(offset)
                .limit(per_page)
                .all()
            )

            playlist_data = []
            for playlist in playlists:
                data = playlist.to_dict()
                data["can_modify"] = playlist.can_modify(user)
                playlist_data.append(data)

            return jsonify(
                {
                    "success": True,
                    "playlists": playlist_data,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total_count,
                        "pages": (total_count + per_page - 1) // per_page,
                    },
                }
            )

    except Exception as e:
        logger.error(f"Failed to get playlists: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>", methods=["GET"])
@monitor_performance("api.playlists.get")
def get_playlist(playlist_id):
    """Get specific playlist with entries"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        include_entries = request.args.get("include_entries", "true").lower() == "true"

        with get_db() as session:
            playlist = (
                session.query(Playlist)
                .options(
                    joinedload(Playlist.user),
                    joinedload(Playlist.entries)
                    .joinedload(PlaylistEntry.video)
                    .joinedload(Video.artist),
                    joinedload(Playlist.entries).joinedload(PlaylistEntry.user),
                )
                .filter(Playlist.id == playlist_id)
                .first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_access(user):
                return jsonify({"error": "Access denied"}), 403

            playlist_data = playlist.to_dict(include_entries=include_entries)
            playlist_data["can_modify"] = playlist.can_modify(user)

            return jsonify({"success": True, "playlist": playlist_data})

    except Exception as e:
        logger.error(f"Failed to get playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/", methods=["POST"])
@monitor_performance("api.playlists.create")
def create_playlist():
    """Create new playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        data = request.get_json()

        if not data or "name" not in data:
            return jsonify({"error": "name is required"}), 400

        name = data["name"].strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400

        description = (data.get("description") or "").strip()
        is_public = data.get("is_public", False)

        # Only admins can create featured playlists
        is_featured = data.get("is_featured", False) and user.can_access_admin()

        with get_db() as session:
            # Check if user already has a playlist with this name
            existing = (
                session.query(Playlist)
                .filter(and_(Playlist.user_id == user.id, Playlist.name == name))
                .first()
            )

            if existing:
                return (
                    jsonify({"error": "You already have a playlist with this name"}),
                    400,
                )

            # Create playlist
            playlist = Playlist(
                name=name,
                description=description or None,
                user_id=user.id,
                is_public=is_public,
                is_featured=is_featured,
            )

            session.add(playlist)
            session.commit()

            logger.info(f"Created playlist '{name}' for user {user.username}")

            playlist_data = playlist.to_dict()
            playlist_data["can_modify"] = True  # Creator can always modify

            return jsonify({"success": True, "playlist": playlist_data}), 201

    except Exception as e:
        logger.error(f"Failed to create playlist: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>", methods=["PUT"])
@monitor_performance("api.playlists.update")
def update_playlist(playlist_id):
    """Update playlist details"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        data = request.get_json()

        if not data:
            return jsonify({"error": "Request data required"}), 400

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            # Update fields
            if "name" in data:
                new_name = data["name"].strip()
                if not new_name:
                    return jsonify({"error": "name cannot be empty"}), 400

                # Check for duplicate name (excluding current playlist)
                existing = (
                    session.query(Playlist)
                    .filter(
                        and_(
                            Playlist.user_id == playlist.user_id,
                            Playlist.name == new_name,
                            Playlist.id != playlist_id,
                        )
                    )
                    .first()
                )

                if existing:
                    return (
                        jsonify(
                            {"error": "You already have a playlist with this name"}
                        ),
                        400,
                    )

                playlist.name = new_name

            if "description" in data:
                playlist.description = (data["description"] or "").strip() or None

            if "thumbnail_url" in data:
                thumbnail_url = (data["thumbnail_url"] or "").strip() or None
                playlist.thumbnail_url = thumbnail_url

            if "is_public" in data:
                playlist.is_public = bool(data["is_public"])

            # Only admins can modify featured status
            if "is_featured" in data and user.can_access_admin():
                playlist.is_featured = bool(data["is_featured"])

            session.commit()

            logger.info(f"Updated playlist {playlist_id} by user {user.username}")

            playlist_data = playlist.to_dict()
            playlist_data["can_modify"] = playlist.can_modify(user)

            return jsonify({"success": True, "playlist": playlist_data})

    except Exception as e:
        logger.error(f"Failed to update playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>", methods=["DELETE"])
@monitor_performance("api.playlists.delete")
def delete_playlist(playlist_id):
    """Delete playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            playlist_name = playlist.name
            session.delete(playlist)
            session.commit()

            logger.info(f"Deleted playlist '{playlist_name}' by user {user.username}")

            return jsonify(
                {
                    "success": True,
                    "message": f"Playlist '{playlist_name}' deleted successfully",
                }
            )

    except Exception as e:
        logger.error(f"Failed to delete playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/videos", methods=["POST"])
@monitor_performance("api.playlists.add_video")
def add_video_to_playlist(playlist_id):
    """Add video(s) to playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        data = request.get_json()

        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids is required"}), 400

        video_ids = data["video_ids"]
        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({"error": "video_ids must be a non-empty list"}), 400

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            # Verify all videos exist
            videos = session.query(Video).filter(Video.id.in_(video_ids)).all()
            found_video_ids = {v.id for v in videos}
            missing_ids = [vid for vid in video_ids if vid not in found_video_ids]

            if missing_ids:
                return jsonify({"error": f"Videos not found: {missing_ids}"}), 404

            # Get current max position
            max_position = (
                session.query(func.coalesce(func.max(PlaylistEntry.position), 0))
                .filter(PlaylistEntry.playlist_id == playlist_id)
                .scalar()
                or 0
            )

            added_count = 0
            skipped_count = 0

            for video_id in video_ids:
                # Check if video is already in playlist
                existing = (
                    session.query(PlaylistEntry)
                    .filter(
                        and_(
                            PlaylistEntry.playlist_id == playlist_id,
                            PlaylistEntry.video_id == video_id,
                        )
                    )
                    .first()
                )

                if existing:
                    skipped_count += 1
                    continue

                max_position += 1
                entry = PlaylistEntry(
                    playlist_id=playlist_id,
                    video_id=video_id,
                    position=max_position,
                    added_by=user.id,
                )

                session.add(entry)
                added_count += 1

            # Update playlist stats
            playlist.update_stats()
            session.commit()

            logger.info(
                f"Added {added_count} videos to playlist {playlist_id} by user {user.username}"
            )

            return jsonify(
                {
                    "success": True,
                    "added_count": added_count,
                    "skipped_count": skipped_count,
                    "total_videos": playlist.video_count,
                }
            )

    except Exception as e:
        logger.error(f"Failed to add videos to playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/videos/<int:entry_id>", methods=["DELETE"])
@monitor_performance("api.playlists.remove_video")
def remove_video_from_playlist(playlist_id, entry_id):
    """Remove video from playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            entry = (
                session.query(PlaylistEntry)
                .filter(
                    and_(
                        PlaylistEntry.id == entry_id,
                        PlaylistEntry.playlist_id == playlist_id,
                    )
                )
                .first()
            )

            if not entry:
                return jsonify({"error": "Playlist entry not found"}), 404

            removed_position = entry.position
            session.delete(entry)

            # Reorder remaining entries
            session.query(PlaylistEntry).filter(
                and_(
                    PlaylistEntry.playlist_id == playlist_id,
                    PlaylistEntry.position > removed_position,
                )
            ).update({PlaylistEntry.position: PlaylistEntry.position - 1})

            # Update playlist stats
            playlist.update_stats()
            session.commit()

            logger.info(
                f"Removed entry {entry_id} from playlist {playlist_id} by user {user.username}"
            )

            return jsonify(
                {
                    "success": True,
                    "message": "Video removed from playlist",
                    "total_videos": playlist.video_count,
                }
            )

    except Exception as e:
        logger.error(f"Failed to remove video from playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/videos/reorder", methods=["POST"])
@monitor_performance("api.playlists.reorder")
def reorder_playlist(playlist_id):
    """Reorder videos in playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        data = request.get_json()

        if not data or "entry_orders" not in data:
            return jsonify({"error": "entry_orders is required"}), 400

        entry_orders = data["entry_orders"]  # List of {id: int, position: int}
        if not isinstance(entry_orders, list):
            return jsonify({"error": "entry_orders must be a list"}), 400

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            # Update positions
            updated_count = 0
            for item in entry_orders:
                if (
                    not isinstance(item, dict)
                    or "id" not in item
                    or "position" not in item
                ):
                    continue

                entry = (
                    session.query(PlaylistEntry)
                    .filter(
                        and_(
                            PlaylistEntry.id == item["id"],
                            PlaylistEntry.playlist_id == playlist_id,
                        )
                    )
                    .first()
                )

                if entry:
                    entry.position = item["position"]
                    updated_count += 1

            session.commit()

            logger.info(
                f"Reordered {updated_count} entries in playlist {playlist_id} by user {user.username}"
            )

            return jsonify({"success": True, "updated_count": updated_count})

    except Exception as e:
        logger.error(f"Failed to reorder playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/bulk/delete", methods=["POST"])
@monitor_performance("api.playlists.bulk_delete")
def bulk_delete_playlists():
    """Delete multiple playlists"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401
        data = request.get_json()

        if not data or "playlist_ids" not in data:
            return jsonify({"error": "playlist_ids is required"}), 400

        playlist_ids = data["playlist_ids"]
        if not isinstance(playlist_ids, list) or not playlist_ids:
            return jsonify({"error": "playlist_ids must be a non-empty list"}), 400

        with get_db() as session:
            playlists = (
                session.query(Playlist).filter(Playlist.id.in_(playlist_ids)).all()
            )

            deleted_count = 0
            denied_count = 0

            for playlist in playlists:
                if playlist.can_modify(user):
                    session.delete(playlist)
                    deleted_count += 1
                else:
                    denied_count += 1

            session.commit()

            logger.info(
                f"Bulk deleted {deleted_count} playlists by user {user.username}"
            )

            return jsonify(
                {
                    "success": True,
                    "deleted_count": deleted_count,
                    "denied_count": denied_count,
                }
            )

    except Exception as e:
        logger.error(f"Failed to bulk delete playlists: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/user/<int:user_id>", methods=["GET"])
@monitor_performance("api.playlists.user_playlists")
def get_user_playlists(user_id):
    """Get playlists for specific user"""
    try:
        current_user = get_current_user_from_session()
        if not current_user:
            return jsonify({"error": "User not found"}), 401
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 50)), 200)

        offset = (page - 1) * per_page

        with get_db() as session:
            # Check if requesting user can access target user's playlists
            if user_id != current_user.id and not current_user.can_access_admin():
                # Non-admin users can only see public playlists of other users
                query = session.query(Playlist).filter(
                    and_(Playlist.user_id == user_id, Playlist.is_public == True)
                )
            else:
                # Admin or own playlists - see all
                query = session.query(Playlist).filter(Playlist.user_id == user_id)

            total_count = query.count()

            playlists = (
                query.options(joinedload(Playlist.user))
                .order_by(Playlist.updated_at.desc())
                .offset(offset)
                .limit(per_page)
                .all()
            )

            playlist_data = []
            for playlist in playlists:
                data = playlist.to_dict()
                data["can_modify"] = playlist.can_modify(current_user)
                playlist_data.append(data)

            return jsonify(
                {
                    "success": True,
                    "playlists": playlist_data,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total_count,
                        "pages": (total_count + per_page - 1) // per_page,
                    },
                }
            )

    except Exception as e:
        logger.error(f"Failed to get user playlists for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/thumbnail/upload", methods=["POST"])
@monitor_performance("api.playlists.upload_thumbnail")
def upload_playlist_thumbnail(playlist_id):
    """Upload thumbnail from URL for a playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401

        data = request.get_json()
        if not data or not data.get("url"):
            return jsonify({"error": "URL is required"}), 400

        thumbnail_url = data.get("url").strip()
        if not thumbnail_url:
            return jsonify({"error": "Valid URL is required"}), 400

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )
            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            # Download thumbnail using thumbnail service
            thumbnail_service = ThumbnailService()

            try:
                downloaded_path = thumbnail_service.download_playlist_thumbnail(
                    playlist.name, thumbnail_url
                )

                if not downloaded_path:
                    return (
                        jsonify({"error": "Failed to download thumbnail from URL"}),
                        400,
                    )

                # Convert absolute path to relative path for storage
                # Get relative path from thumbnails directory
                from pathlib import Path

                abs_path = Path(downloaded_path)
                thumbnails_dir = thumbnail_service.thumbnails_dir

                try:
                    relative_path = abs_path.relative_to(thumbnails_dir)
                    # Store relative path in database
                    playlist.thumbnail_url = f"/thumbnails/{relative_path}"
                    session.commit()

                    logger.info(
                        f"Thumbnail uploaded for playlist {playlist_id} by user {user.username}"
                    )

                    playlist_data = playlist.to_dict()
                    playlist_data["can_modify"] = playlist.can_modify(user)

                    return jsonify(
                        {
                            "success": True,
                            "message": "Thumbnail uploaded successfully",
                            "playlist": playlist_data,
                            "thumbnail_path": playlist.thumbnail_url,
                        }
                    )

                except ValueError:
                    # If path is not relative to thumbnails dir, store absolute path
                    playlist.thumbnail_url = (
                        f"/thumbnails/playlists/{Path(downloaded_path).name}"
                    )
                    session.commit()

                    playlist_data = playlist.to_dict()
                    playlist_data["can_modify"] = playlist.can_modify(user)

                    return jsonify(
                        {
                            "success": True,
                            "message": "Thumbnail uploaded successfully",
                            "playlist": playlist_data,
                            "thumbnail_path": playlist.thumbnail_url,
                        }
                    )

            except Exception as download_error:
                logger.error(f"Failed to download thumbnail: {download_error}")
                return (
                    jsonify(
                        {
                            "error": f"Failed to download thumbnail: {str(download_error)}"
                        }
                    ),
                    400,
                )

    except Exception as e:
        logger.error(f"Failed to upload thumbnail for playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/thumbnail/file", methods=["POST"])
@monitor_performance("api.playlists.upload_thumbnail_file")
def upload_playlist_thumbnail_file(playlist_id):
    """Upload thumbnail file for a playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Check if file was uploaded
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Validate file type
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        file_ext = (
            "." + file.filename.rsplit(".", 1)[1].lower()
            if "." in file.filename
            else ""
        )
        if file_ext not in allowed_extensions:
            return (
                jsonify(
                    {
                        "error": "Invalid file type. Please upload JPG, PNG, WebP, or GIF images."
                    }
                ),
                400,
            )

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )
            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Access denied"}), 403

            # Read file data
            file_data = file.read()
            if len(file_data) > 10 * 1024 * 1024:  # 10MB limit
                return jsonify({"error": "File too large. Maximum size is 10MB."}), 400

            # Upload using thumbnail service
            thumbnail_service = ThumbnailService()

            try:
                upload_result = thumbnail_service.upload_manual_thumbnail(
                    file_data=file_data,
                    filename=file.filename,
                    entity_type="playlist",
                    entity_id=playlist.id,
                    entity_name=playlist.name,
                )

                if not upload_result:
                    return jsonify({"error": "Failed to process thumbnail file"}), 400

                # Convert absolute path to relative path for storage
                from pathlib import Path

                primary_path = Path(upload_result["primary_path"])
                thumbnails_dir = thumbnail_service.thumbnails_dir

                try:
                    relative_path = primary_path.relative_to(thumbnails_dir)
                    # Store relative path in database
                    playlist.thumbnail_url = f"/thumbnails/{relative_path}"
                    session.commit()

                    logger.info(
                        f"Thumbnail file uploaded for playlist {playlist_id} by user {user.username}"
                    )

                    playlist_data = playlist.to_dict()
                    playlist_data["can_modify"] = playlist.can_modify(user)

                    return jsonify(
                        {
                            "success": True,
                            "message": "Thumbnail uploaded successfully",
                            "playlist": playlist_data,
                            "thumbnail_path": playlist.thumbnail_url,
                            "upload_info": upload_result["metadata"],
                        }
                    )

                except ValueError:
                    # If path is not relative to thumbnails dir, use filename
                    playlist.thumbnail_url = (
                        f"/thumbnails/playlists/medium/{primary_path.name}"
                    )
                    session.commit()

                    playlist_data = playlist.to_dict()
                    playlist_data["can_modify"] = playlist.can_modify(user)

                    return jsonify(
                        {
                            "success": True,
                            "message": "Thumbnail uploaded successfully",
                            "playlist": playlist_data,
                            "thumbnail_path": playlist.thumbnail_url,
                            "upload_info": upload_result["metadata"],
                        }
                    )

            except Exception as upload_error:
                logger.error(f"Failed to upload thumbnail file: {upload_error}")
                return (
                    jsonify(
                        {"error": f"Failed to process thumbnail: {str(upload_error)}"}
                    ),
                    400,
                )

    except Exception as e:
        logger.error(f"Failed to upload thumbnail file for playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


# ===== DYNAMIC PLAYLISTS ENDPOINTS (Issue #109) =====


@playlists_bp.route("/dynamic", methods=["POST"])
@monitor_performance("api.playlists.create_dynamic")
def create_dynamic_playlist():
    """Create a new dynamic playlist with filter criteria"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        # Validate required fields
        required_fields = ["name", "filter_criteria"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        from src.services.dynamic_playlist_service import dynamic_playlist_service

        # Create dynamic playlist
        playlist = dynamic_playlist_service.create_dynamic_playlist(
            name=data["name"],
            description=data.get("description"),
            user_id=user.id,
            filter_criteria=data["filter_criteria"],
            is_public=data.get("is_public", False),
            auto_update=data.get("auto_update", True),
        )

        logger.info(f"User {user.username} created dynamic playlist '{playlist.name}'")
        return jsonify(
            {"success": True, "playlist": playlist.to_dict(include_entries=True)}
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to create dynamic playlist: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/refresh", methods=["POST"])
@monitor_performance("api.playlists.refresh_dynamic")
def refresh_dynamic_playlist(playlist_id):
    """Manually refresh a dynamic playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )
            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Permission denied"}), 403

            if not playlist.is_dynamic():
                return jsonify({"error": "Playlist is not dynamic"}), 400

            from src.services.dynamic_playlist_service import dynamic_playlist_service

            changes_made = dynamic_playlist_service.update_dynamic_playlist(playlist_id)

            # Query fresh playlist data instead of refreshing to avoid session conflicts
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            logger.info(
                f"User {user.username} refreshed dynamic playlist '{playlist.name}'"
            )
            return jsonify(
                {
                    "success": True,
                    "changes_made": changes_made,
                    "playlist": playlist.to_dict(include_entries=True),
                }
            )

    except Exception as e:
        logger.error(f"Failed to refresh dynamic playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/<int:playlist_id>/filters", methods=["PUT"])
@monitor_performance("api.playlists.update_filters")
def update_playlist_filters(playlist_id):
    """Update filter criteria for a dynamic playlist"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data or "filter_criteria" not in data:
            return jsonify({"error": "Filter criteria required"}), 400

        with get_db() as session:
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )
            if not playlist:
                return jsonify({"error": "Playlist not found"}), 404

            if not playlist.can_modify(user):
                return jsonify({"error": "Permission denied"}), 403

            if not playlist.is_dynamic():
                return jsonify({"error": "Playlist is not dynamic"}), 400

            # Update filter criteria
            playlist.filter_criteria = data["filter_criteria"]

            # Update auto_update setting if provided
            if "auto_update" in data:
                playlist.auto_update = data["auto_update"]

            # Validate new criteria
            if not playlist.validate_filter_criteria():
                return jsonify({"error": "Invalid filter criteria"}), 400

            session.commit()

            # Refresh playlist with new criteria
            from src.services.dynamic_playlist_service import dynamic_playlist_service

            changes_made = dynamic_playlist_service.update_dynamic_playlist(playlist_id)

            # Query fresh playlist data instead of refreshing to avoid session conflicts
            playlist = (
                session.query(Playlist).filter(Playlist.id == playlist_id).first()
            )

            logger.info(
                f"User {user.username} updated filters for dynamic playlist '{playlist.name}'"
            )
            return jsonify(
                {
                    "success": True,
                    "changes_made": changes_made,
                    "playlist": playlist.to_dict(include_entries=True),
                }
            )

    except Exception as e:
        logger.error(f"Failed to update filters for playlist {playlist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/dynamic/templates", methods=["GET"])
@monitor_performance("api.playlists.get_templates")
def get_dynamic_playlist_templates():
    """Get available dynamic playlist templates"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        from src.services.dynamic_playlist_service import dynamic_playlist_service

        templates = dynamic_playlist_service.get_dynamic_playlist_templates()

        return jsonify({"success": True, "templates": templates})

    except Exception as e:
        logger.error(f"Failed to get dynamic playlist templates: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/dynamic/templates/<template_id>", methods=["POST"])
@monitor_performance("api.playlists.create_from_template")
def create_playlist_from_template(template_id):
    """Create a dynamic playlist from a template"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json() or {}

        from src.services.dynamic_playlist_service import dynamic_playlist_service

        # Get template
        templates = dynamic_playlist_service.get_dynamic_playlist_templates()
        template = next((t for t in templates if t["id"] == template_id), None)

        if not template:
            return jsonify({"error": "Template not found"}), 404

        # Create playlist from template
        playlist_name = data.get("name", template["name"])
        playlist_description = data.get("description", template["description"])

        playlist = dynamic_playlist_service.create_dynamic_playlist(
            name=playlist_name,
            description=playlist_description,
            user_id=user.id,
            filter_criteria=template["filter_criteria"],
            is_public=data.get("is_public", False),
            auto_update=data.get("auto_update", True),
        )

        logger.info(
            f"User {user.username} created playlist from template '{template_id}'"
        )
        return jsonify(
            {
                "success": True,
                "playlist": playlist.to_dict(include_entries=True),
                "template_used": template_id,
            }
        )

    except Exception as e:
        logger.error(f"Failed to create playlist from template {template_id}: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/dynamic/preview", methods=["POST"])
@monitor_performance("api.playlists.preview_filters")
def preview_dynamic_playlist():
    """Preview what videos would match given filter criteria"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data or "filter_criteria" not in data:
            return jsonify({"error": "Filter criteria required"}), 400

        from src.services.dynamic_playlist_service import dynamic_playlist_service

        # Get preview
        limit = data.get("limit", 50)
        preview = dynamic_playlist_service.preview_filter_criteria(
            data["filter_criteria"], limit=limit
        )

        return jsonify({"success": True, "preview": preview})

    except Exception as e:
        logger.error(f"Failed to preview dynamic playlist: {e}")
        return jsonify({"error": str(e)}), 500


@playlists_bp.route("/dynamic/update-all", methods=["POST"])
@monitor_performance("api.playlists.update_all_dynamic")
def update_all_dynamic_playlists():
    """Update all dynamic playlists (admin only)"""
    try:
        user = get_current_user_from_session()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        if user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            return jsonify({"error": "Admin permission required"}), 403

        data = request.get_json() or {}
        max_age_hours = data.get("max_age_hours", 24)

        from src.services.dynamic_playlist_service import dynamic_playlist_service

        result = dynamic_playlist_service.update_all_dynamic_playlists(max_age_hours)

        logger.info(f"Admin {user.username} triggered update of all dynamic playlists")
        return jsonify({"success": True, "update_result": result})

    except Exception as e:
        logger.error(f"Failed to update all dynamic playlists: {e}")
        return jsonify({"error": str(e)}), 500
