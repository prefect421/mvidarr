"""
Export Service - Data Collection Module
Streaming functions for collecting export data from database
"""

import json
from typing import Any, Dict, Generator

from sqlalchemy.orm import joinedload

from src.database.connection import get_db
from src.database.import_export_models import (
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
    ExportOptions,
    ProcessingProgress,
)
from src.database.models import (
    Artist,
    Playlist,
    PlaylistEntry,
    Setting,
    Video,
    VideoBlacklist,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.export.collectors")


def stream_artists(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Generator[ExportedArtist, None, None]:
    """Stream artists for export"""

    try:
        with get_db() as db:
            query = db.query(Artist)

            # Apply filters
            if export_options.artist_filter:
                query = query.filter(Artist.id.in_(export_options.artist_filter))
            if export_options.date_range_start:
                query = query.filter(
                    Artist.created_at >= export_options.date_range_start
                )
            if export_options.date_range_end:
                query = query.filter(Artist.created_at <= export_options.date_range_end)

            # Stream in chunks
            offset = 0
            while True:
                chunk = query.offset(offset).limit(export_options.chunk_size).all()
                if not chunk:
                    break

                for artist in chunk:
                    # Convert to exportable format
                    exported_artist = ExportedArtist(
                        id=artist.id,
                        name=artist.name,
                        imvdb_id=artist.imvdb_id,
                        spotify_id=artist.spotify_id,
                        lastfm_name=artist.lastfm_name,
                        thumbnail_url=(
                            artist.thumbnail_url
                            if export_options.include_thumbnails
                            else None
                        ),
                        auto_download=artist.auto_download,
                        monitored=artist.monitored,
                        keywords=(
                            json.loads(artist.keywords) if artist.keywords else None
                        ),
                        folder_path=(
                            artist.folder_path
                            if export_options.include_file_paths
                            else None
                        ),
                        genres=artist.genres.split(",") if artist.genres else None,
                        source=artist.source,
                        imvdb_metadata=(
                            artist.imvdb_metadata
                            if export_options.include_metadata
                            else None
                        ),
                        created_at=(
                            artist.created_at.isoformat() if artist.created_at else None
                        ),
                        updated_at=(
                            artist.updated_at.isoformat() if artist.updated_at else None
                        ),
                        video_count=(
                            len(artist.videos) if hasattr(artist, "videos") else 0
                        ),
                        downloaded_count=(
                            len(
                                [
                                    v
                                    for v in artist.videos
                                    if v.status.value == "DOWNLOADED"
                                ]
                            )
                            if hasattr(artist, "videos")
                            else 0
                        ),
                    )

                    yield exported_artist

                    # Update progress
                    progress.records_processed += 1
                    progress.current_record_type = "artist"
                    progress.status_message = f"Exporting artist: {artist.name}"
                    if progress.total_records > 0:
                        progress.overall_progress = min(
                            80.0,
                            (progress.records_processed / progress.total_records) * 75.0
                            + 5.0,
                        )
                    update_progress(progress)

                offset += export_options.chunk_size

    except Exception as e:
        logger.error(f"Error streaming artists: {e}")
        raise


def stream_videos(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Generator[ExportedVideo, None, None]:
    """Stream videos for export"""

    try:
        with get_db() as db:
            query = db.query(Video).options(joinedload(Video.artist))

            # Apply filters
            if export_options.artist_filter:
                query = query.filter(Video.artist_id.in_(export_options.artist_filter))
            if export_options.status_filter:
                query = query.filter(Video.status.in_(export_options.status_filter))
            if export_options.date_range_start:
                query = query.filter(
                    Video.created_at >= export_options.date_range_start
                )
            if export_options.date_range_end:
                query = query.filter(Video.created_at <= export_options.date_range_end)

            # Stream in chunks
            offset = 0
            while True:
                chunk = query.offset(offset).limit(export_options.chunk_size).all()
                if not chunk:
                    break

                for video in chunk:
                    # Extract FFmpeg metadata if available
                    ffmpeg_data = {}
                    if video.video_metadata and export_options.include_metadata:
                        ffmpeg_data = {
                            "width": video.video_metadata.get("width"),
                            "height": video.video_metadata.get("height"),
                            "video_codec": video.video_metadata.get("video_codec"),
                            "audio_codec": video.video_metadata.get("audio_codec"),
                            "fps": video.video_metadata.get("fps"),
                            "bitrate": video.video_metadata.get("bitrate"),
                            "ffmpeg_extracted": video.video_metadata.get(
                                "ffmpeg_extracted", False
                            ),
                        }

                    # Convert to exportable format
                    exported_video = ExportedVideo(
                        id=video.id,
                        artist_id=video.artist_id,
                        title=video.title,
                        imvdb_id=video.imvdb_id,
                        youtube_id=video.youtube_id,
                        youtube_url=video.youtube_url,
                        url=video.url,
                        playlist_id=video.playlist_id,
                        thumbnail_url=(
                            video.thumbnail_url
                            if export_options.include_thumbnails
                            else None
                        ),
                        duration=video.duration,
                        year=video.year,
                        release_date=(
                            video.release_date.isoformat()
                            if video.release_date
                            else None
                        ),
                        description=video.description,
                        view_count=video.view_count,
                        like_count=video.like_count,
                        genres=json.loads(video.genres) if video.genres else None,
                        directors=(
                            json.loads(video.directors) if video.directors else None
                        ),
                        producers=(
                            json.loads(video.producers) if video.producers else None
                        ),
                        status=video.status.value,
                        quality=video.quality,
                        video_metadata=(
                            video.video_metadata
                            if export_options.include_metadata
                            else None
                        ),
                        imvdb_metadata=(
                            video.imvdb_metadata
                            if export_options.include_metadata
                            else None
                        ),
                        created_at=(
                            video.created_at.isoformat() if video.created_at else None
                        ),
                        updated_at=(
                            video.updated_at.isoformat() if video.updated_at else None
                        ),
                        local_path=(
                            video.local_path
                            if export_options.include_file_paths
                            else None
                        ),
                        **ffmpeg_data,
                    )

                    yield exported_video

                    # Update progress
                    progress.records_processed += 1
                    progress.current_record_type = "video"
                    progress.status_message = f"Exporting video: {video.title}"
                    if progress.total_records > 0:
                        progress.overall_progress = min(
                            80.0,
                            (progress.records_processed / progress.total_records) * 75.0
                            + 5.0,
                        )
                    update_progress(progress)

                offset += export_options.chunk_size

    except Exception as e:
        logger.error(f"Error streaming videos: {e}")
        raise


def stream_playlists(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Generator[ExportedPlaylist, None, None]:
    """Stream playlists for export"""

    try:
        with get_db() as db:
            query = db.query(Playlist)

            # Apply filters
            if export_options.playlist_filter:
                query = query.filter(Playlist.id.in_(export_options.playlist_filter))
            if export_options.date_range_start:
                query = query.filter(
                    Playlist.created_at >= export_options.date_range_start
                )
            if export_options.date_range_end:
                query = query.filter(
                    Playlist.created_at <= export_options.date_range_end
                )

            # Stream in chunks
            offset = 0
            while True:
                chunk = query.offset(offset).limit(export_options.chunk_size).all()
                if not chunk:
                    break

                for playlist in chunk:
                    # Get playlist entries
                    entries = []
                    playlist_entries = (
                        db.query(PlaylistEntry)
                        .filter(PlaylistEntry.playlist_id == playlist.id)
                        .order_by(PlaylistEntry.position)
                        .all()
                    )

                    for entry in playlist_entries:
                        entries.append(
                            {
                                "video_id": entry.video_id,
                                "position": entry.position,
                                "notes": entry.notes,
                                "added_at": (
                                    entry.added_at.isoformat()
                                    if entry.added_at
                                    else None
                                ),
                            }
                        )

                    # Convert to exportable format
                    exported_playlist = ExportedPlaylist(
                        id=playlist.id,
                        name=playlist.name,
                        description=playlist.description,
                        user_id=playlist.user_id,
                        is_public=playlist.is_public,
                        is_featured=playlist.is_featured,
                        total_duration=playlist.total_duration,
                        video_count=playlist.video_count,
                        playlist_metadata=(
                            playlist.playlist_metadata
                            if export_options.include_metadata
                            else None
                        ),
                        thumbnail_url=(
                            playlist.thumbnail_url
                            if export_options.include_thumbnails
                            else None
                        ),
                        created_at=(
                            playlist.created_at.isoformat()
                            if playlist.created_at
                            else None
                        ),
                        updated_at=(
                            playlist.updated_at.isoformat()
                            if playlist.updated_at
                            else None
                        ),
                        entries=entries,
                    )

                    yield exported_playlist

                    # Update progress
                    progress.records_processed += 1
                    progress.current_record_type = "playlist"
                    progress.status_message = f"Exporting playlist: {playlist.name}"
                    if progress.total_records > 0:
                        progress.overall_progress = min(
                            80.0,
                            (progress.records_processed / progress.total_records) * 75.0
                            + 5.0,
                        )
                    update_progress(progress)

                offset += export_options.chunk_size

    except Exception as e:
        logger.error(f"Error streaming playlists: {e}")
        raise


def stream_settings(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Generator[ExportedSetting, None, None]:
    """Stream settings for export"""

    try:
        with get_db() as db:
            # Get all settings, excluding sensitive ones
            sensitive_keys = {
                "database_url",
                "secret_key",
                "jwt_secret",
                "encryption_key",
                "email_password",
                "smtp_password",
                "api_keys",
            }

            query = db.query(Setting)
            settings = query.all()

            for setting in settings:
                # Skip sensitive settings unless specifically included
                if (
                    setting.key in sensitive_keys
                    and not export_options.include_user_data
                ):
                    continue

                exported_setting = ExportedSetting(
                    key=setting.key,
                    value=setting.value,
                    description=setting.description,
                    created_at=(
                        setting.created_at.isoformat() if setting.created_at else None
                    ),
                    updated_at=(
                        setting.updated_at.isoformat() if setting.updated_at else None
                    ),
                )

                yield exported_setting

                # Update progress
                progress.records_processed += 1
                progress.current_record_type = "setting"
                progress.status_message = f"Exporting setting: {setting.key}"
                if progress.total_records > 0:
                    progress.overall_progress = min(
                        80.0,
                        (progress.records_processed / progress.total_records) * 75.0
                        + 5.0,
                    )
                update_progress(progress)

    except Exception as e:
        logger.error(f"Error streaming settings: {e}")
        raise


def stream_blacklist(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Generator[Dict[str, Any], None, None]:
    """Stream blacklist entries for export"""

    try:
        with get_db() as db:
            blacklist_entries = db.query(VideoBlacklist).all()

            for entry in blacklist_entries:
                blacklist_data = {
                    "youtube_url": entry.youtube_url,
                    "title": entry.title,
                    "artist_name": entry.artist_name,
                    "blacklisted_at": (
                        entry.blacklisted_at.isoformat()
                        if entry.blacklisted_at
                        else None
                    ),
                }

                yield blacklist_data

                # Update progress
                progress.records_processed += 1
                progress.current_record_type = "blacklist"
                progress.status_message = (
                    f"Exporting blacklist entry: {entry.title or entry.youtube_url}"
                )
                if progress.total_records > 0:
                    progress.overall_progress = min(
                        80.0,
                        (progress.records_processed / progress.total_records) * 75.0
                        + 5.0,
                    )
                update_progress(progress)

    except Exception as e:
        logger.error(f"Error streaming blacklist: {e}")
        raise
