"""
Export Service - Utilities Module
Helper functions for export operations (checksums, serialization, cleanup, counting)
"""

import hashlib
from pathlib import Path
from typing import Any, Dict

from src.database.connection import get_db
from src.database.import_export_models import (
    ExportData,
    ExportManifest,
    ExportOptions,
    ExportType,
    ProcessingProgress,
)
from src.database.models import Artist, Playlist, Setting, Video, VideoBlacklist
from src.services.export_collectors import (
    stream_artists,
    stream_blacklist,
    stream_playlists,
    stream_settings,
    stream_videos,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.export.utils")


def calculate_file_checksum(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def serialize_export_options(export_options: ExportOptions) -> Dict[str, Any]:
    """Serialize export options for database storage"""
    return {
        "format": export_options.format.value,
        "export_type": export_options.export_type.value,
        "include_file_paths": export_options.include_file_paths,
        "include_thumbnails": export_options.include_thumbnails,
        "include_metadata": export_options.include_metadata,
        "include_user_data": export_options.include_user_data,
        "compression_enabled": export_options.compression_enabled,
        "compression_level": export_options.compression_level,
        "chunk_size": export_options.chunk_size,
        "encrypt_output": export_options.encrypt_output,
    }


def cleanup_export_files(operation_id: int, temp_dir: Path):
    """Clean up temporary files for an export operation"""
    try:
        # Find files matching the operation ID pattern
        pattern = f"mvidarr_export_{operation_id}_*"
        for file_path in temp_dir.glob(pattern):
            file_path.unlink(missing_ok=True)
            logger.info(f"Cleaned up export file: {file_path.name}")
    except Exception as e:
        logger.error(
            f"Error cleaning up export files for operation {operation_id}: {e}"
        )


def create_export_manifest(export_options: ExportOptions) -> ExportManifest:
    """Create export manifest with metadata"""
    return ExportManifest(
        export_type=export_options.export_type.value,
        export_format=export_options.format.value,
        compression_enabled=export_options.compression_enabled,
        encryption_enabled=export_options.encrypt_output,
        includes_file_paths=export_options.include_file_paths,
        includes_thumbnails=export_options.include_thumbnails,
        includes_metadata=export_options.include_metadata,
        includes_user_data=export_options.include_user_data,
        anonymized_users=export_options.anonymize_users,
    )


def count_exportable_records(export_options: ExportOptions) -> Dict[str, int]:
    """Count total records that will be exported"""
    counts = {}

    try:
        with get_db() as db:
            # Count artists
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.ARTISTS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                query = db.query(Artist)
                if export_options.artist_filter:
                    query = query.filter(Artist.id.in_(export_options.artist_filter))
                if export_options.date_range_start:
                    query = query.filter(
                        Artist.created_at >= export_options.date_range_start
                    )
                if export_options.date_range_end:
                    query = query.filter(
                        Artist.created_at <= export_options.date_range_end
                    )
                counts["artists"] = query.count()
            else:
                counts["artists"] = 0

            # Count videos
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.VIDEOS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                query = db.query(Video)
                if export_options.artist_filter:
                    query = query.filter(
                        Video.artist_id.in_(export_options.artist_filter)
                    )
                if export_options.status_filter:
                    query = query.filter(Video.status.in_(export_options.status_filter))
                if export_options.date_range_start:
                    query = query.filter(
                        Video.created_at >= export_options.date_range_start
                    )
                if export_options.date_range_end:
                    query = query.filter(
                        Video.created_at <= export_options.date_range_end
                    )
                counts["videos"] = query.count()
            else:
                counts["videos"] = 0

            # Count playlists
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.PLAYLISTS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                query = db.query(Playlist)
                if export_options.playlist_filter:
                    query = query.filter(
                        Playlist.id.in_(export_options.playlist_filter)
                    )
                if export_options.date_range_start:
                    query = query.filter(
                        Playlist.created_at >= export_options.date_range_start
                    )
                if export_options.date_range_end:
                    query = query.filter(
                        Playlist.created_at <= export_options.date_range_end
                    )
                counts["playlists"] = query.count()
            else:
                counts["playlists"] = 0

            # Count settings
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.SETTINGS_ONLY,
            ]:
                counts["settings"] = db.query(Setting).count()
            else:
                counts["settings"] = 0

            # Count blacklist
            if export_options.export_type == ExportType.FULL_LIBRARY:
                counts["blacklist"] = db.query(VideoBlacklist).count()
            else:
                counts["blacklist"] = 0

    except Exception as e:
        logger.error(f"Error counting exportable records: {e}")
        counts = {
            "artists": 0,
            "videos": 0,
            "playlists": 0,
            "settings": 0,
            "blacklist": 0,
        }

    return counts


def collect_export_data(
    export_options: ExportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> ExportData:
    """Collect all data for export using streaming approach"""

    export_data = ExportData(manifest=create_export_manifest(export_options))

    try:
        # Export artists
        if export_options.export_type in [
            ExportType.FULL_LIBRARY,
            ExportType.ARTISTS_ONLY,
            ExportType.CUSTOM_SELECTION,
        ]:
            artists = list(stream_artists(export_options, progress, update_progress))
            export_data.artists = artists
            export_data.manifest.artists_count = len(artists)

        # Export videos
        if export_options.export_type in [
            ExportType.FULL_LIBRARY,
            ExportType.VIDEOS_ONLY,
            ExportType.CUSTOM_SELECTION,
        ]:
            videos = list(stream_videos(export_options, progress, update_progress))
            export_data.videos = videos
            export_data.manifest.videos_count = len(videos)

        # Export playlists
        if export_options.export_type in [
            ExportType.FULL_LIBRARY,
            ExportType.PLAYLISTS_ONLY,
            ExportType.CUSTOM_SELECTION,
        ]:
            playlists = list(
                stream_playlists(export_options, progress, update_progress)
            )
            export_data.playlists = playlists
            export_data.manifest.playlists_count = len(playlists)

        # Export settings
        if export_options.export_type in [
            ExportType.FULL_LIBRARY,
            ExportType.SETTINGS_ONLY,
        ]:
            settings = list(stream_settings(export_options, progress, update_progress))
            export_data.settings = settings
            export_data.manifest.settings_count = len(settings)

        # Export blacklist
        if export_options.export_type == ExportType.FULL_LIBRARY:
            blacklist = list(
                stream_blacklist(export_options, progress, update_progress)
            )
            export_data.blacklist = blacklist

        # Update manifest totals
        export_data.manifest.total_records = (
            export_data.manifest.artists_count
            + export_data.manifest.videos_count
            + export_data.manifest.playlists_count
            + export_data.manifest.settings_count
            + len(export_data.blacklist)
        )

        return export_data

    except Exception as e:
        logger.error(f"Error collecting export data: {e}")
        raise
