"""
Export Service - Format Generators Module
Generate export files in different formats (JSON, CSV, XML, YAML)
"""

import gzip
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import yaml
from src.database.import_export_models import ExportData, ExportFormat, ExportOptions
from src.services.export_csv_builders import (
    create_artists_csv,
    create_blacklist_csv,
    create_playlists_csv,
    create_settings_csv,
    create_videos_csv,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.export.formatters")


def generate_json_export(
    export_data: ExportData,
    base_filename: str,
    export_options: ExportOptions,
    temp_dir: Path,
) -> Path:
    """Generate JSON format export"""

    filename = f"{base_filename}.json"
    if export_options.compression_enabled:
        filename += ".gz"

    output_file = temp_dir / filename

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

    logger.info(f"Generated JSON export: {filename}")
    return output_file


def generate_csv_export(
    export_data: ExportData,
    base_filename: str,
    export_options: ExportOptions,
    temp_dir: Path,
) -> Path:
    """Generate CSV format export (separate files for each entity type in a ZIP)"""

    filename = f"{base_filename}.zip"
    output_file = temp_dir / filename

    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Export artists CSV
        if export_data.artists:
            csv_content = create_artists_csv(export_data.artists)
            zip_file.writestr("artists.csv", csv_content)

        # Export videos CSV
        if export_data.videos:
            csv_content = create_videos_csv(export_data.videos)
            zip_file.writestr("videos.csv", csv_content)

        # Export playlists CSV
        if export_data.playlists:
            csv_content = create_playlists_csv(export_data.playlists)
            zip_file.writestr("playlists.csv", csv_content)

        # Export settings CSV
        if export_data.settings:
            csv_content = create_settings_csv(export_data.settings)
            zip_file.writestr("settings.csv", csv_content)

        # Export blacklist CSV
        if export_data.blacklist:
            csv_content = create_blacklist_csv(export_data.blacklist)
            zip_file.writestr("blacklist.csv", csv_content)

        # Add manifest
        manifest_json = json.dumps(export_data.manifest.__dict__, indent=2)
        zip_file.writestr("manifest.json", manifest_json)

    logger.info(f"Generated CSV export: {filename}")
    return output_file


def generate_xml_export(
    export_data: ExportData,
    base_filename: str,
    export_options: ExportOptions,
    temp_dir: Path,
) -> Path:
    """Generate XML format export"""

    filename = f"{base_filename}.xml"
    if export_options.compression_enabled:
        filename += ".gz"

    output_file = temp_dir / filename

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

    # Add videos
    if export_data.videos:
        videos_elem = ET.SubElement(root, "videos")
        for video in export_data.videos:
            video_elem = ET.SubElement(videos_elem, "video")
            for key, value in video.__dict__.items():
                elem = ET.SubElement(video_elem, key)
                elem.text = str(value) if value is not None else ""

    # Add playlists
    if export_data.playlists:
        playlists_elem = ET.SubElement(root, "playlists")
        for playlist in export_data.playlists:
            playlist_elem = ET.SubElement(playlists_elem, "playlist")
            for key, value in playlist.__dict__.items():
                elem = ET.SubElement(playlist_elem, key)
                elem.text = str(value) if value is not None else ""

    # Add settings
    if export_data.settings:
        settings_elem = ET.SubElement(root, "settings")
        for setting in export_data.settings:
            setting_elem = ET.SubElement(settings_elem, "setting")
            for key, value in setting.__dict__.items():
                elem = ET.SubElement(setting_elem, key)
                elem.text = str(value) if value is not None else ""

    # Add blacklist
    if export_data.blacklist:
        blacklist_elem = ET.SubElement(root, "blacklist")
        for entry in export_data.blacklist:
            entry_elem = ET.SubElement(blacklist_elem, "entry")
            for key, value in entry.items():
                elem = ET.SubElement(entry_elem, key)
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

    logger.info(f"Generated XML export: {filename}")
    return output_file


def generate_yaml_export(
    export_data: ExportData,
    base_filename: str,
    export_options: ExportOptions,
    temp_dir: Path,
) -> Path:
    """Generate YAML format export"""

    filename = f"{base_filename}.yaml"
    if export_options.compression_enabled:
        filename += ".gz"

    output_file = temp_dir / filename

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

    logger.info(f"Generated YAML export: {filename}")
    return output_file


def generate_export_file(
    operation_id: int,
    export_data: ExportData,
    export_options: ExportOptions,
    temp_dir: Path,
    calculate_checksum_func: callable,
) -> Path:
    """Generate the final export file in the specified format"""
    from datetime import datetime

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_filename = f"mvidarr_export_{operation_id}_{timestamp}"

    if export_options.format == ExportFormat.JSON:
        output_file = generate_json_export(
            export_data, base_filename, export_options, temp_dir
        )
    elif export_options.format == ExportFormat.CSV:
        output_file = generate_csv_export(
            export_data, base_filename, export_options, temp_dir
        )
    elif export_options.format == ExportFormat.XML:
        output_file = generate_xml_export(
            export_data, base_filename, export_options, temp_dir
        )
    elif export_options.format == ExportFormat.YAML:
        output_file = generate_yaml_export(
            export_data, base_filename, export_options, temp_dir
        )
    else:
        raise ValueError(f"Unsupported export format: {export_options.format}")

    # Add checksum to manifest
    export_data.manifest.checksum = calculate_checksum_func(output_file)
    export_data.manifest.file_size_bytes = output_file.stat().st_size

    return output_file
