"""
Import Validators for MVidarr 0.9.7 - Issue #76
Validation functions for import service with comprehensive data integrity checks.

This module contains all validation logic extracted from ImportService to improve
code organization and maintainability. Validators check artists, videos, playlists,
settings, blacklist entries, and cross-references.
"""

import re
from typing import Any, Dict, List, Tuple

from src.database.import_export_models import (
    ExportData,
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
    ValidationError,
    ValidationLevel,
    ValidationResult,
)
from src.database.models import VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.import_validators")


def validate_import_data(
    import_data: ExportData,
    validation_level: ValidationLevel,
    youtube_url_pattern: re.Pattern,
    imvdb_id_pattern: re.Pattern,
    max_title_length: int,
    max_description_length: int,
    max_name_length: int,
    valid_video_statuses: set,
) -> ValidationResult:
    """
    Validate import data and return validation result

    Args:
        import_data: Parsed import data to validate
        validation_level: Level of validation strictness
        youtube_url_pattern: Compiled regex for YouTube URL validation
        imvdb_id_pattern: Compiled regex for IMVDB ID validation
        max_title_length: Maximum allowed title length
        max_description_length: Maximum allowed description length
        max_name_length: Maximum allowed name length
        valid_video_statuses: Set of valid video status values

    Returns:
        ValidationResult with detailed validation information
    """
    errors = []
    warnings = []
    total_records = 0
    valid_records = 0

    try:
        # Validate artists
        for i, artist in enumerate(import_data.artists):
            total_records += 1
            artist_errors, artist_warnings = validate_artist(
                artist,
                f"artist_{i}",
                imvdb_id_pattern,
                max_name_length,
            )
            errors.extend(artist_errors)
            warnings.extend(artist_warnings)
            if not artist_errors:
                valid_records += 1

        # Validate videos
        for i, video in enumerate(import_data.videos):
            total_records += 1
            video_errors, video_warnings = validate_video(
                video,
                f"video_{i}",
                youtube_url_pattern,
                max_title_length,
                max_description_length,
                valid_video_statuses,
            )
            errors.extend(video_errors)
            warnings.extend(video_warnings)
            if not video_errors:
                valid_records += 1

        # Validate playlists
        for i, playlist in enumerate(import_data.playlists):
            total_records += 1
            playlist_errors, playlist_warnings = validate_playlist(
                playlist, f"playlist_{i}", max_name_length
            )
            errors.extend(playlist_errors)
            warnings.extend(playlist_warnings)
            if not playlist_errors:
                valid_records += 1

        # Validate settings
        for i, setting in enumerate(import_data.settings):
            total_records += 1
            setting_errors, setting_warnings = validate_setting(setting, f"setting_{i}")
            errors.extend(setting_errors)
            warnings.extend(setting_warnings)
            if not setting_errors:
                valid_records += 1

        # Validate blacklist entries
        for i, blacklist_entry in enumerate(import_data.blacklist):
            total_records += 1
            blacklist_errors, blacklist_warnings = validate_blacklist_entry(
                blacklist_entry, f"blacklist_{i}", youtube_url_pattern
            )
            errors.extend(blacklist_errors)
            warnings.extend(blacklist_warnings)
            if not blacklist_errors:
                valid_records += 1

        # Cross-reference validation
        cross_ref_errors, cross_ref_warnings = validate_cross_references(import_data)
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


def validate_artist(
    artist: ExportedArtist,
    record_id: str,
    imvdb_id_pattern: re.Pattern,
    max_name_length: int,
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a single artist record

    Args:
        artist: Artist data to validate
        record_id: Identifier for this record in validation results
        imvdb_id_pattern: Compiled regex for IMVDB ID validation
        max_name_length: Maximum allowed name length

    Returns:
        Tuple of (errors, warnings) lists
    """
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
    if artist.name and len(artist.name) > max_name_length:
        errors.append(
            ValidationError(
                record_type="artist",
                record_id=record_id,
                field_name="name",
                error_code="LENGTH_EXCEEDED",
                error_message=f"Artist name exceeds {max_name_length} characters",
                suggested_fix=f"Truncate name to {max_name_length} characters",
            )
        )

    # External ID validation
    if artist.imvdb_id and not imvdb_id_pattern.match(artist.imvdb_id):
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
    if artist.thumbnail_url and not is_valid_url(artist.thumbnail_url):
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


def validate_video(
    video: ExportedVideo,
    record_id: str,
    youtube_url_pattern: re.Pattern,
    max_title_length: int,
    max_description_length: int,
    valid_video_statuses: set,
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a single video record

    Args:
        video: Video data to validate
        record_id: Identifier for this record in validation results
        youtube_url_pattern: Compiled regex for YouTube URL validation
        max_title_length: Maximum allowed title length
        max_description_length: Maximum allowed description length
        valid_video_statuses: Set of valid video status values

    Returns:
        Tuple of (errors, warnings) lists
    """
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
    if video.title and len(video.title) > max_title_length:
        errors.append(
            ValidationError(
                record_type="video",
                record_id=record_id,
                field_name="title",
                error_code="LENGTH_EXCEEDED",
                error_message=f"Video title exceeds {max_title_length} characters",
                suggested_fix=f"Truncate title to {max_title_length} characters",
            )
        )

    if video.description and len(video.description) > max_description_length:
        warnings.append(
            ValidationError(
                record_type="video",
                record_id=record_id,
                field_name="description",
                error_code="LENGTH_EXCEEDED",
                error_message=f"Description exceeds {max_description_length} characters",
                suggested_fix=f"Truncate description to {max_description_length} characters",
                severity="warning",
            )
        )

    # Status validation
    if video.status not in valid_video_statuses:
        errors.append(
            ValidationError(
                record_type="video",
                record_id=record_id,
                field_name="status",
                error_code="INVALID_VALUE",
                error_message=f"Invalid video status: {video.status}",
                suggested_fix=f"Use one of: {', '.join(valid_video_statuses)}",
            )
        )

    # URL validation
    if video.youtube_url and not youtube_url_pattern.match(video.youtube_url):
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


def validate_playlist(
    playlist: ExportedPlaylist, record_id: str, max_name_length: int
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a single playlist record

    Args:
        playlist: Playlist data to validate
        record_id: Identifier for this record in validation results
        max_name_length: Maximum allowed name length

    Returns:
        Tuple of (errors, warnings) lists
    """
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
    if playlist.name and len(playlist.name) > max_name_length:
        errors.append(
            ValidationError(
                record_type="playlist",
                record_id=record_id,
                field_name="name",
                error_code="LENGTH_EXCEEDED",
                error_message=f"Playlist name exceeds {max_name_length} characters",
                suggested_fix=f"Truncate name to {max_name_length} characters",
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


def validate_setting(
    setting: ExportedSetting, record_id: str
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a single setting record

    Args:
        setting: Setting data to validate
        record_id: Identifier for this record in validation results

    Returns:
        Tuple of (errors, warnings) lists
    """
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


def validate_blacklist_entry(
    entry: Dict[str, Any], record_id: str, youtube_url_pattern: re.Pattern
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate a single blacklist entry

    Args:
        entry: Blacklist entry data to validate
        record_id: Identifier for this record in validation results
        youtube_url_pattern: Compiled regex for YouTube URL validation

    Returns:
        Tuple of (errors, warnings) lists
    """
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
    if youtube_url and not youtube_url_pattern.match(youtube_url):
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


def validate_cross_references(
    import_data: ExportData,
) -> Tuple[List[ValidationError], List[ValidationError]]:
    """
    Validate cross-references between entities

    Args:
        import_data: Complete import data with all entities

    Returns:
        Tuple of (errors, warnings) lists
    """
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


def is_valid_url(url: str) -> bool:
    """
    Check if URL is valid

    Args:
        url: URL string to validate

    Returns:
        True if URL is valid, False otherwise
    """
    return url and (url.startswith("http://") or url.startswith("https://"))
