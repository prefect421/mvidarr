"""
Metadata Models for Enhanced Metadata Enrichment Service
Data classes and helper functions for metadata enrichment operations

Extracted from metadata_enrichment_service.py as part of code cleanup.
"""

import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests

from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_models")


def search_lyrics_azlyrics(artist, title):
    """Search for lyrics using Lyrics.ovh API (formerly azlyrics approach)"""
    try:
        # Clean artist and title for API request
        artist_clean = artist.strip()
        title_clean = title.strip()

        # URL encode the parameters to handle special characters
        artist_encoded = urllib.parse.quote(artist_clean)
        title_encoded = urllib.parse.quote(title_clean)

        # Use the free Lyrics.ovh API
        url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{title_encoded}"

        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            lyrics = data.get("lyrics", "")

            # Clean up the lyrics
            if lyrics:
                lyrics = lyrics.strip()
                # Remove excessive whitespace and normalize line breaks
                lyrics = "\n".join(
                    line.strip() for line in lyrics.split("\n") if line.strip()
                )

                # Check if we got substantial content (more than just a few words)
                if len(lyrics) > 50:
                    return lyrics

        return None

    except Exception as e:
        logger.warning(f"Lyrics.ovh search failed for {artist} - {title}: {e}")
        return None


@dataclass
class ArtistMetadata:
    """Unified artist metadata from multiple sources"""

    name: str
    source: str
    confidence: float = 0.0

    # Core metadata
    genres: List[str] = field(default_factory=list)
    popularity: Optional[int] = None
    followers: Optional[int] = None
    images: List[Dict] = field(default_factory=list)

    # External IDs
    spotify_id: Optional[str] = None
    lastfm_name: Optional[str] = None
    imvdb_id: Optional[str] = None
    mbid: Optional[str] = None  # MusicBrainz ID

    # Rich metadata
    biography: Optional[str] = None
    related_artists: List[str] = field(default_factory=list)
    similar_artists: List[str] = field(default_factory=list)
    top_tracks: List[str] = field(default_factory=list)

    # Statistics
    playcount: Optional[int] = None
    listeners: Optional[int] = None
    user_playcount: Optional[int] = None

    # Source-specific data
    raw_data: Dict = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class EnrichmentResult:
    """Result of metadata enrichment process"""

    success: bool
    artist_id: Optional[int] = None
    video_id: Optional[int] = None
    sources_used: List[str] = field(default_factory=list)
    metadata_found: Dict = field(default_factory=dict)
    metadata_sources: List[str] = field(default_factory=list)
    enriched_fields: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    processing_time: float = 0.0
