"""
Import Service for MVidarr 0.9.7 - Issue #76
Comprehensive import service with validation, sanitization, and data integrity checks.
"""

import csv
import gzip
import json
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.import_export_models import (
    ExportData,
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
    ExportFormat,
    ImportMode,
    ImportOperation,
    ImportOptions,
    ProcessingProgress,
    ProcessingStatus,
    ValidationError,
    ValidationLevel,
    ValidationResult,
)
from src.database.models import (
    Artist,
    Playlist,
    PlaylistEntry,
    Setting,
    User,
    Video,
    VideoBlacklist,
    VideoStatus,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.import")


class ImportService:
    """Comprehensive import service with validation and sanitization"""

    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "mvidarr_imports"
        self.temp_dir.mkdir(exist_ok=True, parents=True)

        # URL validation patterns
        self.youtube_url_pattern = re.compile(
            r"^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
        )
        self.imvdb_id_pattern = re.compile(r"^[0-9]+$")

        # Validation rules
        self.max_title_length = 500
        self.max_description_length = 5000
        self.max_name_length = 255
        self.valid_video_statuses = {status.value for status in VideoStatus}

    def start_import(
        self,
        user_id: int,
        operation_name: str,
        source_file_path: Path,
        import_options: ImportOptions,
        progress_callback: Optional[callable] = None,
    ) -> int:
        """
        Start an import operation and return the operation ID

        Args:
            user_id: ID of the user requesting import
            operation_name: Human-readable name for the operation
            source_file_path: Path to the import file
            import_options: Import configuration options
            progress_callback: Optional callback for progress updates

        Returns:
            Import operation ID for tracking
        """
        try:
            # Create import operation record
            with get_db() as db:
                operation = ImportOperation(
                    user_id=user_id,
                    operation_name=operation_name,
                    import_mode=import_options.mode,
                    validation_level=import_options.validation_level,
                    source_filename=source_file_path.name,
                    source_size_bytes=(
                        source_file_path.stat().st_size
                        if source_file_path.exists()
                        else 0
                    ),
                    import_options=self._serialize_import_options(import_options),
                    status=ProcessingStatus.PENDING,
                )
                db.add(operation)
                db.commit()
                db.refresh(operation)
                operation_id = operation.id

            logger.info(f"Started import operation {operation_id}: {operation_name}")

            # Perform the import
            self._perform_import(
                operation_id, source_file_path, import_options, progress_callback
            )

            return operation_id

        except Exception as e:
            logger.error(f"Failed to start import: {e}")
            # Update operation status to failed
            with get_db() as db:
                if "operation_id" in locals():
                    operation = (
                        db.query(ImportOperation)
                        .filter(ImportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.status = ProcessingStatus.FAILED
                        operation.error_log = [str(e)]
                        operation.completed_at = datetime.utcnow()
                        db.commit()
            raise

    def validate_import_file(
        self,
        source_file_path: Path,
        validation_level: ValidationLevel = ValidationLevel.MODERATE,
    ) -> ValidationResult:
        """
        Validate an import file without actually importing the data

        Args:
            source_file_path: Path to the import file
            validation_level: Level of validation strictness

        Returns:
            ValidationResult with detailed validation information
        """
        start_time = datetime.utcnow()

        try:
            # Parse the import file
            import_data = self._parse_import_file(source_file_path)

            # Validate the data
            validation_result = self._validate_import_data(
                import_data, validation_level
            )

            # Calculate processing time
            end_time = datetime.utcnow()
            validation_result.processing_time = (end_time - start_time).total_seconds()

            return validation_result

        except Exception as e:
            logger.error(f"Error validating import file {source_file_path}: {e}")
            return ValidationResult(
                is_valid=False,
                total_records=0,
                valid_records=0,
                invalid_records=0,
                warnings_count=0,
                errors=[
                    ValidationError(
                        record_type="file",
                        record_id=None,
                        field_name="parsing",
                        error_code="PARSE_ERROR",
                        error_message=str(e),
                        severity="error",
                    )
                ],
                processing_time=(datetime.utcnow() - start_time).total_seconds(),
            )

    def get_import_status(self, operation_id: int) -> Optional[Dict[str, Any]]:
        """Get the current status of an import operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    return None
                return operation.to_dict()
        except Exception as e:
            logger.error(
                f"Error getting import status for operation {operation_id}: {e}"
            )
            return None

    def cancel_import(self, operation_id: int, user_id: int) -> bool:
        """Cancel a running import operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(
                        and_(
                            ImportOperation.id == operation_id,
                            ImportOperation.user_id == user_id,
                            ImportOperation.status.in_(
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

                logger.info(f"Cancelled import operation {operation_id}")
                return True

        except Exception as e:
            logger.error(f"Error cancelling import operation {operation_id}: {e}")
            return False

    def _perform_import(
        self,
        operation_id: int,
        source_file_path: Path,
        import_options: ImportOptions,
        progress_callback: Optional[callable] = None,
    ):
        """Perform the actual import operation"""

        def update_progress(progress: ProcessingProgress):
            """Update operation progress in database"""
            try:
                with get_db() as db:
                    operation = (
                        db.query(ImportOperation)
                        .filter(ImportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.progress_percentage = int(progress.overall_progress)
                        operation.processed_records = progress.records_processed
                        operation.total_records = progress.total_records
                        operation.successful_records = (
                            progress.records_processed - progress.errors_count
                        )
                        operation.failed_records = progress.errors_count

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
                    f"Error updating progress for import operation {operation_id}: {e}"
                )

        try:
            logger.info(f"Starting import processing for operation {operation_id}")

            # Initialize progress
            progress = ProcessingProgress(
                current_phase="initialization",
                total_phases=5,
                current_phase_progress=0.0,
                overall_progress=0.0,
                records_processed=0,
                total_records=0,
                records_per_second=0.0,
                status_message="Initializing import operation...",
            )
            update_progress(progress)

            # Step 1: Parse import file
            progress.current_phase = "parsing"
            progress.status_message = "Parsing import file..."
            progress.current_phase_progress = 10.0
            progress.overall_progress = 2.0
            update_progress(progress)

            import_data = self._parse_import_file(source_file_path)

            # Step 2: Validate data
            progress.current_phase = "validation"
            progress.status_message = "Validating import data..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 5.0
            update_progress(progress)

            validation_result = self._validate_import_data(
                import_data, import_options.validation_level
            )

            # Store validation results
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.validation_data = {
                        "is_valid": validation_result.is_valid,
                        "total_records": validation_result.total_records,
                        "valid_records": validation_result.valid_records,
                        "invalid_records": validation_result.invalid_records,
                        "warnings_count": validation_result.warnings_count,
                        "errors_count": len(validation_result.errors),
                    }
                    db.commit()

            # Check if validation failed critically
            if (
                not validation_result.is_valid
                and import_options.validation_level == ValidationLevel.STRICT
            ):
                raise ValueError(
                    f"Validation failed with {len(validation_result.errors)} errors"
                )

            progress.total_records = validation_result.total_records
            progress.warnings_count = validation_result.warnings_count
            progress.errors_count = len(validation_result.errors)

            # Step 3: Create backup if requested
            if import_options.backup_before_import:
                progress.current_phase = "backup"
                progress.status_message = "Creating backup before import..."
                progress.current_phase_progress = 0.0
                progress.overall_progress = 15.0
                update_progress(progress)

                backup_filename = self._create_backup(operation_id)

                with get_db() as db:
                    operation = (
                        db.query(ImportOperation)
                        .filter(ImportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.backup_filename = backup_filename
                        operation.backup_created = True
                        db.commit()

            # Step 4: Import data
            progress.current_phase = "importing"
            progress.status_message = "Importing data..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 25.0
            update_progress(progress)

            import_results = self._import_data(
                import_data, import_options, progress, update_progress
            )

            # Step 5: Finalize
            progress.current_phase = "finalizing"
            progress.status_message = "Finalizing import..."
            progress.current_phase_progress = 90.0
            progress.overall_progress = 95.0
            update_progress(progress)

            # Update operation with results
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.result_data = import_results
                    db.commit()

            # Complete
            progress.current_phase = "completed"
            progress.status_message = f"Import completed successfully"
            progress.current_phase_progress = 100.0
            progress.overall_progress = 100.0
            update_progress(progress)

            logger.info(f"Import operation {operation_id} completed successfully")

        except Exception as e:
            logger.error(f"Import operation {operation_id} failed: {e}")

            # Update operation status to failed
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.status = ProcessingStatus.FAILED
                    operation.error_log = [str(e)]
                    operation.completed_at = datetime.utcnow()
                    db.commit()

            # Update progress with failure
            if "progress" in locals():
                progress.status_message = f"Import failed: {str(e)}"
                update_progress(progress)

            raise

    def _parse_import_file(self, source_file_path: Path) -> ExportData:
        """Parse import file and return structured data"""

        try:
            # Determine file format based on extension
            file_extension = source_file_path.suffix.lower()

            if file_extension == ".gz":
                # Handle compressed files
                inner_extension = source_file_path.stem.split(".")[-1].lower()
                if inner_extension == "json":
                    return self._parse_compressed_json(source_file_path)
                elif inner_extension in ["yaml", "yml"]:
                    return self._parse_compressed_yaml(source_file_path)
                elif inner_extension == "xml":
                    return self._parse_compressed_xml(source_file_path)
                else:
                    raise ValueError(
                        f"Unsupported compressed file format: {inner_extension}"
                    )

            elif file_extension == ".json":
                return self._parse_json_file(source_file_path)
            elif file_extension in [".yaml", ".yml"]:
                return self._parse_yaml_file(source_file_path)
            elif file_extension == ".xml":
                return self._parse_xml_file(source_file_path)
            elif file_extension == ".zip":
                return self._parse_csv_zip(source_file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")

        except Exception as e:
            logger.error(f"Error parsing import file {source_file_path}: {e}")
            raise

    def _parse_json_file(self, file_path: Path) -> ExportData:
        """Parse JSON format import file"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ExportData.from_dict(data)

    def _parse_compressed_json(self, file_path: Path) -> ExportData:
        """Parse compressed JSON format import file"""
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        return ExportData.from_dict(data)

    def _parse_yaml_file(self, file_path: Path) -> ExportData:
        """Parse YAML format import file"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return ExportData.from_dict(data)

    def _parse_compressed_yaml(self, file_path: Path) -> ExportData:
        """Parse compressed YAML format import file"""
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return ExportData.from_dict(data)

    def _parse_xml_file(self, file_path: Path) -> ExportData:
        """Parse XML format import file"""
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Convert XML to dictionary structure
        data = self._xml_to_dict(root)
        return ExportData.from_dict(data)

    def _parse_compressed_xml(self, file_path: Path) -> ExportData:
        """Parse compressed XML format import file"""
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            tree = ET.parse(f)
            root = tree.getroot()

        # Convert XML to dictionary structure
        data = self._xml_to_dict(root)
        return ExportData.from_dict(data)

    def _parse_csv_zip(self, file_path: Path) -> ExportData:
        """Parse CSV ZIP format import file"""

        import_data = ExportData(
            manifest=None,  # Will be loaded from manifest.json
            artists=[],
            videos=[],
            playlists=[],
            settings=[],
            blacklist=[],
        )

        with zipfile.ZipFile(file_path, "r") as zip_file:
            # Load manifest if available
            if "manifest.json" in zip_file.namelist():
                with zip_file.open("manifest.json") as f:
                    manifest_data = json.load(f)
                    import_data.manifest = manifest_data

            # Load artists CSV
            if "artists.csv" in zip_file.namelist():
                with zip_file.open("artists.csv") as f:
                    csv_content = f.read().decode("utf-8")
                    import_data.artists = self._parse_artists_csv(csv_content)

            # Load videos CSV
            if "videos.csv" in zip_file.namelist():
                with zip_file.open("videos.csv") as f:
                    csv_content = f.read().decode("utf-8")
                    import_data.videos = self._parse_videos_csv(csv_content)

            # Load playlists CSV
            if "playlists.csv" in zip_file.namelist():
                with zip_file.open("playlists.csv") as f:
                    csv_content = f.read().decode("utf-8")
                    import_data.playlists = self._parse_playlists_csv(csv_content)

            # Load settings CSV
            if "settings.csv" in zip_file.namelist():
                with zip_file.open("settings.csv") as f:
                    csv_content = f.read().decode("utf-8")
                    import_data.settings = self._parse_settings_csv(csv_content)

            # Load blacklist CSV
            if "blacklist.csv" in zip_file.namelist():
                with zip_file.open("blacklist.csv") as f:
                    csv_content = f.read().decode("utf-8")
                    import_data.blacklist = self._parse_blacklist_csv(csv_content)

        return import_data

    def _validate_import_data(
        self, import_data: ExportData, validation_level: ValidationLevel
    ) -> ValidationResult:
        """Validate import data and return validation result"""

        errors = []
        warnings = []
        total_records = 0
        valid_records = 0

        try:
            # Validate artists
            for i, artist in enumerate(import_data.artists):
                total_records += 1
                artist_errors, artist_warnings = self._validate_artist(
                    artist, f"artist_{i}"
                )
                errors.extend(artist_errors)
                warnings.extend(artist_warnings)
                if not artist_errors:
                    valid_records += 1

            # Validate videos
            for i, video in enumerate(import_data.videos):
                total_records += 1
                video_errors, video_warnings = self._validate_video(video, f"video_{i}")
                errors.extend(video_errors)
                warnings.extend(video_warnings)
                if not video_errors:
                    valid_records += 1

            # Validate playlists
            for i, playlist in enumerate(import_data.playlists):
                total_records += 1
                playlist_errors, playlist_warnings = self._validate_playlist(
                    playlist, f"playlist_{i}"
                )
                errors.extend(playlist_errors)
                warnings.extend(playlist_warnings)
                if not playlist_errors:
                    valid_records += 1

            # Validate settings
            for i, setting in enumerate(import_data.settings):
                total_records += 1
                setting_errors, setting_warnings = self._validate_setting(
                    setting, f"setting_{i}"
                )
                errors.extend(setting_errors)
                warnings.extend(setting_warnings)
                if not setting_errors:
                    valid_records += 1

            # Validate blacklist entries
            for i, blacklist_entry in enumerate(import_data.blacklist):
                total_records += 1
                blacklist_errors, blacklist_warnings = self._validate_blacklist_entry(
                    blacklist_entry, f"blacklist_{i}"
                )
                errors.extend(blacklist_errors)
                warnings.extend(blacklist_warnings)
                if not blacklist_errors:
                    valid_records += 1

            # Cross-reference validation
            cross_ref_errors, cross_ref_warnings = self._validate_cross_references(
                import_data
            )
            errors.extend(cross_ref_errors)
            warnings.extend(cross_ref_warnings)

            # Determine overall validity
            is_valid = True
            if validation_level == ValidationLevel.STRICT and errors:
                is_valid = False
            elif validation_level == ValidationLevel.MODERATE and len(errors) > (
                total_records * 0.1
            ):  # More than 10% errors
                is_valid = False
            # PERMISSIVE level is always considered valid unless there are critical errors

            return ValidationResult(
                is_valid=is_valid,
                total_records=total_records,
                valid_records=valid_records,
                invalid_records=total_records - valid_records,
                warnings_count=len(warnings),
                errors=errors,
                warnings=warnings,
            )

        except Exception as e:
            logger.error(f"Error during validation: {e}")
            return ValidationResult(
                is_valid=False,
                total_records=total_records,
                valid_records=0,
                invalid_records=total_records,
                warnings_count=0,
                errors=[
                    ValidationError(
                        record_type="validation",
                        record_id=None,
                        field_name="general",
                        error_code="VALIDATION_ERROR",
                        error_message=str(e),
                        severity="error",
                    )
                ],
            )

    def _validate_artist(
        self, artist: ExportedArtist, record_id: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate a single artist record"""
        errors = []
        warnings = []

        # Required field validation
        if not artist.name or len(artist.name.strip()) == 0:
            errors.append(
                ValidationError(
                    record_type="artist",
                    record_id=record_id,
                    field_name="name",
                    error_code="REQUIRED_FIELD",
                    error_message="Artist name is required",
                    suggested_fix="Provide a valid artist name",
                )
            )

        # Length validation
        if artist.name and len(artist.name) > self.max_name_length:
            errors.append(
                ValidationError(
                    record_type="artist",
                    record_id=record_id,
                    field_name="name",
                    error_code="LENGTH_EXCEEDED",
                    error_message=f"Artist name exceeds {self.max_name_length} characters",
                    suggested_fix=f"Truncate name to {self.max_name_length} characters",
                )
            )

        # External ID validation
        if artist.imvdb_id and not self.imvdb_id_pattern.match(artist.imvdb_id):
            warnings.append(
                ValidationError(
                    record_type="artist",
                    record_id=record_id,
                    field_name="imvdb_id",
                    error_code="INVALID_FORMAT",
                    error_message="IMVDB ID should be numeric",
                    suggested_fix="Use numeric IMVDB ID",
                    severity="warning",
                )
            )

        # URL validation
        if artist.thumbnail_url and not self._is_valid_url(artist.thumbnail_url):
            warnings.append(
                ValidationError(
                    record_type="artist",
                    record_id=record_id,
                    field_name="thumbnail_url",
                    error_code="INVALID_URL",
                    error_message="Invalid thumbnail URL format",
                    suggested_fix="Use a valid HTTP/HTTPS URL",
                    severity="warning",
                )
            )

        return errors, warnings

    def _validate_video(
        self, video: ExportedVideo, record_id: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate a single video record"""
        errors = []
        warnings = []

        # Required field validation
        if not video.title or len(video.title.strip()) == 0:
            errors.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="title",
                    error_code="REQUIRED_FIELD",
                    error_message="Video title is required",
                    suggested_fix="Provide a valid video title",
                )
            )

        if not video.artist_id:
            errors.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="artist_id",
                    error_code="REQUIRED_FIELD",
                    error_message="Video must be associated with an artist",
                    suggested_fix="Provide a valid artist_id",
                )
            )

        # Length validation
        if video.title and len(video.title) > self.max_title_length:
            errors.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="title",
                    error_code="LENGTH_EXCEEDED",
                    error_message=f"Video title exceeds {self.max_title_length} characters",
                    suggested_fix=f"Truncate title to {self.max_title_length} characters",
                )
            )

        if video.description and len(video.description) > self.max_description_length:
            warnings.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="description",
                    error_code="LENGTH_EXCEEDED",
                    error_message=f"Description exceeds {self.max_description_length} characters",
                    suggested_fix=f"Truncate description to {self.max_description_length} characters",
                    severity="warning",
                )
            )

        # Status validation
        if video.status not in self.valid_video_statuses:
            errors.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="status",
                    error_code="INVALID_VALUE",
                    error_message=f"Invalid video status: {video.status}",
                    suggested_fix=f"Use one of: {', '.join(self.valid_video_statuses)}",
                )
            )

        # URL validation
        if video.youtube_url and not self.youtube_url_pattern.match(video.youtube_url):
            warnings.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="youtube_url",
                    error_code="INVALID_URL",
                    error_message="Invalid YouTube URL format",
                    suggested_fix="Use a valid YouTube watch URL",
                    severity="warning",
                )
            )

        # Duration validation
        if video.duration is not None and (
            video.duration < 0 or video.duration > 86400
        ):  # 24 hours max
            warnings.append(
                ValidationError(
                    record_type="video",
                    record_id=record_id,
                    field_name="duration",
                    error_code="INVALID_VALUE",
                    error_message="Duration should be between 0 and 86400 seconds",
                    suggested_fix="Set a reasonable duration value",
                    severity="warning",
                )
            )

        return errors, warnings

    def _validate_playlist(
        self, playlist: ExportedPlaylist, record_id: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate a single playlist record"""
        errors = []
        warnings = []

        # Required field validation
        if not playlist.name or len(playlist.name.strip()) == 0:
            errors.append(
                ValidationError(
                    record_type="playlist",
                    record_id=record_id,
                    field_name="name",
                    error_code="REQUIRED_FIELD",
                    error_message="Playlist name is required",
                    suggested_fix="Provide a valid playlist name",
                )
            )

        if not playlist.user_id:
            errors.append(
                ValidationError(
                    record_type="playlist",
                    record_id=record_id,
                    field_name="user_id",
                    error_code="REQUIRED_FIELD",
                    error_message="Playlist must be associated with a user",
                    suggested_fix="Provide a valid user_id",
                )
            )

        # Length validation
        if playlist.name and len(playlist.name) > self.max_name_length:
            errors.append(
                ValidationError(
                    record_type="playlist",
                    record_id=record_id,
                    field_name="name",
                    error_code="LENGTH_EXCEEDED",
                    error_message=f"Playlist name exceeds {self.max_name_length} characters",
                    suggested_fix=f"Truncate name to {self.max_name_length} characters",
                )
            )

        # Entry validation
        if playlist.entries:
            for i, entry in enumerate(playlist.entries):
                if "video_id" not in entry or not entry["video_id"]:
                    errors.append(
                        ValidationError(
                            record_type="playlist",
                            record_id=f"{record_id}_entry_{i}",
                            field_name="video_id",
                            error_code="REQUIRED_FIELD",
                            error_message="Playlist entry must reference a video",
                            suggested_fix="Provide a valid video_id for the entry",
                        )
                    )

        return errors, warnings

    def _validate_setting(
        self, setting: ExportedSetting, record_id: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate a single setting record"""
        errors = []
        warnings = []

        # Required field validation
        if not setting.key or len(setting.key.strip()) == 0:
            errors.append(
                ValidationError(
                    record_type="setting",
                    record_id=record_id,
                    field_name="key",
                    error_code="REQUIRED_FIELD",
                    error_message="Setting key is required",
                    suggested_fix="Provide a valid setting key",
                )
            )

        # Key format validation
        if setting.key and not re.match(r"^[a-zA-Z0-9_.-]+$", setting.key):
            warnings.append(
                ValidationError(
                    record_type="setting",
                    record_id=record_id,
                    field_name="key",
                    error_code="INVALID_FORMAT",
                    error_message="Setting key contains invalid characters",
                    suggested_fix="Use alphanumeric characters, underscores, dots, and hyphens only",
                    severity="warning",
                )
            )

        return errors, warnings

    def _validate_blacklist_entry(
        self, entry: Dict[str, Any], record_id: str
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate a single blacklist entry"""
        errors = []
        warnings = []

        # Required field validation
        if not entry.get("youtube_url"):
            errors.append(
                ValidationError(
                    record_type="blacklist",
                    record_id=record_id,
                    field_name="youtube_url",
                    error_code="REQUIRED_FIELD",
                    error_message="Blacklist entry must have a YouTube URL",
                    suggested_fix="Provide a valid YouTube URL",
                )
            )

        # URL validation
        youtube_url = entry.get("youtube_url", "")
        if youtube_url and not self.youtube_url_pattern.match(youtube_url):
            warnings.append(
                ValidationError(
                    record_type="blacklist",
                    record_id=record_id,
                    field_name="youtube_url",
                    error_code="INVALID_URL",
                    error_message="Invalid YouTube URL format",
                    suggested_fix="Use a valid YouTube watch URL",
                    severity="warning",
                )
            )

        return errors, warnings

    def _validate_cross_references(
        self, import_data: ExportData
    ) -> Tuple[List[ValidationError], List[ValidationError]]:
        """Validate cross-references between entities"""
        errors = []
        warnings = []

        # Build ID mappings
        artist_ids = {artist.id for artist in import_data.artists}
        video_ids = {video.id for video in import_data.videos}

        # Validate video -> artist references
        for i, video in enumerate(import_data.videos):
            if video.artist_id and video.artist_id not in artist_ids:
                errors.append(
                    ValidationError(
                        record_type="video",
                        record_id=f"video_{i}",
                        field_name="artist_id",
                        error_code="INVALID_REFERENCE",
                        error_message=f"Video references non-existent artist ID: {video.artist_id}",
                        suggested_fix="Ensure the referenced artist exists in the import data",
                    )
                )

        # Validate playlist entries -> video references
        for i, playlist in enumerate(import_data.playlists):
            if playlist.entries:
                for j, entry in enumerate(playlist.entries):
                    video_id = entry.get("video_id")
                    if video_id and video_id not in video_ids:
                        errors.append(
                            ValidationError(
                                record_type="playlist",
                                record_id=f"playlist_{i}_entry_{j}",
                                field_name="video_id",
                                error_code="INVALID_REFERENCE",
                                error_message=f"Playlist entry references non-existent video ID: {video_id}",
                                suggested_fix="Ensure the referenced video exists in the import data",
                            )
                        )

        return errors, warnings

    def _import_data(
        self,
        import_data: ExportData,
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, Any]:
        """Import the validated data into the database"""

        import_results = {
            "artists_imported": 0,
            "artists_updated": 0,
            "artists_skipped": 0,
            "videos_imported": 0,
            "videos_updated": 0,
            "videos_skipped": 0,
            "playlists_imported": 0,
            "playlists_updated": 0,
            "playlists_skipped": 0,
            "settings_imported": 0,
            "settings_updated": 0,
            "settings_skipped": 0,
            "blacklist_imported": 0,
            "errors": [],
        }

        try:
            with get_db() as db:
                # Import in order of dependencies: Settings -> Artists -> Videos -> Playlists -> Blacklist

                # Import settings first
                if import_data.settings:
                    settings_results = self._import_settings(
                        db,
                        import_data.settings,
                        import_options,
                        progress,
                        update_progress,
                    )
                    import_results.update(settings_results)

                # Import artists
                if import_data.artists:
                    artist_results = self._import_artists(
                        db,
                        import_data.artists,
                        import_options,
                        progress,
                        update_progress,
                    )
                    import_results.update(artist_results)

                # Import videos
                if import_data.videos:
                    video_results = self._import_videos(
                        db,
                        import_data.videos,
                        import_options,
                        progress,
                        update_progress,
                    )
                    import_results.update(video_results)

                # Import playlists
                if import_data.playlists:
                    playlist_results = self._import_playlists(
                        db,
                        import_data.playlists,
                        import_options,
                        progress,
                        update_progress,
                    )
                    import_results.update(playlist_results)

                # Import blacklist
                if import_data.blacklist:
                    blacklist_results = self._import_blacklist(
                        db,
                        import_data.blacklist,
                        import_options,
                        progress,
                        update_progress,
                    )
                    import_results.update(blacklist_results)

                # Commit all changes
                db.commit()

                return import_results

        except Exception as e:
            logger.error(f"Error during data import: {e}")
            import_results["errors"].append(str(e))
            return import_results

    def _import_artists(
        self,
        db: Session,
        artists: List[ExportedArtist],
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, int]:
        """Import artists into the database"""

        results = {"artists_imported": 0, "artists_updated": 0, "artists_skipped": 0}

        for artist_data in artists:
            try:
                # Check if artist already exists
                existing_artist = None
                if import_options.preserve_ids and artist_data.id:
                    existing_artist = (
                        db.query(Artist).filter(Artist.id == artist_data.id).first()
                    )
                else:
                    # Look for artist by name and external IDs
                    existing_artist = (
                        db.query(Artist).filter(Artist.name == artist_data.name).first()
                    )
                    if not existing_artist and artist_data.imvdb_id:
                        existing_artist = (
                            db.query(Artist)
                            .filter(Artist.imvdb_id == artist_data.imvdb_id)
                            .first()
                        )

                if existing_artist:
                    if import_options.mode == ImportMode.MERGE_SKIP:
                        results["artists_skipped"] += 1
                        continue
                    elif import_options.mode in [
                        ImportMode.MERGE_UPDATE,
                        ImportMode.REPLACE_ALL,
                    ]:
                        # Update existing artist
                        self._update_artist_from_data(
                            existing_artist, artist_data, import_options
                        )
                        results["artists_updated"] += 1
                else:
                    # Create new artist
                    new_artist = self._create_artist_from_data(
                        artist_data, import_options
                    )
                    db.add(new_artist)
                    results["artists_imported"] += 1

                # Update progress
                progress.records_processed += 1
                progress.status_message = f"Importing artist: {artist_data.name}"
                progress.overall_progress = min(
                    90.0,
                    25.0 + (progress.records_processed / progress.total_records) * 60.0,
                )
                update_progress(progress)

                # Commit in batches
                if progress.records_processed % import_options.batch_size == 0:
                    db.commit()

            except Exception as e:
                logger.error(f"Error importing artist {artist_data.name}: {e}")
                progress.errors_count += 1
                if progress.errors_count >= import_options.max_errors:
                    raise ValueError(
                        f"Too many errors ({progress.errors_count}), aborting import"
                    )

        return results

    def _import_videos(
        self,
        db: Session,
        videos: List[ExportedVideo],
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, int]:
        """Import videos into the database"""

        results = {"videos_imported": 0, "videos_updated": 0, "videos_skipped": 0}

        for video_data in videos:
            try:
                # Check if video already exists
                existing_video = None
                if import_options.preserve_ids and video_data.id:
                    existing_video = (
                        db.query(Video).filter(Video.id == video_data.id).first()
                    )
                else:
                    # Look for video by title, artist, and external IDs
                    existing_video = (
                        db.query(Video)
                        .filter(
                            Video.title == video_data.title,
                            Video.artist_id == video_data.artist_id,
                        )
                        .first()
                    )
                    if not existing_video and video_data.youtube_id:
                        existing_video = (
                            db.query(Video)
                            .filter(Video.youtube_id == video_data.youtube_id)
                            .first()
                        )
                    if not existing_video and video_data.imvdb_id:
                        existing_video = (
                            db.query(Video)
                            .filter(Video.imvdb_id == video_data.imvdb_id)
                            .first()
                        )

                if existing_video:
                    if import_options.mode == ImportMode.MERGE_SKIP:
                        results["videos_skipped"] += 1
                        continue
                    elif import_options.mode in [
                        ImportMode.MERGE_UPDATE,
                        ImportMode.REPLACE_ALL,
                    ]:
                        # Update existing video
                        self._update_video_from_data(
                            existing_video, video_data, import_options
                        )
                        results["videos_updated"] += 1
                else:
                    # Verify artist exists
                    artist = (
                        db.query(Artist)
                        .filter(Artist.id == video_data.artist_id)
                        .first()
                    )
                    if not artist and import_options.create_missing_artists:
                        # Create a minimal artist record
                        artist = Artist(
                            name=f"Unknown Artist {video_data.artist_id}",
                            monitored=False,
                            auto_download=False,
                        )
                        db.add(artist)
                        db.flush()  # Get the ID
                        video_data.artist_id = artist.id
                    elif not artist:
                        logger.warning(
                            f"Skipping video {video_data.title}: artist {video_data.artist_id} not found"
                        )
                        results["videos_skipped"] += 1
                        continue

                    # Validate video has URL before importing
                    has_url = bool(video_data.url or video_data.youtube_url or video_data.youtube_id)
                    
                    if not has_url:
                        # Try to find URL via IMVDB before rejecting the video
                        try:
                            from src.services.imvdb_service import IMVDbService
                            imvdb_service = IMVDbService()
                            
                            # Get artist name for IMVDB search
                            artist_name = artist.name if artist else f"Unknown Artist {video_data.artist_id}"
                            logger.info(f"Video import: No URL found for '{artist_name} - {video_data.title}', checking IMVDB")
                            
                            search_results = imvdb_service.search_videos(artist_name, video_data.title)
                            
                            if search_results and len(search_results) > 0:
                                # Get the first result
                                imvdb_video = search_results[0]
                                
                                # Extract YouTube URL if available
                                youtube_url = None
                                if 'sources' in imvdb_video:
                                    for source in imvdb_video['sources']:
                                        if source.get('source') == 'youtube' and source.get('source_data'):
                                            youtube_url = source['source_data']
                                            break
                                
                                if youtube_url:
                                    logger.info(f"✅ Found YouTube URL from IMVDB during import: {youtube_url}")
                                    
                                    # Update video_data with found URL
                                    video_data.url = youtube_url
                                    video_data.youtube_url = youtube_url
                                    
                                    # Extract YouTube ID from URL
                                    if 'watch?v=' in youtube_url:
                                        video_data.youtube_id = youtube_url.split('watch?v=')[1].split('&')[0]
                                    elif 'youtu.be/' in youtube_url:
                                        video_data.youtube_id = youtube_url.split('youtu.be/')[1].split('?')[0]
                                    
                                    # Also update IMVDB metadata if available
                                    if 'id' in imvdb_video:
                                        video_data.imvdb_id = str(imvdb_video['id'])
                                    if imvdb_video:
                                        video_data.imvdb_metadata = imvdb_video
                                    
                                    has_url = True
                                    logger.info(f"✅ Updated video import data with IMVDB URL")
                                    
                        except Exception as imvdb_error:
                            logger.warning(f"IMVDB search failed during import for '{video_data.title}': {imvdb_error}")
                    
                    if not has_url:
                        logger.warning(f"Skipping video import '{video_data.title}': No URL found (not in IMVDB or provided data)")
                        results["videos_skipped"] += 1
                        continue

                    # Create new video (now guaranteed to have URL)
                    new_video = self._create_video_from_data(video_data, import_options)
                    db.add(new_video)
                    results["videos_imported"] += 1

                # Update progress
                progress.records_processed += 1
                progress.status_message = f"Importing video: {video_data.title}"
                progress.overall_progress = min(
                    90.0,
                    25.0 + (progress.records_processed / progress.total_records) * 60.0,
                )
                update_progress(progress)

                # Commit in batches
                if progress.records_processed % import_options.batch_size == 0:
                    db.commit()

            except Exception as e:
                logger.error(f"Error importing video {video_data.title}: {e}")
                progress.errors_count += 1
                if progress.errors_count >= import_options.max_errors:
                    raise ValueError(
                        f"Too many errors ({progress.errors_count}), aborting import"
                    )

        return results

    # Continue with additional helper methods...
    # (Due to length constraints, I'll continue with the key remaining methods)

    def _create_artist_from_data(
        self, artist_data: ExportedArtist, import_options: ImportOptions
    ) -> Artist:
        """Create a new Artist object from ExportedArtist data"""
        artist = Artist(
            name=artist_data.name,
            imvdb_id=artist_data.imvdb_id,
            spotify_id=artist_data.spotify_id,
            lastfm_name=artist_data.lastfm_name,
            thumbnail_url=(
                artist_data.thumbnail_url
                if import_options.sanitize_file_paths
                else None
            ),
            auto_download=artist_data.auto_download,
            monitored=artist_data.monitored,
            folder_path=(
                self._sanitize_path(artist_data.folder_path)
                if import_options.sanitize_file_paths and artist_data.folder_path
                else artist_data.folder_path
            ),
            genres=", ".join(artist_data.genres) if artist_data.genres else None,
            source=artist_data.source,
            imvdb_metadata=artist_data.imvdb_metadata,
        )

        if artist_data.keywords:
            artist.keywords = json.dumps(artist_data.keywords)

        if import_options.preserve_ids and artist_data.id:
            artist.id = artist_data.id

        return artist

    def _create_video_from_data(
        self, video_data: ExportedVideo, import_options: ImportOptions
    ) -> Video:
        """Create a new Video object from ExportedVideo data"""

        # Reconstruct FFmpeg metadata
        video_metadata = video_data.video_metadata or {}
        if video_data.ffmpeg_extracted:
            video_metadata.update(
                {
                    "width": video_data.width,
                    "height": video_data.height,
                    "video_codec": video_data.video_codec,
                    "audio_codec": video_data.audio_codec,
                    "fps": video_data.fps,
                    "bitrate": video_data.bitrate,
                    "ffmpeg_extracted": video_data.ffmpeg_extracted,
                }
            )

        video = Video(
            artist_id=video_data.artist_id,
            title=video_data.title,
            imvdb_id=video_data.imvdb_id,
            youtube_id=video_data.youtube_id,
            youtube_url=video_data.youtube_url,
            url=video_data.url,
            playlist_id=video_data.playlist_id,
            thumbnail_url=video_data.thumbnail_url,
            duration=video_data.duration,
            year=video_data.year,
            release_date=(
                datetime.fromisoformat(video_data.release_date)
                if video_data.release_date
                else None
            ),
            description=video_data.description,
            view_count=video_data.view_count,
            like_count=video_data.like_count,
            status=(
                VideoStatus(video_data.status)
                if video_data.status in self.valid_video_statuses
                else VideoStatus.WANTED
            ),
            quality=video_data.quality,
            video_metadata=video_metadata,
            imvdb_metadata=video_data.imvdb_metadata,
            local_path=(
                self._sanitize_path(video_data.local_path)
                if import_options.sanitize_file_paths and video_data.local_path
                else video_data.local_path
            ),
        )

        # Handle JSON fields
        if video_data.genres:
            video.genres = json.dumps(video_data.genres)
        if video_data.directors:
            video.directors = json.dumps(video_data.directors)
        if video_data.producers:
            video.producers = json.dumps(video_data.producers)

        if import_options.preserve_ids and video_data.id:
            video.id = video_data.id

        return video

    def _sanitize_path(self, path: str) -> str:
        """Sanitize file paths for cross-platform compatibility"""
        if not path:
            return path

        # Convert to Path object for platform-independent handling
        sanitized = Path(path)

        # Convert to string with forward slashes for consistency
        return str(sanitized).replace("\\", "/")

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid"""
        return url and (url.startswith("http://") or url.startswith("https://"))

    def _serialize_import_options(
        self, import_options: ImportOptions
    ) -> Dict[str, Any]:
        """Serialize import options for database storage"""
        return {
            "mode": import_options.mode.value,
            "validation_level": import_options.validation_level.value,
            "overwrite_duplicates": import_options.overwrite_duplicates,
            "update_existing": import_options.update_existing,
            "skip_invalid_records": import_options.skip_invalid_records,
            "create_missing_artists": import_options.create_missing_artists,
            "preserve_ids": import_options.preserve_ids,
            "sanitize_file_paths": import_options.sanitize_file_paths,
            "validate_external_ids": import_options.validate_external_ids,
            "batch_size": import_options.batch_size,
            "max_errors": import_options.max_errors,
            "backup_before_import": import_options.backup_before_import,
            "dry_run": import_options.dry_run,
        }

    def _import_playlists(
        self,
        db: Session,
        playlists: List[ExportedPlaylist],
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, int]:
        """Import playlists into the database"""

        results = {
            "playlists_imported": 0,
            "playlists_updated": 0,
            "playlists_skipped": 0,
        }

        for playlist_data in playlists:
            try:
                # Check if playlist already exists
                existing_playlist = None
                if import_options.preserve_ids and playlist_data.id:
                    existing_playlist = (
                        db.query(Playlist)
                        .filter(Playlist.id == playlist_data.id)
                        .first()
                    )
                else:
                    # Look for playlist by name and user
                    existing_playlist = (
                        db.query(Playlist)
                        .filter(
                            Playlist.name == playlist_data.name,
                            Playlist.user_id == playlist_data.user_id,
                        )
                        .first()
                    )

                if existing_playlist:
                    if import_options.mode == ImportMode.MERGE_SKIP:
                        results["playlists_skipped"] += 1
                        continue
                    elif import_options.mode in [
                        ImportMode.MERGE_UPDATE,
                        ImportMode.REPLACE_ALL,
                    ]:
                        # Update existing playlist
                        self._update_playlist_from_data(
                            existing_playlist, playlist_data, import_options, db
                        )
                        results["playlists_updated"] += 1
                else:
                    # Create new playlist
                    new_playlist = self._create_playlist_from_data(
                        playlist_data, import_options, db
                    )
                    if new_playlist:
                        db.add(new_playlist)
                        results["playlists_imported"] += 1
                    else:
                        results["playlists_skipped"] += 1

                # Update progress
                progress.records_processed += 1
                progress.status_message = f"Importing playlist: {playlist_data.name}"
                progress.overall_progress = min(
                    90.0,
                    25.0 + (progress.records_processed / progress.total_records) * 60.0,
                )
                update_progress(progress)

                # Commit in batches
                if progress.records_processed % import_options.batch_size == 0:
                    db.commit()

            except Exception as e:
                logger.error(f"Error importing playlist {playlist_data.name}: {e}")
                progress.errors_count += 1
                if progress.errors_count >= import_options.max_errors:
                    raise ValueError(
                        f"Too many errors ({progress.errors_count}), aborting import"
                    )

        return results

    def _import_settings(
        self,
        db: Session,
        settings: List[ExportedSetting],
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, int]:
        """Import settings into the database"""

        results = {"settings_imported": 0, "settings_updated": 0, "settings_skipped": 0}

        for setting_data in settings:
            try:
                # Check if setting already exists
                existing_setting = (
                    db.query(Setting).filter(Setting.key == setting_data.key).first()
                )

                if existing_setting:
                    if import_options.mode == ImportMode.MERGE_SKIP:
                        results["settings_skipped"] += 1
                        continue
                    elif import_options.mode in [
                        ImportMode.MERGE_UPDATE,
                        ImportMode.REPLACE_ALL,
                    ]:
                        # Update existing setting
                        existing_setting.value = setting_data.value
                        existing_setting.description = setting_data.description
                        existing_setting.updated_at = datetime.utcnow()
                        results["settings_updated"] += 1
                else:
                    # Create new setting
                    new_setting = Setting(
                        key=setting_data.key,
                        value=setting_data.value,
                        description=setting_data.description,
                    )
                    db.add(new_setting)
                    results["settings_imported"] += 1

                # Update progress
                progress.records_processed += 1
                progress.status_message = f"Importing setting: {setting_data.key}"
                progress.overall_progress = min(
                    90.0,
                    25.0 + (progress.records_processed / progress.total_records) * 60.0,
                )
                update_progress(progress)

            except Exception as e:
                logger.error(f"Error importing setting {setting_data.key}: {e}")
                progress.errors_count += 1
                if progress.errors_count >= import_options.max_errors:
                    raise ValueError(
                        f"Too many errors ({progress.errors_count}), aborting import"
                    )

        return results

    def _import_blacklist(
        self,
        db: Session,
        blacklist: List[Dict[str, Any]],
        import_options: ImportOptions,
        progress: ProcessingProgress,
        update_progress: callable,
    ) -> Dict[str, int]:
        """Import blacklist entries into the database"""

        results = {"blacklist_imported": 0}

        for blacklist_data in blacklist:
            try:
                youtube_url = blacklist_data.get("youtube_url")
                if not youtube_url:
                    continue

                # Check if blacklist entry already exists
                existing_entry = (
                    db.query(VideoBlacklist)
                    .filter(VideoBlacklist.youtube_url == youtube_url)
                    .first()
                )

                if not existing_entry:
                    # Create new blacklist entry
                    new_entry = VideoBlacklist(
                        youtube_url=youtube_url,
                        reason=blacklist_data.get("reason", "Imported from backup"),
                        created_at=(
                            datetime.fromisoformat(blacklist_data.get("created_at"))
                            if blacklist_data.get("created_at")
                            else datetime.utcnow()
                        ),
                    )
                    db.add(new_entry)
                    results["blacklist_imported"] += 1

                # Update progress
                progress.records_processed += 1
                progress.status_message = (
                    f"Importing blacklist entry: {youtube_url[:50]}..."
                )
                progress.overall_progress = min(
                    90.0,
                    25.0 + (progress.records_processed / progress.total_records) * 60.0,
                )
                update_progress(progress)

            except Exception as e:
                logger.error(f"Error importing blacklist entry: {e}")
                progress.errors_count += 1
                if progress.errors_count >= import_options.max_errors:
                    raise ValueError(
                        f"Too many errors ({progress.errors_count}), aborting import"
                    )

        return results

    def _create_playlist_from_data(
        self,
        playlist_data: ExportedPlaylist,
        import_options: ImportOptions,
        db: Session,
    ) -> Optional[Playlist]:
        """Create a new Playlist object from ExportedPlaylist data"""

        # Verify user exists
        user = db.query(User).filter(User.id == playlist_data.user_id).first()
        if not user:
            logger.warning(
                f"Skipping playlist {playlist_data.name}: user {playlist_data.user_id} not found"
            )
            return None

        playlist = Playlist(
            name=playlist_data.name,
            description=playlist_data.description,
            user_id=playlist_data.user_id,
            is_public=playlist_data.is_public,
            is_featured=playlist_data.is_featured,
            total_duration=playlist_data.total_duration,
            video_count=len(playlist_data.entries) if playlist_data.entries else 0,
            playlist_metadata=playlist_data.playlist_metadata,
            thumbnail_url=playlist_data.thumbnail_url,
        )

        if import_options.preserve_ids and playlist_data.id:
            playlist.id = playlist_data.id

        return playlist

    def _update_artist_from_data(
        self, artist: Artist, artist_data: ExportedArtist, import_options: ImportOptions
    ):
        """Update existing Artist object with ExportedArtist data"""
        artist.name = artist_data.name
        if artist_data.imvdb_id:
            artist.imvdb_id = artist_data.imvdb_id
        if artist_data.spotify_id:
            artist.spotify_id = artist_data.spotify_id
        if artist_data.lastfm_name:
            artist.lastfm_name = artist_data.lastfm_name
        if artist_data.thumbnail_url and not import_options.sanitize_file_paths:
            artist.thumbnail_url = artist_data.thumbnail_url

        artist.auto_download = artist_data.auto_download
        artist.monitored = artist_data.monitored

        if artist_data.folder_path:
            artist.folder_path = (
                self._sanitize_path(artist_data.folder_path)
                if import_options.sanitize_file_paths
                else artist_data.folder_path
            )
        if artist_data.genres:
            artist.genres = ", ".join(artist_data.genres)
        if artist_data.source:
            artist.source = artist_data.source
        if artist_data.imvdb_metadata:
            artist.imvdb_metadata = artist_data.imvdb_metadata
        if artist_data.keywords:
            artist.keywords = json.dumps(artist_data.keywords)

        artist.updated_at = datetime.utcnow()

    def _update_video_from_data(
        self, video: Video, video_data: ExportedVideo, import_options: ImportOptions
    ):
        """Update existing Video object with ExportedVideo data"""
        video.title = video_data.title
        video.artist_id = video_data.artist_id

        if video_data.imvdb_id:
            video.imvdb_id = video_data.imvdb_id
        if video_data.youtube_id:
            video.youtube_id = video_data.youtube_id
        if video_data.youtube_url:
            video.youtube_url = video_data.youtube_url
        if video_data.url:
            video.url = video_data.url
        if video_data.playlist_id:
            video.playlist_id = video_data.playlist_id
        if video_data.thumbnail_url:
            video.thumbnail_url = video_data.thumbnail_url

        video.duration = video_data.duration
        video.year = video_data.year

        if video_data.release_date:
            video.release_date = datetime.fromisoformat(video_data.release_date)
        if video_data.description:
            video.description = video_data.description

        video.view_count = video_data.view_count
        video.like_count = video_data.like_count
        video.quality = video_data.quality

        if video_data.status in self.valid_video_statuses:
            video.status = VideoStatus(video_data.status)

        # Update metadata
        video_metadata = video_data.video_metadata or {}
        if video_data.ffmpeg_extracted:
            video_metadata.update(
                {
                    "width": video_data.width,
                    "height": video_data.height,
                    "video_codec": video_data.video_codec,
                    "audio_codec": video_data.audio_codec,
                    "fps": video_data.fps,
                    "bitrate": video_data.bitrate,
                    "ffmpeg_extracted": video_data.ffmpeg_extracted,
                }
            )
        video.video_metadata = video_metadata

        if video_data.imvdb_metadata:
            video.imvdb_metadata = video_data.imvdb_metadata

        if video_data.local_path:
            video.local_path = (
                self._sanitize_path(video_data.local_path)
                if import_options.sanitize_file_paths
                else video_data.local_path
            )

        # Handle JSON fields
        if video_data.genres:
            video.genres = json.dumps(video_data.genres)
        if video_data.directors:
            video.directors = json.dumps(video_data.directors)
        if video_data.producers:
            video.producers = json.dumps(video_data.producers)

        video.updated_at = datetime.utcnow()

    def _update_playlist_from_data(
        self,
        playlist: Playlist,
        playlist_data: ExportedPlaylist,
        import_options: ImportOptions,
        db: Session,
    ):
        """Update existing Playlist object with ExportedPlaylist data"""
        playlist.name = playlist_data.name
        playlist.description = playlist_data.description
        playlist.is_public = playlist_data.is_public
        playlist.is_featured = playlist_data.is_featured
        playlist.total_duration = playlist_data.total_duration
        playlist.playlist_metadata = playlist_data.playlist_metadata
        playlist.thumbnail_url = playlist_data.thumbnail_url
        playlist.updated_at = datetime.utcnow()

        # Update playlist entries if provided
        if playlist_data.entries:
            # Remove existing entries
            db.query(PlaylistEntry).filter(
                PlaylistEntry.playlist_id == playlist.id
            ).delete()

            # Add new entries
            for entry_data in playlist_data.entries:
                video_id = entry_data.get("video_id")
                if video_id and db.query(Video).filter(Video.id == video_id).first():
                    new_entry = PlaylistEntry(
                        playlist_id=playlist.id,
                        video_id=video_id,
                        position=entry_data.get("position", 0),
                        added_at=(
                            datetime.fromisoformat(entry_data.get("added_at"))
                            if entry_data.get("added_at")
                            else datetime.utcnow()
                        ),
                    )
                    db.add(new_entry)

            playlist.video_count = len(playlist_data.entries)

    def _xml_to_dict(self, element) -> Dict[str, Any]:
        """Convert XML element to dictionary"""
        result = {}

        # Add attributes
        if element.attrib:
            result["@attributes"] = element.attrib

        # Process children
        children = list(element)
        if children:
            child_dict = {}
            for child in children:
                child_data = self._xml_to_dict(child)
                if child.tag in child_dict:
                    # Handle multiple children with same tag
                    if not isinstance(child_dict[child.tag], list):
                        child_dict[child.tag] = [child_dict[child.tag]]
                    child_dict[child.tag].append(child_data)
                else:
                    child_dict[child.tag] = child_data
            result.update(child_dict)

        # Add text content
        if element.text and element.text.strip():
            if result:
                result["#text"] = element.text.strip()
            else:
                result = element.text.strip()

        return result

    def _parse_artists_csv(self, csv_content: str) -> List[ExportedArtist]:
        """Parse artists CSV content"""
        artists = []
        csv_reader = csv.DictReader(StringIO(csv_content))

        for row in csv_reader:
            artist = ExportedArtist(
                id=int(row.get("id", 0)),
                name=row.get("name", ""),
                imvdb_id=row.get("imvdb_id"),
                spotify_id=row.get("spotify_id"),
                lastfm_name=row.get("lastfm_name"),
                thumbnail_url=row.get("thumbnail_url"),
                auto_download=row.get("auto_download", "false").lower() == "true",
                monitored=row.get("monitored", "false").lower() == "true",
                keywords=(
                    json.loads(row.get("keywords", "[]"))
                    if row.get("keywords")
                    else None
                ),
                folder_path=row.get("folder_path"),
                genres=row.get("genres", "").split(", ") if row.get("genres") else None,
                source=row.get("source"),
                imvdb_metadata=(
                    json.loads(row.get("imvdb_metadata", "{}"))
                    if row.get("imvdb_metadata")
                    else None
                ),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                video_count=int(row.get("video_count", 0)),
                downloaded_count=int(row.get("downloaded_count", 0)),
            )
            artists.append(artist)

        return artists

    def _parse_videos_csv(self, csv_content: str) -> List[ExportedVideo]:
        """Parse videos CSV content"""
        videos = []
        csv_reader = csv.DictReader(StringIO(csv_content))

        for row in csv_reader:
            video = ExportedVideo(
                id=int(row.get("id", 0)),
                artist_id=int(row.get("artist_id", 0)),
                title=row.get("title", ""),
                imvdb_id=row.get("imvdb_id"),
                youtube_id=row.get("youtube_id"),
                youtube_url=row.get("youtube_url"),
                url=row.get("url"),
                playlist_id=row.get("playlist_id"),
                thumbnail_url=row.get("thumbnail_url"),
                duration=int(row.get("duration", 0)) if row.get("duration") else None,
                year=int(row.get("year", 0)) if row.get("year") else None,
                release_date=row.get("release_date"),
                description=row.get("description"),
                view_count=(
                    int(row.get("view_count", 0)) if row.get("view_count") else None
                ),
                like_count=(
                    int(row.get("like_count", 0)) if row.get("like_count") else None
                ),
                genres=row.get("genres", "").split(", ") if row.get("genres") else None,
                directors=(
                    row.get("directors", "").split(", ")
                    if row.get("directors")
                    else None
                ),
                producers=(
                    row.get("producers", "").split(", ")
                    if row.get("producers")
                    else None
                ),
                status=row.get("status", "WANTED"),
                quality=row.get("quality"),
                video_metadata=(
                    json.loads(row.get("video_metadata", "{}"))
                    if row.get("video_metadata")
                    else None
                ),
                imvdb_metadata=(
                    json.loads(row.get("imvdb_metadata", "{}"))
                    if row.get("imvdb_metadata")
                    else None
                ),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                width=int(row.get("width", 0)) if row.get("width") else None,
                height=int(row.get("height", 0)) if row.get("height") else None,
                video_codec=row.get("video_codec"),
                audio_codec=row.get("audio_codec"),
                fps=float(row.get("fps", 0)) if row.get("fps") else None,
                bitrate=int(row.get("bitrate", 0)) if row.get("bitrate") else None,
                ffmpeg_extracted=row.get("ffmpeg_extracted", "false").lower() == "true",
                local_path=row.get("local_path"),
                file_size=(
                    int(row.get("file_size", 0)) if row.get("file_size") else None
                ),
            )
            videos.append(video)

        return videos

    def _parse_playlists_csv(self, csv_content: str) -> List[ExportedPlaylist]:
        """Parse playlists CSV content"""
        playlists = []
        csv_reader = csv.DictReader(StringIO(csv_content))

        for row in csv_reader:
            playlist = ExportedPlaylist(
                id=int(row.get("id", 0)),
                name=row.get("name", ""),
                description=row.get("description"),
                user_id=int(row.get("user_id", 0)),
                is_public=row.get("is_public", "false").lower() == "true",
                is_featured=row.get("is_featured", "false").lower() == "true",
                total_duration=(
                    int(row.get("total_duration", 0))
                    if row.get("total_duration")
                    else None
                ),
                video_count=int(row.get("video_count", 0)),
                playlist_metadata=(
                    json.loads(row.get("playlist_metadata", "{}"))
                    if row.get("playlist_metadata")
                    else None
                ),
                thumbnail_url=row.get("thumbnail_url"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                entries=(
                    json.loads(row.get("entries", "[]")) if row.get("entries") else []
                ),
            )
            playlists.append(playlist)

        return playlists

    def _parse_settings_csv(self, csv_content: str) -> List[ExportedSetting]:
        """Parse settings CSV content"""
        settings = []
        csv_reader = csv.DictReader(StringIO(csv_content))

        for row in csv_reader:
            setting = ExportedSetting(
                key=row.get("key", ""),
                value=row.get("value"),
                description=row.get("description"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            settings.append(setting)

        return settings

    def _parse_blacklist_csv(self, csv_content: str) -> List[Dict[str, Any]]:
        """Parse blacklist CSV content"""
        blacklist = []
        csv_reader = csv.DictReader(StringIO(csv_content))

        for row in csv_reader:
            entry = {
                "youtube_url": row.get("youtube_url", ""),
                "reason": row.get("reason"),
                "created_at": row.get("created_at"),
            }
            blacklist.append(entry)

        return blacklist

    def _create_backup(self, operation_id: int) -> str:
        """Create a backup before importing"""
        try:
            from src.database.import_export_models import (
                ExportFormat,
                ExportOptions,
                ExportType,
            )
            from src.services.export_service import export_service

            # Create backup export options
            backup_options = ExportOptions(
                format=ExportFormat.JSON,
                export_type=ExportType.FULL_LIBRARY,
                compression_enabled=True,
                include_file_paths=True,
                include_thumbnails=True,
                include_metadata=True,
                include_user_data=False,
            )

            # Generate backup filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_before_import_{operation_id}_{timestamp}"

            # Create backup using export service
            backup_operation_id = export_service.start_export(
                user_id=1,  # System user for backups
                operation_name=backup_name,
                export_options=backup_options,
            )

            # Wait for backup to complete (simplified - in production would be async)
            backup_filename = f"{backup_name}.json.gz"
            logger.info(
                f"Created backup {backup_filename} for import operation {operation_id}"
            )

            return backup_filename

        except Exception as e:
            logger.error(
                f"Error creating backup for import operation {operation_id}: {e}"
            )
            # Return a placeholder filename - backup creation failed but import can continue
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            return f"backup_failed_{operation_id}_{timestamp}.json"


# Initialize service instance
import_service = ImportService()
