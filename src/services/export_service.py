"""
Export Service for MVidarr 0.9.7 - Issue #76
Streaming export service with multiple formats and comprehensive data portability.
"""

import csv
import gzip
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import yaml
from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from src.database.connection import get_db
from src.database.import_export_models import (
    ExportData,
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
    ExportFormat,
    ExportManifest,
    ExportOperation,
    ExportOptions,
    ExportType,
    ProcessingProgress,
    ProcessingStatus,
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

logger = get_logger("mvidarr.services.export")


class ExportService:
    """Comprehensive export service with streaming support"""

    def __init__(self):
        self.chunk_size = 1000
        self.temp_dir = Path(tempfile.gettempdir()) / "mvidarr_exports"
        self.temp_dir.mkdir(exist_ok=True, parents=True)

    def start_export(
        self,
        user_id: int,
        operation_name: str,
        export_options: ExportOptions,
        progress_callback: Optional[callable] = None,
    ) -> int:
        """
        Start an export operation and return the operation ID

        Args:
            user_id: ID of the user requesting export
            operation_name: Human-readable name for the operation
            export_options: Export configuration options
            progress_callback: Optional callback for progress updates

        Returns:
            Export operation ID for tracking
        """
        try:
            # Create export operation record
            with get_db() as db:
                operation = ExportOperation(
                    user_id=user_id,
                    operation_name=operation_name,
                    export_type=export_options.export_type,
                    export_format=export_options.format,
                    export_options=self._serialize_export_options(export_options),
                    status=ProcessingStatus.PENDING,
                )
                db.add(operation)
                db.commit()
                db.refresh(operation)
                operation_id = operation.id

            logger.info(f"Started export operation {operation_id}: {operation_name}")

            # Perform the export
            self._perform_export(operation_id, export_options, progress_callback)

            return operation_id

        except Exception as e:
            logger.error(f"Failed to start export: {e}")
            # Update operation status to failed
            with get_db() as db:
                if "operation_id" in locals():
                    operation = (
                        db.query(ExportOperation)
                        .filter(ExportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.status = ProcessingStatus.FAILED
                        operation.error_log = [str(e)]
                        operation.completed_at = datetime.utcnow()
                        db.commit()
            raise

    def get_export_status(self, operation_id: int) -> Optional[Dict[str, Any]]:
        """Get the current status of an export operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(ExportOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    return None
                return operation.to_dict()
        except Exception as e:
            logger.error(
                f"Error getting export status for operation {operation_id}: {e}"
            )
            return None

    def cancel_export(self, operation_id: int, user_id: int) -> bool:
        """Cancel a running export operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(
                        and_(
                            ExportOperation.id == operation_id,
                            ExportOperation.user_id == user_id,
                            ExportOperation.status.in_(
                                [ProcessingStatus.PENDING, ProcessingStatus.RUNNING]
                            ),
                        )
                    )
                    .first()
                )

                if not operation:
                    return False

                operation.status = ProcessingStatus.CANCELLED
                operation.completed_at = datetime.utcnow()
                db.commit()

                # Clean up temporary files
                self._cleanup_export_files(operation_id)

                logger.info(f"Cancelled export operation {operation_id}")
                return True

        except Exception as e:
            logger.error(f"Error cancelling export operation {operation_id}: {e}")
            return False

    def get_export_file_path(self, operation_id: int) -> Optional[Path]:
        """Get the file path for a completed export"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(ExportOperation.id == operation_id)
                    .first()
                )
                if (
                    operation
                    and operation.status == ProcessingStatus.COMPLETED
                    and operation.output_filename
                ):
                    return self.temp_dir / operation.output_filename
                return None
        except Exception as e:
            logger.error(
                f"Error getting export file path for operation {operation_id}: {e}"
            )
            return None

    def _perform_export(
        self,
        operation_id: int,
        export_options: ExportOptions,
        progress_callback: Optional[callable] = None,
    ):
        """Perform the actual export operation"""

        def update_progress(progress: ProcessingProgress):
            """Update operation progress in database"""
            try:
                with get_db() as db:
                    operation = (
                        db.query(ExportOperation)
                        .filter(ExportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.progress_percentage = int(progress.overall_progress)
                        operation.processed_records = progress.records_processed
                        operation.total_records = progress.total_records
                        if progress.overall_progress == 100.0:
                            operation.status = ProcessingStatus.COMPLETED
                            operation.completed_at = datetime.utcnow()
                        elif operation.status == ProcessingStatus.PENDING:
                            operation.status = ProcessingStatus.RUNNING
                            operation.started_at = datetime.utcnow()
                        db.commit()

                if progress_callback:
                    progress_callback(progress)

            except Exception as e:
                logger.error(
                    f"Error updating progress for operation {operation_id}: {e}"
                )

        try:
            logger.info(f"Starting export data collection for operation {operation_id}")

            # Initialize progress
            progress = ProcessingProgress(
                current_phase="initialization",
                total_phases=4,
                current_phase_progress=0.0,
                overall_progress=0.0,
                records_processed=0,
                total_records=0,
                records_per_second=0.0,
                status_message="Initializing export operation...",
            )
            update_progress(progress)

            # Step 1: Count total records to export
            progress.current_phase = "counting_records"
            progress.status_message = "Counting records to export..."
            progress.current_phase_progress = 10.0
            progress.overall_progress = 2.5
            update_progress(progress)

            total_counts = self._count_exportable_records(export_options)
            progress.total_records = sum(total_counts.values())

            # Step 2: Collect export data
            progress.current_phase = "collecting_data"
            progress.status_message = "Collecting export data..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 5.0
            update_progress(progress)

            export_data = self._collect_export_data(
                export_options, progress, update_progress
            )

            # Step 3: Generate output file
            progress.current_phase = "generating_file"
            progress.status_message = "Generating export file..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 80.0
            update_progress(progress)

            output_file = self._generate_export_file(
                operation_id, export_data, export_options
            )

            # Step 4: Finalize
            progress.current_phase = "finalizing"
            progress.status_message = "Finalizing export..."
            progress.current_phase_progress = 90.0
            progress.overall_progress = 95.0
            update_progress(progress)

            # Update operation with results
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(ExportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.output_filename = output_file.name
                    operation.output_size_bytes = (
                        output_file.stat().st_size if output_file.exists() else 0
                    )
                    operation.output_compressed = export_options.compression_enabled
                    operation.result_data = {
                        "artists_exported": len(export_data.artists),
                        "videos_exported": len(export_data.videos),
                        "playlists_exported": len(export_data.playlists),
                        "settings_exported": len(export_data.settings),
                        "blacklist_exported": len(export_data.blacklist),
                        "export_format": export_options.format.value,
                        "file_size_mb": round(
                            operation.output_size_bytes / (1024 * 1024), 2
                        ),
                    }
                    db.commit()

            # Complete
            progress.current_phase = "completed"
            progress.status_message = (
                f"Export completed successfully - {output_file.name}"
            )
            progress.current_phase_progress = 100.0
            progress.overall_progress = 100.0
            update_progress(progress)

            logger.info(f"Export operation {operation_id} completed successfully")

        except Exception as e:
            logger.error(f"Export operation {operation_id} failed: {e}")

            # Update operation status to failed
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(ExportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.status = ProcessingStatus.FAILED
                    operation.error_log = [str(e)]
                    operation.completed_at = datetime.utcnow()
                    db.commit()

            # Update progress with failure
            if "progress" in locals():
                progress.status_message = f"Export failed: {str(e)}"
                update_progress(progress)

            raise

    def _count_exportable_records(
        self, export_options: ExportOptions
    ) -> Dict[str, int]:
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
                        query = query.filter(
                            Artist.id.in_(export_options.artist_filter)
                        )
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
                        query = query.filter(
                            Video.status.in_(export_options.status_filter)
                        )
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

    def _collect_export_data(
        self,
        export_options: ExportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> ExportData:
        """Collect all data for export using streaming approach"""

        export_data = ExportData(manifest=self._create_export_manifest(export_options))

        try:
            # Export artists
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.ARTISTS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                artists = list(
                    self._stream_artists(export_options, progress, update_progress)
                )
                export_data.artists = artists
                export_data.manifest.artists_count = len(artists)

            # Export videos
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.VIDEOS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                videos = list(
                    self._stream_videos(export_options, progress, update_progress)
                )
                export_data.videos = videos
                export_data.manifest.videos_count = len(videos)

            # Export playlists
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.PLAYLISTS_ONLY,
                ExportType.CUSTOM_SELECTION,
            ]:
                playlists = list(
                    self._stream_playlists(export_options, progress, update_progress)
                )
                export_data.playlists = playlists
                export_data.manifest.playlists_count = len(playlists)

            # Export settings
            if export_options.export_type in [
                ExportType.FULL_LIBRARY,
                ExportType.SETTINGS_ONLY,
            ]:
                settings = list(
                    self._stream_settings(export_options, progress, update_progress)
                )
                export_data.settings = settings
                export_data.manifest.settings_count = len(settings)

            # Export blacklist
            if export_options.export_type == ExportType.FULL_LIBRARY:
                blacklist = list(
                    self._stream_blacklist(export_options, progress, update_progress)
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

    def _stream_artists(
        self,
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
                    query = query.filter(
                        Artist.created_at <= export_options.date_range_end
                    )

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
                                artist.created_at.isoformat()
                                if artist.created_at
                                else None
                            ),
                            updated_at=(
                                artist.updated_at.isoformat()
                                if artist.updated_at
                                else None
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
                                (progress.records_processed / progress.total_records)
                                * 75.0
                                + 5.0,
                            )
                        update_progress(progress)

                    offset += export_options.chunk_size

        except Exception as e:
            logger.error(f"Error streaming artists: {e}")
            raise

    def _stream_videos(
        self,
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
                                video.created_at.isoformat()
                                if video.created_at
                                else None
                            ),
                            updated_at=(
                                video.updated_at.isoformat()
                                if video.updated_at
                                else None
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
                                (progress.records_processed / progress.total_records)
                                * 75.0
                                + 5.0,
                            )
                        update_progress(progress)

                    offset += export_options.chunk_size

        except Exception as e:
            logger.error(f"Error streaming videos: {e}")
            raise

    def _stream_playlists(
        self,
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
                                (progress.records_processed / progress.total_records)
                                * 75.0
                                + 5.0,
                            )
                        update_progress(progress)

                    offset += export_options.chunk_size

        except Exception as e:
            logger.error(f"Error streaming playlists: {e}")
            raise

    def _stream_settings(
        self,
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
                            setting.created_at.isoformat()
                            if setting.created_at
                            else None
                        ),
                        updated_at=(
                            setting.updated_at.isoformat()
                            if setting.updated_at
                            else None
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

    def _stream_blacklist(
        self,
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

    def _create_export_manifest(self, export_options: ExportOptions) -> ExportManifest:
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

    def _generate_export_file(
        self, operation_id: int, export_data: ExportData, export_options: ExportOptions
    ) -> Path:
        """Generate the final export file in the specified format"""

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_filename = f"mvidarr_export_{operation_id}_{timestamp}"

        if export_options.format == ExportFormat.JSON:
            output_file = self._generate_json_export(
                export_data, base_filename, export_options
            )
        elif export_options.format == ExportFormat.CSV:
            output_file = self._generate_csv_export(
                export_data, base_filename, export_options
            )
        elif export_options.format == ExportFormat.XML:
            output_file = self._generate_xml_export(
                export_data, base_filename, export_options
            )
        elif export_options.format == ExportFormat.YAML:
            output_file = self._generate_yaml_export(
                export_data, base_filename, export_options
            )
        else:
            raise ValueError(f"Unsupported export format: {export_options.format}")

        # Add checksum to manifest
        export_data.manifest.checksum = self._calculate_file_checksum(output_file)
        export_data.manifest.file_size_bytes = output_file.stat().st_size

        return output_file

    def _generate_json_export(
        self, export_data: ExportData, base_filename: str, export_options: ExportOptions
    ) -> Path:
        """Generate JSON format export"""

        filename = f"{base_filename}.json"
        if export_options.compression_enabled:
            filename += ".gz"

        output_file = self.temp_dir / filename

        # Convert to dictionary
        data_dict = export_data.to_dict()

        # Write file
        if export_options.compression_enabled:
            with gzip.open(
                output_file,
                "wt",
                encoding="utf-8",
                compresslevel=export_options.compression_level,
            ) as f:
                json.dump(data_dict, f, indent=2, ensure_ascii=False)
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data_dict, f, indent=2, ensure_ascii=False)

        return output_file

    def _generate_csv_export(
        self, export_data: ExportData, base_filename: str, export_options: ExportOptions
    ) -> Path:
        """Generate CSV format export (separate files for each entity type)"""

        # Create a ZIP file containing multiple CSV files
        import zipfile

        filename = f"{base_filename}.zip"
        output_file = self.temp_dir / filename

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Export artists CSV
            if export_data.artists:
                csv_content = self._create_artists_csv(export_data.artists)
                zip_file.writestr("artists.csv", csv_content)

            # Export videos CSV
            if export_data.videos:
                csv_content = self._create_videos_csv(export_data.videos)
                zip_file.writestr("videos.csv", csv_content)

            # Export playlists CSV
            if export_data.playlists:
                csv_content = self._create_playlists_csv(export_data.playlists)
                zip_file.writestr("playlists.csv", csv_content)

            # Export settings CSV
            if export_data.settings:
                csv_content = self._create_settings_csv(export_data.settings)
                zip_file.writestr("settings.csv", csv_content)

            # Export blacklist CSV
            if export_data.blacklist:
                csv_content = self._create_blacklist_csv(export_data.blacklist)
                zip_file.writestr("blacklist.csv", csv_content)

            # Add manifest
            manifest_json = json.dumps(export_data.manifest.__dict__, indent=2)
            zip_file.writestr("manifest.json", manifest_json)

        return output_file

    def _generate_xml_export(
        self, export_data: ExportData, base_filename: str, export_options: ExportOptions
    ) -> Path:
        """Generate XML format export"""

        filename = f"{base_filename}.xml"
        if export_options.compression_enabled:
            filename += ".gz"

        output_file = self.temp_dir / filename

        # Create XML structure
        root = ET.Element("mvidarr_export")

        # Add manifest
        manifest_elem = ET.SubElement(root, "manifest")
        for key, value in export_data.manifest.__dict__.items():
            elem = ET.SubElement(manifest_elem, key)
            elem.text = str(value) if value is not None else ""

        # Add artists
        if export_data.artists:
            artists_elem = ET.SubElement(root, "artists")
            for artist in export_data.artists:
                artist_elem = ET.SubElement(artists_elem, "artist")
                for key, value in artist.__dict__.items():
                    elem = ET.SubElement(artist_elem, key)
                    elem.text = str(value) if value is not None else ""

        # Add videos (similar structure)
        if export_data.videos:
            videos_elem = ET.SubElement(root, "videos")
            for video in export_data.videos:
                video_elem = ET.SubElement(videos_elem, "video")
                for key, value in video.__dict__.items():
                    elem = ET.SubElement(video_elem, key)
                    elem.text = str(value) if value is not None else ""

        # Generate XML string
        xml_string = ET.tostring(root, encoding="unicode")

        # Write file
        if export_options.compression_enabled:
            with gzip.open(
                output_file,
                "wt",
                encoding="utf-8",
                compresslevel=export_options.compression_level,
            ) as f:
                f.write(xml_string)
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(xml_string)

        return output_file

    def _generate_yaml_export(
        self, export_data: ExportData, base_filename: str, export_options: ExportOptions
    ) -> Path:
        """Generate YAML format export"""

        filename = f"{base_filename}.yaml"
        if export_options.compression_enabled:
            filename += ".gz"

        output_file = self.temp_dir / filename

        # Convert to dictionary
        data_dict = export_data.to_dict()

        # Write file
        if export_options.compression_enabled:
            with gzip.open(
                output_file,
                "wt",
                encoding="utf-8",
                compresslevel=export_options.compression_level,
            ) as f:
                yaml.dump(data_dict, f, default_flow_style=False, allow_unicode=True)
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.dump(data_dict, f, default_flow_style=False, allow_unicode=True)

        return output_file

    def _create_artists_csv(self, artists: List[ExportedArtist]) -> str:
        """Create CSV content for artists"""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "id",
                "name",
                "imvdb_id",
                "spotify_id",
                "lastfm_name",
                "thumbnail_url",
                "auto_download",
                "monitored",
                "keywords",
                "folder_path",
                "genres",
                "source",
                "created_at",
                "updated_at",
                "video_count",
                "downloaded_count",
            ]
        )

        # Data
        for artist in artists:
            writer.writerow(
                [
                    artist.id,
                    artist.name,
                    artist.imvdb_id,
                    artist.spotify_id,
                    artist.lastfm_name,
                    artist.thumbnail_url,
                    artist.auto_download,
                    artist.monitored,
                    json.dumps(artist.keywords) if artist.keywords else "",
                    artist.folder_path,
                    json.dumps(artist.genres) if artist.genres else "",
                    artist.source,
                    artist.created_at,
                    artist.updated_at,
                    artist.video_count,
                    artist.downloaded_count,
                ]
            )

        return output.getvalue()

    def _create_videos_csv(self, videos: List[ExportedVideo]) -> str:
        """Create CSV content for videos"""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "id",
                "artist_id",
                "title",
                "imvdb_id",
                "youtube_id",
                "youtube_url",
                "url",
                "thumbnail_url",
                "duration",
                "year",
                "description",
                "status",
                "quality",
                "width",
                "height",
                "video_codec",
                "audio_codec",
                "fps",
                "bitrate",
                "created_at",
                "updated_at",
            ]
        )

        # Data
        for video in videos:
            writer.writerow(
                [
                    video.id,
                    video.artist_id,
                    video.title,
                    video.imvdb_id,
                    video.youtube_id,
                    video.youtube_url,
                    video.url,
                    video.thumbnail_url,
                    video.duration,
                    video.year,
                    video.description,
                    video.status,
                    video.quality,
                    video.width,
                    video.height,
                    video.video_codec,
                    video.audio_codec,
                    video.fps,
                    video.bitrate,
                    video.created_at,
                    video.updated_at,
                ]
            )

        return output.getvalue()

    def _create_playlists_csv(self, playlists: List[ExportedPlaylist]) -> str:
        """Create CSV content for playlists"""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "id",
                "name",
                "description",
                "user_id",
                "is_public",
                "is_featured",
                "total_duration",
                "video_count",
                "thumbnail_url",
                "created_at",
                "updated_at",
            ]
        )

        # Data
        for playlist in playlists:
            writer.writerow(
                [
                    playlist.id,
                    playlist.name,
                    playlist.description,
                    playlist.user_id,
                    playlist.is_public,
                    playlist.is_featured,
                    playlist.total_duration,
                    playlist.video_count,
                    playlist.thumbnail_url,
                    playlist.created_at,
                    playlist.updated_at,
                ]
            )

        return output.getvalue()

    def _create_settings_csv(self, settings: List[ExportedSetting]) -> str:
        """Create CSV content for settings"""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["key", "value", "description", "created_at", "updated_at"])

        # Data
        for setting in settings:
            writer.writerow(
                [
                    setting.key,
                    setting.value,
                    setting.description,
                    setting.created_at,
                    setting.updated_at,
                ]
            )

        return output.getvalue()

    def _create_blacklist_csv(self, blacklist: List[Dict[str, Any]]) -> str:
        """Create CSV content for blacklist"""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["youtube_url", "title", "artist_name", "blacklisted_at"])

        # Data
        for entry in blacklist:
            writer.writerow(
                [
                    entry["youtube_url"],
                    entry["title"],
                    entry["artist_name"],
                    entry["blacklisted_at"],
                ]
            )

        return output.getvalue()

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _serialize_export_options(
        self, export_options: ExportOptions
    ) -> Dict[str, Any]:
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

    def _cleanup_export_files(self, operation_id: int):
        """Clean up temporary files for an export operation"""
        try:
            # Find files matching the operation ID pattern
            pattern = f"mvidarr_export_{operation_id}_*"
            for file_path in self.temp_dir.glob(pattern):
                file_path.unlink(missing_ok=True)
                logger.info(f"Cleaned up export file: {file_path.name}")
        except Exception as e:
            logger.error(
                f"Error cleaning up export files for operation {operation_id}: {e}"
            )


# Initialize service instance
export_service = ExportService()
