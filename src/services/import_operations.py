"""
Import Operations Module for MVidarr 0.9.7 - Issue #76
Contains CRUD methods and import operations extracted from import_service.py
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from src.database.import_export_models import (
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
    ImportMode,
    ImportOptions,
    ProcessingProgress,
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

logger = get_logger("mvidarr.services.import_operations")


def perform_import(
    operation_id: int,
    import_data: Any,
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
    db: Session,
) -> Dict[str, Any]:
    """
    Perform the actual import operation

    Args:
        operation_id: ID of the import operation
        import_data: ExportData object containing data to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates
        db: Database session

    Returns:
        Dictionary containing import results and statistics
    """
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
        # Import in order of dependencies: Settings -> Artists -> Videos -> Playlists -> Blacklist

        # Import settings first
        if import_data.settings:
            settings_results = import_settings(
                db,
                import_data.settings,
                import_options,
                progress,
                update_progress,
            )
            import_results.update(settings_results)

        # Import artists
        if import_data.artists:
            artist_results = import_artists(
                db,
                import_data.artists,
                import_options,
                progress,
                update_progress,
            )
            import_results.update(artist_results)

        # Import videos
        if import_data.videos:
            video_results = import_videos(
                db,
                import_data.videos,
                import_options,
                progress,
                update_progress,
            )
            import_results.update(video_results)

        # Import playlists
        if import_data.playlists:
            playlist_results = import_playlists(
                db,
                import_data.playlists,
                import_options,
                progress,
                update_progress,
            )
            import_results.update(playlist_results)

        # Import blacklist
        if import_data.blacklist:
            blacklist_results = import_blacklist(
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


def import_artists(
    db: Session,
    artists: List[ExportedArtist],
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Dict[str, int]:
    """
    Import artists into the database

    Args:
        db: Database session
        artists: List of ExportedArtist objects to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates

    Returns:
        Dictionary containing import statistics
    """
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
                    update_artist_from_data(
                        existing_artist, artist_data, import_options
                    )
                    results["artists_updated"] += 1
            else:
                # Create new artist
                new_artist = create_artist_from_data(artist_data, import_options)
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


def import_videos(
    db: Session,
    videos: List[ExportedVideo],
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Dict[str, int]:
    """
    Import videos into the database

    Args:
        db: Database session
        videos: List of ExportedVideo objects to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates

    Returns:
        Dictionary containing import statistics
    """
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
                    update_video_from_data(existing_video, video_data, import_options)
                    results["videos_updated"] += 1
            else:
                # Verify artist exists
                artist = (
                    db.query(Artist).filter(Artist.id == video_data.artist_id).first()
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
                has_url = bool(
                    video_data.url or video_data.youtube_url or video_data.youtube_id
                )

                if not has_url:
                    # Try to find URL via IMVDB before rejecting the video
                    try:
                        from src.services.imvdb_service import IMVDbService

                        imvdb_service = IMVDbService()

                        # Get artist name for IMVDB search
                        artist_name = (
                            artist.name
                            if artist
                            else f"Unknown Artist {video_data.artist_id}"
                        )
                        logger.info(
                            f"Video import: No URL found for '{artist_name} - {video_data.title}', checking IMVDB"
                        )

                        search_results = imvdb_service.search_videos(
                            artist_name, video_data.title
                        )

                        if search_results and len(search_results) > 0:
                            # Get the first result
                            imvdb_video = search_results[0]

                            # Extract YouTube URL if available
                            youtube_url = None
                            if "sources" in imvdb_video:
                                for source in imvdb_video["sources"]:
                                    if source.get("source") == "youtube" and source.get(
                                        "source_data"
                                    ):
                                        youtube_url = source["source_data"]
                                        break

                            if youtube_url:
                                logger.info(
                                    f"✅ Found YouTube URL from IMVDB during import: {youtube_url}"
                                )

                                # Update video_data with found URL
                                video_data.url = youtube_url
                                video_data.youtube_url = youtube_url

                                # Extract YouTube ID from URL
                                if "watch?v=" in youtube_url:
                                    video_data.youtube_id = youtube_url.split(
                                        "watch?v="
                                    )[1].split("&")[0]
                                elif "youtu.be/" in youtube_url:
                                    video_data.youtube_id = youtube_url.split(
                                        "youtu.be/"
                                    )[1].split("?")[0]

                                # Also update IMVDB metadata if available
                                if "id" in imvdb_video:
                                    video_data.imvdb_id = str(imvdb_video["id"])
                                if imvdb_video:
                                    video_data.imvdb_metadata = imvdb_video

                                has_url = True
                                logger.info(
                                    f"✅ Updated video import data with IMVDB URL"
                                )

                    except Exception as imvdb_error:
                        logger.warning(
                            f"IMVDB search failed during import for '{video_data.title}': {imvdb_error}"
                        )

                if not has_url:
                    logger.warning(
                        f"Skipping video import '{video_data.title}': No URL found (not in IMVDB or provided data)"
                    )
                    results["videos_skipped"] += 1
                    continue

                # Create new video (now guaranteed to have URL)
                new_video = create_video_from_data(video_data, import_options)
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


def import_playlists(
    db: Session,
    playlists: List[ExportedPlaylist],
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Dict[str, int]:
    """
    Import playlists into the database

    Args:
        db: Database session
        playlists: List of ExportedPlaylist objects to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates

    Returns:
        Dictionary containing import statistics
    """
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
                    db.query(Playlist).filter(Playlist.id == playlist_data.id).first()
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
                    update_playlist_from_data(
                        existing_playlist, playlist_data, import_options, db
                    )
                    results["playlists_updated"] += 1
            else:
                # Create new playlist
                new_playlist = create_playlist_from_data(
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


def import_settings(
    db: Session,
    settings: List[ExportedSetting],
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Dict[str, int]:
    """
    Import settings into the database

    Args:
        db: Database session
        settings: List of ExportedSetting objects to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates

    Returns:
        Dictionary containing import statistics
    """
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


def import_blacklist(
    db: Session,
    blacklist: List[Dict[str, Any]],
    import_options: ImportOptions,
    progress: ProcessingProgress,
    update_progress: callable,
) -> Dict[str, int]:
    """
    Import blacklist entries into the database

    Args:
        db: Database session
        blacklist: List of blacklist entry dictionaries to import
        import_options: Import configuration options
        progress: Progress tracking object
        update_progress: Callback function for progress updates

    Returns:
        Dictionary containing import statistics
    """
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


def create_artist_from_data(
    artist_data: ExportedArtist, import_options: ImportOptions
) -> Artist:
    """
    Create a new Artist object from ExportedArtist data

    Args:
        artist_data: ExportedArtist object containing artist data
        import_options: Import configuration options

    Returns:
        New Artist object
    """
    artist = Artist(
        name=artist_data.name,
        imvdb_id=artist_data.imvdb_id,
        spotify_id=artist_data.spotify_id,
        lastfm_name=artist_data.lastfm_name,
        thumbnail_url=(
            artist_data.thumbnail_url if import_options.sanitize_file_paths else None
        ),
        auto_download=artist_data.auto_download,
        monitored=artist_data.monitored,
        folder_path=(
            sanitize_path(artist_data.folder_path)
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


def create_video_from_data(
    video_data: ExportedVideo, import_options: ImportOptions
) -> Video:
    """
    Create a new Video object from ExportedVideo data

    Args:
        video_data: ExportedVideo object containing video data
        import_options: Import configuration options

    Returns:
        New Video object
    """
    # Valid video statuses
    valid_video_statuses = {status.value for status in VideoStatus}

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
            if video_data.status in valid_video_statuses
            else VideoStatus.WANTED
        ),
        quality=video_data.quality,
        video_metadata=video_metadata,
        imvdb_metadata=video_data.imvdb_metadata,
        local_path=(
            sanitize_path(video_data.local_path)
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


def create_playlist_from_data(
    playlist_data: ExportedPlaylist,
    import_options: ImportOptions,
    db: Session,
) -> Optional[Playlist]:
    """
    Create a new Playlist object from ExportedPlaylist data

    Args:
        playlist_data: ExportedPlaylist object containing playlist data
        import_options: Import configuration options
        db: Database session

    Returns:
        New Playlist object or None if user not found
    """
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


def update_artist_from_data(
    artist: Artist, artist_data: ExportedArtist, import_options: ImportOptions
):
    """
    Update existing Artist object with ExportedArtist data

    Args:
        artist: Existing Artist object to update
        artist_data: ExportedArtist object containing new data
        import_options: Import configuration options
    """
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
            sanitize_path(artist_data.folder_path)
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


def update_video_from_data(
    video: Video, video_data: ExportedVideo, import_options: ImportOptions
):
    """
    Update existing Video object with ExportedVideo data

    Args:
        video: Existing Video object to update
        video_data: ExportedVideo object containing new data
        import_options: Import configuration options
    """
    # Valid video statuses
    valid_video_statuses = {status.value for status in VideoStatus}

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

    if video_data.status in valid_video_statuses:
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
            sanitize_path(video_data.local_path)
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


def update_playlist_from_data(
    playlist: Playlist,
    playlist_data: ExportedPlaylist,
    import_options: ImportOptions,
    db: Session,
):
    """
    Update existing Playlist object with ExportedPlaylist data

    Args:
        playlist: Existing Playlist object to update
        playlist_data: ExportedPlaylist object containing new data
        import_options: Import configuration options
        db: Database session
    """
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


def sanitize_path(path: str) -> str:
    """
    Sanitize file paths for cross-platform compatibility

    Args:
        path: File path to sanitize

    Returns:
        Sanitized file path
    """
    if not path:
        return path

    # Convert to Path object for platform-independent handling
    sanitized = Path(path)

    # Convert to string with forward slashes for consistency
    return str(sanitized).replace("\\", "/")


def create_backup(operation_id: int) -> str:
    """
    Create a backup before importing

    Args:
        operation_id: ID of the import operation

    Returns:
        Backup filename
    """
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
        logger.error(f"Error creating backup for import operation {operation_id}: {e}")
        # Return a placeholder filename - backup creation failed but import can continue
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"backup_failed_{operation_id}_{timestamp}.json"
