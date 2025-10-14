"""
Import Parsers for MVidarr - File Parsing Methods
Extracted from import_service.py for better code organization and maintainability.

This module contains all file parsing functionality for various import formats:
- JSON (compressed and uncompressed)
- YAML (compressed and uncompressed)
- XML (compressed and uncompressed)
- CSV (within ZIP archives)
"""

import csv
import gzip
import json
import xml.etree.ElementTree as ET
import zipfile
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.database.import_export_models import (
    ExportData,
    ExportedArtist,
    ExportedPlaylist,
    ExportedSetting,
    ExportedVideo,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.import_parsers")


def parse_import_file(source_file_path: Path) -> ExportData:
    """
    Parse import file and return structured data

    Args:
        source_file_path: Path to the import file

    Returns:
        ExportData object containing parsed data

    Raises:
        ValueError: If file format is unsupported
        Exception: For parsing errors
    """
    try:
        # Determine file format based on extension
        file_extension = source_file_path.suffix.lower()

        if file_extension == ".gz":
            # Handle compressed files
            inner_extension = source_file_path.stem.split(".")[-1].lower()
            if inner_extension == "json":
                return parse_compressed_json(source_file_path)
            elif inner_extension in ["yaml", "yml"]:
                return parse_compressed_yaml(source_file_path)
            elif inner_extension == "xml":
                return parse_compressed_xml(source_file_path)
            else:
                raise ValueError(
                    f"Unsupported compressed file format: {inner_extension}"
                )

        elif file_extension == ".json":
            return parse_json_file(source_file_path)
        elif file_extension in [".yaml", ".yml"]:
            return parse_yaml_file(source_file_path)
        elif file_extension == ".xml":
            return parse_xml_file(source_file_path)
        elif file_extension == ".zip":
            return parse_csv_zip(source_file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")

    except Exception as e:
        logger.error(f"Error parsing import file {source_file_path}: {e}")
        raise


def parse_json_file(file_path: Path) -> ExportData:
    """
    Parse JSON format import file

    Args:
        file_path: Path to the JSON file

    Returns:
        ExportData object containing parsed data
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ExportData.from_dict(data)


def parse_compressed_json(file_path: Path) -> ExportData:
    """
    Parse compressed JSON format import file

    Args:
        file_path: Path to the compressed JSON file (.json.gz)

    Returns:
        ExportData object containing parsed data
    """
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return ExportData.from_dict(data)


def parse_yaml_file(file_path: Path) -> ExportData:
    """
    Parse YAML format import file

    Args:
        file_path: Path to the YAML file

    Returns:
        ExportData object containing parsed data
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ExportData.from_dict(data)


def parse_compressed_yaml(file_path: Path) -> ExportData:
    """
    Parse compressed YAML format import file

    Args:
        file_path: Path to the compressed YAML file (.yaml.gz)

    Returns:
        ExportData object containing parsed data
    """
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ExportData.from_dict(data)


def parse_xml_file(file_path: Path) -> ExportData:
    """
    Parse XML format import file

    Args:
        file_path: Path to the XML file

    Returns:
        ExportData object containing parsed data
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Convert XML to dictionary structure
    data = xml_to_dict(root)
    return ExportData.from_dict(data)


def parse_compressed_xml(file_path: Path) -> ExportData:
    """
    Parse compressed XML format import file

    Args:
        file_path: Path to the compressed XML file (.xml.gz)

    Returns:
        ExportData object containing parsed data
    """
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        tree = ET.parse(f)
        root = tree.getroot()

    # Convert XML to dictionary structure
    data = xml_to_dict(root)
    return ExportData.from_dict(data)


def parse_csv_zip(file_path: Path) -> ExportData:
    """
    Parse CSV ZIP format import file

    The ZIP archive should contain the following CSV files:
    - manifest.json: Metadata about the export
    - artists.csv: Artist records
    - videos.csv: Video records
    - playlists.csv: Playlist records
    - settings.csv: Application settings
    - blacklist.csv: Blacklisted videos

    Args:
        file_path: Path to the ZIP file

    Returns:
        ExportData object containing parsed data
    """
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
                import_data.artists = parse_artists_csv(csv_content)

        # Load videos CSV
        if "videos.csv" in zip_file.namelist():
            with zip_file.open("videos.csv") as f:
                csv_content = f.read().decode("utf-8")
                import_data.videos = parse_videos_csv(csv_content)

        # Load playlists CSV
        if "playlists.csv" in zip_file.namelist():
            with zip_file.open("playlists.csv") as f:
                csv_content = f.read().decode("utf-8")
                import_data.playlists = parse_playlists_csv(csv_content)

        # Load settings CSV
        if "settings.csv" in zip_file.namelist():
            with zip_file.open("settings.csv") as f:
                csv_content = f.read().decode("utf-8")
                import_data.settings = parse_settings_csv(csv_content)

        # Load blacklist CSV
        if "blacklist.csv" in zip_file.namelist():
            with zip_file.open("blacklist.csv") as f:
                csv_content = f.read().decode("utf-8")
                import_data.blacklist = parse_blacklist_csv(csv_content)

    return import_data


def xml_to_dict(element) -> Dict[str, Any]:
    """
    Convert XML element to dictionary

    Recursively converts an XML element tree into a dictionary structure,
    preserving attributes, child elements, and text content.

    Args:
        element: XML element to convert

    Returns:
        Dictionary representation of the XML element
    """
    result = {}

    # Add attributes
    if element.attrib:
        result["@attributes"] = element.attrib

    # Process children
    children = list(element)
    if children:
        child_dict = {}
        for child in children:
            child_data = xml_to_dict(child)
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


def parse_artists_csv(csv_content: str) -> List[ExportedArtist]:
    """
    Parse artists CSV content

    Args:
        csv_content: CSV content as string

    Returns:
        List of ExportedArtist objects
    """
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
                json.loads(row.get("keywords", "[]")) if row.get("keywords") else None
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


def parse_videos_csv(csv_content: str) -> List[ExportedVideo]:
    """
    Parse videos CSV content

    Args:
        csv_content: CSV content as string

    Returns:
        List of ExportedVideo objects
    """
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
                row.get("directors", "").split(", ") if row.get("directors") else None
            ),
            producers=(
                row.get("producers", "").split(", ") if row.get("producers") else None
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
            file_size=(int(row.get("file_size", 0)) if row.get("file_size") else None),
        )
        videos.append(video)

    return videos


def parse_playlists_csv(csv_content: str) -> List[ExportedPlaylist]:
    """
    Parse playlists CSV content

    Args:
        csv_content: CSV content as string

    Returns:
        List of ExportedPlaylist objects
    """
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
                int(row.get("total_duration", 0)) if row.get("total_duration") else None
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


def parse_settings_csv(csv_content: str) -> List[ExportedSetting]:
    """
    Parse settings CSV content

    Args:
        csv_content: CSV content as string

    Returns:
        List of ExportedSetting objects
    """
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


def parse_blacklist_csv(csv_content: str) -> List[Dict[str, Any]]:
    """
    Parse blacklist CSV content

    Args:
        csv_content: CSV content as string

    Returns:
        List of dictionaries containing blacklist entry data
    """
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
