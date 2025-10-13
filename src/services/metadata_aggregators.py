"""
Metadata Aggregation Functions for MVidarr
Standalone aggregation utilities for combining metadata from multiple sources.

This module contains functions extracted from MetadataEnrichmentService to handle
the aggregation of artist metadata from multiple sources with intelligent conflict
resolution and weighted voting systems.
"""

import re
from typing import Dict, Optional

from src.utils.logger import get_logger

# Import the ArtistMetadata dataclass from the main service
# This maintains compatibility with existing code
try:
    from src.services.metadata_enrichment_service import ArtistMetadata
except ImportError:
    # Fallback for testing or if the module structure changes
    from dataclasses import dataclass, field
    from datetime import datetime
    from typing import Dict, List

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


logger = get_logger("mvidarr.services.metadata_aggregators")


def aggregate_metadata(
    metadata_sources: Dict[str, ArtistMetadata],
    source_weights: Dict[str, float],
    genre_aggregation_threshold: float = 0.3,
    similar_artists_limit: int = 10,
) -> ArtistMetadata:
    """
    Intelligently aggregate metadata from multiple sources

    Args:
        metadata_sources: Dictionary mapping source names to ArtistMetadata objects
        source_weights: Dictionary mapping source names to weight values (0.0-1.0)
        genre_aggregation_threshold: Minimum vote weight required for genre inclusion
        similar_artists_limit: Maximum number of similar/related artists to include

    Returns:
        ArtistMetadata: Aggregated metadata from all sources

    Raises:
        ValueError: If no metadata sources provided
    """
    if not metadata_sources:
        raise ValueError("No metadata sources provided")

    # Start with the highest confidence source as base
    base_source = max(
        metadata_sources.values(),
        key=lambda m: m.confidence * source_weights.get(m.source, 0.5),
    )

    # Create unified metadata starting with base
    unified = ArtistMetadata(
        name=base_source.name,
        source="aggregated",
        confidence=0.0,
        spotify_id=base_source.spotify_id,
        lastfm_name=base_source.lastfm_name,
        imvdb_id=base_source.imvdb_id,
        biography=base_source.biography,
        raw_data={"sources": {}},
    )

    # Aggregate genres with voting system
    genre_votes = {}
    for source_name, metadata in metadata_sources.items():
        weight = source_weights.get(source_name, 0.5) * metadata.confidence
        unified.raw_data["sources"][source_name] = metadata.raw_data

        for genre in metadata.genres:
            genre_lower = genre.lower()
            if genre_lower not in genre_votes:
                genre_votes[genre_lower] = {"votes": 0, "original": genre}
            genre_votes[genre_lower]["votes"] += weight

    # Select genres above threshold
    unified.genres = [
        data["original"]
        for data in genre_votes.values()
        if data["votes"] >= genre_aggregation_threshold
    ]

    # Aggregate other fields using weighted selection
    aggregate_numeric_fields(unified, metadata_sources)
    aggregate_list_fields(unified, metadata_sources, similar_artists_limit)
    aggregate_text_fields(unified, metadata_sources)
    extract_service_ids(unified, metadata_sources)

    # Calculate overall confidence
    unified.confidence = calculate_overall_confidence(metadata_sources, source_weights)

    return unified


def aggregate_numeric_fields(
    unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
) -> None:
    """
    Aggregate numeric fields using weighted averages

    Modifies the unified metadata in-place with aggregated numeric values.
    Prefers Spotify for popularity and followers, Last.fm for playcount/listeners.

    Args:
        unified: The unified ArtistMetadata object to update
        sources: Dictionary of source metadata to aggregate from
    """
    # Popularity (prefer Spotify)
    if any(m.popularity for m in sources.values()):
        spotify_pop = sources.get("spotify", ArtistMetadata("", "")).popularity
        unified.popularity = (
            spotify_pop
            if spotify_pop
            else max(
                (m.popularity for m in sources.values() if m.popularity),
                default=None,
            )
        )

    # Followers (prefer Spotify)
    spotify_followers = sources.get("spotify", ArtistMetadata("", "")).followers
    unified.followers = (
        spotify_followers
        if spotify_followers
        else max((m.followers for m in sources.values() if m.followers), default=None)
    )

    # Playcount and listeners (prefer Last.fm)
    lastfm_data = sources.get("lastfm", ArtistMetadata("", ""))
    unified.playcount = lastfm_data.playcount
    unified.listeners = lastfm_data.listeners
    unified.user_playcount = lastfm_data.user_playcount


def aggregate_list_fields(
    unified: ArtistMetadata,
    sources: Dict[str, ArtistMetadata],
    similar_artists_limit: int = 10,
) -> None:
    """
    Aggregate list fields by merging and deduplicating

    Modifies the unified metadata in-place with aggregated list values.
    Prioritizes sources for different list types:
    - Related/similar artists: Spotify > Last.fm > MusicBrainz > aggregate
    - Top tracks: Spotify > Last.fm
    - Images: Wikipedia > Spotify > Last.fm

    Args:
        unified: The unified ArtistMetadata object to update
        sources: Dictionary of source metadata to aggregate from
        similar_artists_limit: Maximum number of similar/related artists to include
    """
    # Related/similar artists (prefer Spotify, then Last.fm, then MusicBrainz, then others)
    # Priority: Spotify related_artists > Last.fm similar_artists > MusicBrainz > aggregate
    spotify_related = sources.get("spotify", ArtistMetadata("", "")).related_artists
    lastfm_similar = sources.get("lastfm", ArtistMetadata("", "")).similar_artists
    musicbrainz_related = sources.get(
        "musicbrainz", ArtistMetadata("", "")
    ).related_artists

    if spotify_related:
        unified.related_artists = spotify_related[:similar_artists_limit]
        logger.debug(
            f"🎵 AGGREGATION: Using Spotify related artists: {unified.related_artists}"
        )
    elif lastfm_similar:
        unified.related_artists = lastfm_similar[:similar_artists_limit]
        logger.debug(
            f"🎵 AGGREGATION: Using Last.fm similar artists as fallback: {unified.related_artists}"
        )
    elif musicbrainz_related:
        unified.related_artists = musicbrainz_related[:similar_artists_limit]
        logger.debug(
            f"🎵 AGGREGATION: Using MusicBrainz related artists as fallback: {unified.related_artists}"
        )
    else:
        # Final fallback: aggregate from all sources
        all_related = set()
        for metadata in sources.values():
            all_related.update(metadata.related_artists)
            all_related.update(metadata.similar_artists)
        unified.related_artists = list(all_related)[:similar_artists_limit]
        logger.debug(
            f"🎵 AGGREGATION: Using aggregated related/similar artists: {unified.related_artists}"
        )

    # Top tracks (prefer Spotify, then Last.fm for track recommendations)
    if sources.get("spotify", ArtistMetadata("", "")).top_tracks:
        unified.top_tracks = sources["spotify"].top_tracks
    elif sources.get("lastfm", ArtistMetadata("", "")).top_tracks:
        unified.top_tracks = sources["lastfm"].top_tracks

    # Images (prefer Wikipedia > Spotify > LastFM for quality)
    if sources.get("wikipedia", ArtistMetadata("", "")).images:
        unified.images = sources["wikipedia"].images
    elif sources.get("spotify", ArtistMetadata("", "")).images:
        unified.images = sources["spotify"].images
    elif sources.get("lastfm", ArtistMetadata("", "")).images:
        unified.images = sources["lastfm"].images


def aggregate_text_fields(
    unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
) -> None:
    """
    Aggregate text fields with source preference

    Modifies the unified metadata in-place with aggregated text values.
    Prefers Last.fm for biography text. Collects external IDs from all sources.

    Args:
        unified: The unified ArtistMetadata object to update
        sources: Dictionary of source metadata to aggregate from
    """
    # Biography (prefer Last.fm)
    if sources.get("lastfm", ArtistMetadata("", "")).biography:
        unified.biography = sources["lastfm"].biography

    # External IDs from each source
    for metadata in sources.values():
        if metadata.spotify_id and not unified.spotify_id:
            unified.spotify_id = metadata.spotify_id
        if metadata.lastfm_name and not unified.lastfm_name:
            unified.lastfm_name = metadata.lastfm_name
        if metadata.imvdb_id and not unified.imvdb_id:
            unified.imvdb_id = metadata.imvdb_id
        if metadata.mbid and not unified.mbid:
            unified.mbid = metadata.mbid


def extract_service_ids(
    unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
) -> None:
    """
    Extract service IDs and URLs from raw_data for frontend linking

    Modifies the unified metadata's raw_data in-place with service-specific
    identifiers and URLs that can be used for deep linking to external services.

    Args:
        unified: The unified ArtistMetadata object to update
        sources: Dictionary of source metadata to extract IDs from
    """
    # Extract AllMusic ID from AllMusic source
    if "allmusic" in sources:
        allmusic_data = sources["allmusic"]
        if allmusic_data.raw_data.get("allmusic_id"):
            unified.raw_data["allmusic_id"] = allmusic_data.raw_data["allmusic_id"]
        if allmusic_data.raw_data.get("allmusic_url"):
            unified.raw_data["allmusic_url"] = allmusic_data.raw_data["allmusic_url"]

    # Extract Wikipedia URL from Wikipedia source
    if "wikipedia" in sources:
        wikipedia_data = sources["wikipedia"]
        if wikipedia_data.raw_data.get("wikipedia_url"):
            unified.raw_data["wikipedia_url"] = wikipedia_data.raw_data["wikipedia_url"]


def calculate_overall_confidence(
    sources: Dict[str, ArtistMetadata], source_weights: Dict[str, float]
) -> float:
    """
    Calculate overall confidence score from multiple sources

    Computes a weighted average confidence score based on individual source
    confidence values and their configured weights.

    Args:
        sources: Dictionary of source metadata
        source_weights: Dictionary mapping source names to weight values (0.0-1.0)

    Returns:
        float: Overall confidence score (0.0-1.0)
    """
    if not sources:
        return 0.0

    weighted_confidence = 0.0
    total_weight = 0.0

    for source_name, metadata in sources.items():
        weight = source_weights.get(source_name, 0.5)
        weighted_confidence += metadata.confidence * weight
        total_weight += weight

    return min(weighted_confidence / total_weight if total_weight > 0 else 0.0, 1.0)


def is_placeholder_image(image_url: str) -> bool:
    """
    Check if an image URL is a placeholder/generic image that should be filtered out

    Detects common placeholder image patterns from various music services,
    including Last.fm placeholders, generic filenames, and very small images.

    Args:
        image_url: The image URL to check

    Returns:
        bool: True if the image is a placeholder and should be blocked
    """
    if not image_url:
        return True

    # Convert to lowercase for case-insensitive matching
    url_lower = image_url.lower()

    # Known placeholder image patterns and URLs
    placeholder_patterns = [
        # Last.fm placeholder images
        "2a96cbd8b46e442fc41c2b86b821562f.png",  # Specific Last.fm placeholder
        "lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f",
        # General Last.fm placeholder patterns
        "lastfm.freetls.fastly.net/i/u/300x300/4128a6eb29f94943c9d206c08e625904",
        "lastfm.freetls.fastly.net/i/u/300x300/c6f59c1e5e7240a4c0d427abd71f3dbb",
        # Common generic/placeholder image names
        "placeholder",
        "default",
        "generic",
        "no-image",
        "blank",
        "missing",
        "unavailable",
        "coming-soon",
        "avatar-default",
        "profile-default",
        # Music service specific placeholders
        "default_artist",
        "artist_placeholder",
        "music_placeholder",
        "album_default",
        "cover_default",
        # Common placeholder file patterns
        "grey.gif",
        "transparent.png",
        "1x1.png",
        "spacer.gif",
        "default.jpg",
        "default.png",
        "placeholder.jpg",
        "placeholder.png",
    ]

    # Check if URL contains any placeholder patterns
    for pattern in placeholder_patterns:
        if pattern in url_lower:
            logger.info(
                f"Blocking placeholder image: {image_url} (matched pattern: {pattern})"
            )
            return True

    # Check for very small images (likely placeholders)
    # Extract dimensions if they're in the URL
    size_match = re.search(r"/(\d+)x(\d+)/", image_url)
    if size_match:
        width, height = int(size_match.group(1)), int(size_match.group(2))
        # Block very small images (likely placeholders/spacers)
        if width < 50 or height < 50:
            logger.info(
                f"Blocking small placeholder image: {image_url} ({width}x{height})"
            )
            return True

    # Check for single-pixel or tiny images in filename
    tiny_patterns = ["1x1", "2x2", "10x10", "16x16", "32x32"]
    for pattern in tiny_patterns:
        if pattern in url_lower:
            logger.info(f"Blocking tiny image: {image_url} (matched: {pattern})")
            return True

    return False
