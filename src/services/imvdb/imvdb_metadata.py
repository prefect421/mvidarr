"""
IMVDb metadata processing - Metadata extraction and normalization
"""

from typing import Dict, Optional


def extract_artist_name(artist_data: Dict) -> Optional[str]:
    """
    Extract artist name from IMVDb data structure, handling nested formats

    Args:
        artist_data: Raw artist data from IMVDb API

    Returns:
        Artist name string or None
    """
    if not artist_data:
        return None

    # Try multiple possible locations for the artist name
    name_candidates = [
        artist_data.get("name"),  # Direct name field
        (
            artist_data.get("artist", {}).get("name")
            if isinstance(artist_data.get("artist"), dict)
            else None
        ),  # Nested in artist object
        (
            artist_data.get("entity", {}).get("name")
            if isinstance(artist_data.get("entity"), dict)
            else None
        ),  # Nested in entity object
        (
            artist_data.get("data", {}).get("name")
            if isinstance(artist_data.get("data"), dict)
            else None
        ),  # Nested in data object
    ]

    # Find the first non-empty name
    for candidate in name_candidates:
        if candidate:
            name = str(candidate).strip()
            if name:
                return name

    # Fallback to slug if name is not available
    slug_candidates = [
        artist_data.get("slug"),
        (
            artist_data.get("artist", {}).get("slug")
            if isinstance(artist_data.get("artist"), dict)
            else None
        ),
        (
            artist_data.get("entity", {}).get("slug")
            if isinstance(artist_data.get("entity"), dict)
            else None
        ),
    ]

    for slug in slug_candidates:
        if slug:
            return str(slug).replace("-", " ").title()

    return None


def extract_metadata(video_data: Dict) -> Dict:
    """
    Extract and standardize metadata from IMVDb video data

    Args:
        video_data: Raw IMVDb video data

    Returns:
        Standardized metadata dictionary
    """
    metadata = {
        "imvdb_id": video_data.get("id"),
        "title": str(video_data.get("song_title", "")),
        "artist_name": "",
        "artist_imvdb_id": None,
        "year": video_data.get("year"),
        "directors": video_data.get("directors", []),
        "producers": video_data.get("producers", []),
        "thumbnail_url": None,
        "youtube_url": None,
        "youtube_id": None,
        "duration": None,
        "genre": str(video_data.get("genre", "")),
        "label": video_data.get("label"),
        "album": video_data.get("album"),
        "imvdb_url": (
            f"https://imvdb.com/video/{video_data.get('id')}"
            if video_data.get("id")
            else None
        ),
        "raw_metadata": video_data,
    }

    # Extract thumbnail URL from image object or direct image_url
    if "image" in video_data and isinstance(video_data["image"], dict):
        image_data = video_data["image"]
        # Prefer larger images: o (original) > l (large) > b (big) > s (small) > t (thumbnail)
        for size in ["o", "l", "b", "s", "t"]:
            if size in image_data and image_data[size]:
                metadata["thumbnail_url"] = image_data[size]
                break
    elif "image_url" in video_data:
        metadata["thumbnail_url"] = video_data.get("image_url")

    # Extract artist information - handle both single artist and artists array
    if "artist" in video_data and isinstance(video_data["artist"], dict):
        artist_data = video_data["artist"]
        metadata["artist_name"] = artist_data.get("name", "")
        metadata["artist_imvdb_id"] = artist_data.get("id")
    elif (
        "artists" in video_data
        and isinstance(video_data["artists"], list)
        and len(video_data["artists"]) > 0
    ):
        # Use the first artist from the artists array
        artist_data = video_data["artists"][0]
        if isinstance(artist_data, dict):
            metadata["artist_name"] = artist_data.get("name", "")
            metadata["artist_imvdb_id"] = artist_data.get("id")

    # Clean up directors and producers lists
    if isinstance(metadata["directors"], list):
        metadata["directors"] = [
            d.get("name", d) if isinstance(d, dict) else str(d)
            for d in metadata["directors"]
        ]

    if isinstance(metadata["producers"], list):
        metadata["producers"] = [
            p.get("name", p) if isinstance(p, dict) else str(p)
            for p in metadata["producers"]
        ]

    # Extract YouTube URL from sources array (if available)
    if "sources" in video_data and isinstance(video_data["sources"], list):
        for source in video_data["sources"]:
            if isinstance(source, dict):
                source_type = source.get("source", "").lower()
                source_is_primary = source.get("is_primary", False)
                source_data = source.get("source_data", "")

                # Look for YouTube sources
                if source_type == "youtube" and source_data:
                    # IMVDb provides the YouTube ID directly in source_data
                    metadata["youtube_id"] = str(source_data)
                    metadata[
                        "youtube_url"
                    ] = f"https://www.youtube.com/watch?v={source_data}"

                    # If this is the primary source, use it and stop looking
                    if source_is_primary:
                        break

    return metadata
