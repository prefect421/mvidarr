"""
Export Service - CSV Builders Module
CSV generation functions for each entity type
"""

import csv
import json
from io import StringIO
from typing import Any, Dict, List

from src.database.import_export_models import (
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.export.csv_builders")


def create_artists_csv(artists: List[ExportedArtist]) -> str:
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


def create_videos_csv(videos: List[ExportedVideo]) -> str:
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


def create_playlists_csv(playlists: List[ExportedPlaylist]) -> str:
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


def create_settings_csv(settings: List[ExportedSetting]) -> str:
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


def create_blacklist_csv(blacklist: List[Dict[str, Any]]) -> str:
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
