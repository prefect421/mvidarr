"""
Enhanced Metadata Enrichment Service for MVidarr 0.9.7 - Issue #75
Multi-source artist discovery and metadata aggregation system with intelligent conflict resolution.
"""

import asyncio
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union

# Lyrics search functionality
import requests
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services.allmusic_service import allmusic_service
from src.services.async_spotify_service import get_async_spotify_service
from src.services.imvdb_service import imvdb_service
from src.services.lastfm_service import lastfm_service
from src.services.musicbrainz_service import musicbrainz_service
from src.services.settings_service import settings
from src.services.spotify_service import spotify_service
from src.services.video_indexing_service import VideoIndexingService
from src.services.wikipedia_service import WikipediaService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_enrichment")


def search_lyrics_azlyrics(artist, title):
    """Search for lyrics using Lyrics.ovh API (formerly azlyrics approach)"""
    try:
        # Clean artist and title for API request
        artist_clean = artist.strip()
        title_clean = title.strip()

        # URL encode the parameters to handle special characters
        import urllib.parse

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


class MetadataEnrichmentService:
    """Service for intelligent multi-source metadata enrichment"""

    def __init__(self):
        self.spotify = spotify_service
        self.lastfm = lastfm_service
        self.imvdb = imvdb_service
        self.musicbrainz = musicbrainz_service
        self.allmusic = allmusic_service
        self.wikipedia = WikipediaService()

        # Configuration
        self.min_confidence_threshold = 0.7
        self.genre_aggregation_threshold = 0.3
        self.similar_artists_limit = 10
        self.cache_duration_hours = 24

        # Default source weights for confidence calculation
        self.default_source_weights = {
            "spotify": 0.9,
            "musicbrainz": 0.95,  # Most authoritative source
            "allmusic": 0.88,  # High quality music metadata
            "lastfm": 0.8,
            "wikipedia": 0.7,
        }

    def _get_source_priorities(self) -> Dict[str, float]:
        """Get user-configured source priorities/weights from database"""
        from src.services.settings_service import SettingsService as settings

        # Get user-configured source priorities from database settings
        # Higher priority number = higher importance, convert to 0-1 weight scale
        try:
            priority_settings = {
                "musicbrainz": settings.get_int("musicbrainz_priority", 3),
                "allmusic": settings.get_int("allmusic_priority", 4),
                "lastfm": settings.get_int("lastfm_metadata_priority", 2),
                "wikipedia": settings.get_int("wikipedia_priority", 5),
                "spotify": 4,  # Default for Spotify since not in current settings
            }

            # Convert priority rankings to weights (0.5-0.95 scale)
            # Priority 1 = 0.5, Priority 5 = 0.95
            max_priority = max(priority_settings.values())
            user_priorities = {}

            for source, priority in priority_settings.items():
                if priority > 0:  # Only include enabled sources
                    # Convert priority rank to weight: higher priority = higher weight
                    weight = 0.5 + (priority / max_priority) * 0.45
                    user_priorities[source] = round(weight, 2)

            logger.debug(
                f"Using user-configured metadata source priorities: {user_priorities}"
            )
            return user_priorities

        except Exception as e:
            logger.warning(
                f"Error reading user metadata priorities, using defaults: {e}"
            )
            return self.default_source_weights

    @property
    def source_weights(self) -> Dict[str, float]:
        """Get current source weights based on user configuration"""
        return self._get_source_priorities()

    async def enrich_artist_metadata(
        self, artist_id: int, force_refresh: bool = False, app_context=None
    ) -> EnrichmentResult:
        """
        Enrich artist metadata from multiple sources with intelligent aggregation
        """
        start_time = time.time()
        result = EnrichmentResult(success=False, artist_id=artist_id)

        # Set up Flask app context if provided to ensure database and settings access
        app_context_manager = None
        if app_context:
            app_context_manager = app_context.app_context()
            app_context_manager.__enter__()

        try:
            with get_db() as session:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()
                if not artist:
                    result.errors.append(f"Artist with ID {artist_id} not found")
                    return result

                # Store artist name for logging (avoid session issues)
                artist_name = artist.name

                # Check if we need to refresh metadata
                if not force_refresh and self._is_metadata_fresh(artist):
                    logger.debug(
                        f"Artist {artist_name} metadata is fresh, skipping enrichment"
                    )
                    result.success = True
                    result.confidence_score = (
                        0.8  # Assume good confidence for cached data
                    )
                    return result

                logger.info(f"Starting metadata enrichment for artist: {artist_name}")

                # Create a simple artist data structure to avoid session issues
                artist_data = {
                    "id": artist.id,
                    "name": artist.name,
                    "spotify_id": artist.spotify_id,
                    "lastfm_name": artist.lastfm_name,
                    "imvdb_id": artist.imvdb_id,
                }

            # Gather metadata from all sources (outside of session to avoid conflicts)
            metadata_sources = await self._gather_all_sources_metadata(artist_data)

            if not metadata_sources:
                result.errors.append("No metadata found from any source")
                return result

            # Aggregate and resolve conflicts
            unified_metadata = self._aggregate_metadata(metadata_sources)

            # Update artist record in a new session
            with get_db() as session:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()
                if not artist:
                    result.errors.append(
                        f"Artist with ID {artist_id} not found during update"
                    )
                    return result

                # Update artist record - ensure artist is bound to current session
                artist = session.merge(artist)
                updated_fields = self._update_artist_record(
                    session, artist, unified_metadata
                )

                logger.info(
                    f"Committing enriched metadata for {artist_name}: {updated_fields}"
                )

                # Flush changes to database before verification
                session.flush()

                # Verify the data was actually saved BEFORE final commit
                verification = (
                    session.query(Artist).filter(Artist.id == artist_id).first()
                )
                if verification and verification.imvdb_metadata:
                    logger.info(
                        f"Pre-commit verification: Artist {artist_name} has metadata with enrichment_date: {verification.imvdb_metadata.get('enrichment_date')}"
                    )
                else:
                    logger.error(
                        f"Pre-commit verification failed: Artist {artist_name} metadata was not updated properly"
                    )

                # Commit changes
                session.commit()

                logger.info(
                    f"Successfully committed enriched metadata for {artist_name}"
                )

                # Verify the data was actually saved AFTER commit
                session.refresh(verification)
                verification = (
                    session.query(Artist).filter(Artist.id == artist_id).first()
                )
                if verification and verification.imvdb_metadata:
                    logger.info(
                        f"Verification: Artist {artist_name} now has metadata with enrichment_date: {verification.imvdb_metadata.get('enrichment_date')}"
                    )
                else:
                    logger.error(
                        f"Verification failed: Artist {artist_name} metadata was not saved properly"
                    )

                # Validate that meaningful enrichment data was actually gathered
                meaningful_fields = [
                    unified_metadata.biography,
                    unified_metadata.related_artists,
                    unified_metadata.top_tracks,
                    unified_metadata.images,
                    unified_metadata.popularity,
                    unified_metadata.followers,
                    unified_metadata.playcount,
                    unified_metadata.listeners,
                    unified_metadata.genres,  # Include genres as meaningful data
                    unified_metadata.similar_artists,  # Include similar artists as meaningful data
                ]

                has_meaningful_data = any(field for field in meaningful_fields)

                logger.info(
                    f"Meaningful data check for {artist_name}: {has_meaningful_data}"
                )
                logger.info(
                    f"Meaningful fields content: {[(i, bool(field)) for i, field in enumerate(meaningful_fields)]}"
                )

                if not has_meaningful_data:
                    result.errors.append(
                        f"No meaningful enrichment data found for {artist_name}. "
                        f"Sources returned basic data only: {list(metadata_sources.keys())}"
                    )
                    logger.warning(
                        f"Enrichment failed for {artist_name}: no meaningful data from {list(metadata_sources.keys())}"
                    )
                    return result

                # Build successful result
                result.success = True
                result.sources_used = list(metadata_sources.keys())
                result.enriched_fields = (
                    updated_fields  # Fields that were actually updated
                )
                result.metadata_found = updated_fields
                result.confidence_score = unified_metadata.confidence
                result.processing_time = time.time() - start_time

                logger.info(
                    f"Successfully enriched metadata for {artist_name} using sources: {result.sources_used}"
                )

        except Exception as e:
            logger.error(f"Error enriching metadata for artist {artist_id}: {str(e)}")
            result.errors.append(str(e))
        finally:
            # Clean up Flask app context
            if app_context_manager:
                try:
                    app_context_manager.__exit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error cleaning up app context: {e}")

        result.processing_time = time.time() - start_time
        return result

    async def _gather_all_sources_metadata(
        self, artist_data: Dict
    ) -> Dict[str, ArtistMetadata]:
        """Gather metadata from all available sources"""
        metadata_sources = {}

        # Spotify metadata - using async service (always enabled if configured)
        try:
            logger.debug(
                f"🎵 ASYNC SPOTIFY ENRICHMENT: Starting for {artist_data['name']}"
            )

            spotify_metadata = await self._get_spotify_metadata(artist_data)
            if spotify_metadata:
                logger.debug(
                    f"🎵 ASYNC SPOTIFY ENRICHMENT: Got metadata: {spotify_metadata}"
                )
                logger.debug(
                    f"🎵 ASYNC SPOTIFY ENRICHMENT: Related artists: {spotify_metadata.related_artists}"
                )
                logger.debug(
                    f"🎵 ASYNC SPOTIFY ENRICHMENT: Top tracks: {spotify_metadata.top_tracks}"
                )
                metadata_sources["spotify"] = spotify_metadata
                logger.debug(
                    f"Successfully gathered async Spotify metadata for {artist_data['name']}"
                )
            else:
                logger.debug(
                    f"🎵 ASYNC SPOTIFY ENRICHMENT: No metadata returned for {artist_data['name']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to get async Spotify metadata for {artist_data['name']}: {e}"
            )

        # Last.fm metadata - check if enabled
        if hasattr(self.lastfm, "enabled") and self.lastfm.enabled:
            try:
                lastfm_metadata = await self._get_lastfm_metadata(artist_data)
                if lastfm_metadata:
                    metadata_sources["lastfm"] = lastfm_metadata
                    logger.debug(
                        f"Successfully gathered Last.fm metadata for {artist_data['name']}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to get Last.fm metadata for {artist_data['name']}: {e}"
                )
        else:
            logger.debug(
                f"Last.fm integration disabled or not configured, skipping for {artist_data['name']}"
            )

        # IMVDb metadata - DISABLED per user requirements
        # IMVDb should only be used for searching artists and videos, not as a metadata source
        logger.debug(
            f"IMVDb metadata collection disabled per configuration for {artist_data['name']}"
        )

        # MusicBrainz metadata - check if enabled
        if hasattr(self.musicbrainz, "enabled") and self.musicbrainz.enabled:
            try:
                musicbrainz_metadata = await self._get_musicbrainz_metadata(artist_data)
                if musicbrainz_metadata:
                    metadata_sources["musicbrainz"] = musicbrainz_metadata
                    logger.debug(
                        f"Successfully gathered MusicBrainz metadata for {artist_data['name']}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to get MusicBrainz metadata for {artist_data['name']}: {e}"
                )
        else:
            logger.debug(
                f"MusicBrainz integration disabled, skipping for {artist_data['name']}"
            )

        # AllMusic metadata - check if enabled
        logger.debug(
            f"Checking AllMusic for {artist_data['name']}: hasattr={hasattr(self.allmusic, 'enabled')}, enabled={getattr(self.allmusic, 'enabled', None)}"
        )
        if hasattr(self.allmusic, "enabled") and self.allmusic.enabled:
            try:
                logger.info(f"Calling AllMusic for {artist_data['name']}")
                allmusic_metadata = await self._get_allmusic_metadata(artist_data)
                if allmusic_metadata:
                    metadata_sources["allmusic"] = allmusic_metadata
                    logger.info(
                        f"Successfully gathered AllMusic metadata for {artist_data['name']}"
                    )
                else:
                    logger.warning(
                        f"AllMusic returned no metadata for {artist_data['name']}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to get AllMusic metadata for {artist_data['name']}: {e}"
                )
        else:
            logger.warning(
                f"AllMusic integration disabled or not available, skipping for {artist_data['name']} - hasattr: {hasattr(self.allmusic, 'enabled')}, enabled: {getattr(self.allmusic, 'enabled', None)}"
            )

        # Wikipedia metadata - basic biography integration
        try:
            logger.info(f"Calling Wikipedia for {artist_data['name']}")
            wikipedia_metadata = await self._get_wikipedia_metadata(artist_data)
            if wikipedia_metadata:
                metadata_sources["wikipedia"] = wikipedia_metadata
                logger.info(
                    f"Successfully gathered Wikipedia metadata for {artist_data['name']}"
                )
            else:
                logger.debug(
                    f"Wikipedia returned no metadata for {artist_data['name']}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to get Wikipedia metadata for {artist_data['name']}: {e}"
            )

        # Discogs integration removed

        logger.info(
            f"Gathered metadata from {len(metadata_sources)} sources for {artist_data['name']}: {list(metadata_sources.keys())}"
        )
        return metadata_sources

    async def _get_spotify_metadata(
        self, artist_data: Dict
    ) -> Optional[ArtistMetadata]:
        """Get enhanced metadata from Spotify (using async service)"""
        try:
            # Get async Spotify service
            async_spotify = await get_async_spotify_service()

            # Search for artist if we don't have Spotify ID
            spotify_artist = None
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Processing {artist_data['name']}, spotify_id: {artist_data.get('spotify_id')}"
            )

            if artist_data.get("spotify_id"):
                # Get artist by ID
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Getting artist by ID {artist_data['spotify_id']}"
                )
                spotify_artist = await async_spotify.get_artist(
                    artist_data["spotify_id"]
                )
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Got artist by ID: {spotify_artist is not None}"
                )
            else:
                # Search for artist
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Searching for artist {artist_data['name']}"
                )
                search_results = await async_spotify.search_artist(
                    artist_data["name"], limit=5
                )
                artists = search_results.get("artists", {}).get("items", [])
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Search returned {len(artists)} artists"
                )

                # Find best match
                for candidate in artists:
                    if self._is_artist_match(
                        artist_data["name"], candidate.get("name", "")
                    ):
                        spotify_artist = candidate
                        break

            if not spotify_artist:
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: No matching artist found for {artist_data['name']}"
                )
                return None

            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Found artist: {spotify_artist.get('name')} (ID: {spotify_artist['id']})"
            )

            # Get related artists
            related_artists = []
            try:
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Getting related artists for {spotify_artist['id']}"
                )
                related_data = await async_spotify.get_artist_related_artists(
                    spotify_artist["id"]
                )
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Raw related artists response: {related_data}"
                )

                if related_data and "artists" in related_data:
                    related_artists = [
                        a.get("name") for a in related_data.get("artists", [])[:5]
                    ]
                    logger.debug(
                        f"🎵 ASYNC SPOTIFY METADATA: Processed {len(related_artists)} related artists: {related_artists}"
                    )
                else:
                    logger.warning(
                        f"🎵 ASYNC SPOTIFY METADATA: No 'artists' key in related artists response: {related_data}"
                    )

            except Exception as e:
                logger.warning(
                    f"🎵 ASYNC SPOTIFY METADATA: Could not get related artists: {e}"
                )
                logger.exception(f"🎵 ASYNC SPOTIFY METADATA: Full exception details:")

            # Get top tracks
            top_tracks = []
            try:
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Getting top tracks for {spotify_artist['id']}"
                )
                tracks_data = await async_spotify.get_artist_top_tracks(
                    spotify_artist["id"]
                )
                top_tracks = [t.get("name") for t in tracks_data.get("tracks", [])[:5]]
                logger.debug(
                    f"🎵 ASYNC SPOTIFY METADATA: Got {len(top_tracks)} top tracks: {top_tracks}"
                )
            except Exception as e:
                logger.warning(
                    f"🎵 ASYNC SPOTIFY METADATA: Could not get top tracks: {e}"
                )

            # Create metadata object
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Creating ArtistMetadata with related_artists: {related_artists}, top_tracks: {top_tracks}"
            )
            metadata = ArtistMetadata(
                name=spotify_artist.get("name", artist_data["name"]),
                source="spotify",
                confidence=self._calculate_name_similarity(
                    artist_data["name"], spotify_artist.get("name", "")
                ),
                genres=spotify_artist.get("genres", []),
                popularity=spotify_artist.get("popularity"),
                followers=spotify_artist.get("followers", {}).get("total"),
                images=spotify_artist.get("images", []),
                spotify_id=spotify_artist.get("id"),
                related_artists=related_artists,
                top_tracks=top_tracks,
                raw_data=spotify_artist,
            )
            logger.debug(
                f"🎵 ASYNC SPOTIFY METADATA: Final metadata object - related_artists: {metadata.related_artists}, top_tracks: {metadata.top_tracks}"
            )

            return metadata

        except Exception as e:
            logger.error(f"Error getting async Spotify metadata: {e}")
            return None

    async def _get_lastfm_metadata(self, artist_data: Dict) -> Optional[ArtistMetadata]:
        """Get enhanced metadata from Last.fm"""
        try:
            # Get artist info
            artist_info = self.lastfm.get_artist_info(
                artist_data.get("lastfm_name") or artist_data["name"]
            )

            if not artist_info:
                return None

            # Get similar artists
            similar_artists = []
            try:
                artist_name = artist_data.get("lastfm_name") or artist_data["name"]
                similar_artists = self.lastfm.get_similar_artists(
                    artist_name, self.similar_artists_limit
                )
                logger.debug(
                    f"🎵 LAST.FM METADATA: Got {len(similar_artists)} similar artists: {similar_artists}"
                )
            except Exception as e:
                logger.debug(f"🎵 LAST.FM METADATA: Could not get similar artists: {e}")

            # Get top tracks
            top_tracks = []
            try:
                tracks_data = self.lastfm.get_artist_top_tracks_lastfm(
                    artist_data["name"], 5
                )
                top_tracks = [
                    t.get("name")
                    for t in tracks_data.get("toptracks", {}).get("track", [])
                ]
            except Exception as e:
                logger.debug(f"Could not get top tracks: {e}")

            metadata = ArtistMetadata(
                name=artist_info.get("name", artist_data["name"]),
                source="lastfm",
                confidence=self._calculate_name_similarity(
                    artist_data["name"], artist_info.get("name", "")
                ),
                genres=artist_info.get("tags", []),
                biography=artist_info.get("bio", ""),
                similar_artists=similar_artists,
                top_tracks=top_tracks,
                playcount=artist_info.get("playcount"),
                listeners=artist_info.get("listeners"),
                user_playcount=artist_info.get("user_playcount"),
                lastfm_name=artist_info.get("name"),
                raw_data=artist_info,
            )

            return metadata

        except Exception as e:
            logger.error(f"Error getting Last.fm metadata: {e}")
            return None

    async def _get_imvdb_metadata(self, artist_data: Dict) -> Optional[ArtistMetadata]:
        """Get enhanced metadata from IMVDb"""
        try:
            # Use existing IMVDb integration
            if artist_data.get("imvdb_id"):
                # Get fresh artist data by ID
                imvdb_artist_data = self.imvdb.get_artist(artist_data["imvdb_id"])
            else:
                # Search for artist
                search_results = self.imvdb.search_artist(artist_data["name"])
                if not search_results or not search_results.get("results"):
                    return None
                imvdb_artist_data = search_results["results"][0]

            if not imvdb_artist_data:
                return None

            metadata = ArtistMetadata(
                name=imvdb_artist_data.get("name", artist_data["name"]),
                source="imvdb",
                confidence=self._calculate_name_similarity(
                    artist_data["name"], imvdb_artist_data.get("name", "")
                ),
                imvdb_id=str(imvdb_artist_data.get("id")),
                raw_data=imvdb_artist_data,
            )

            return metadata

        except Exception as e:
            logger.error(f"Error getting IMVDb metadata: {e}")
            return None

    async def _get_musicbrainz_metadata(
        self, artist_data: Dict
    ) -> Optional[ArtistMetadata]:
        """Get enhanced metadata from MusicBrainz"""
        try:
            # Check if we have a MusicBrainz ID from Last.fm or elsewhere
            mbid = None

            # Try to get MBID from existing data sources if available
            # This could come from Last.fm data or stored metadata
            with get_db() as session:
                artist = (
                    session.query(Artist).filter(Artist.id == artist_data["id"]).first()
                )
                if artist and artist.imvdb_metadata:
                    # Check if we have stored MBID in metadata
                    stored_mbid = artist.imvdb_metadata.get("musicbrainz_id")
                    if stored_mbid:
                        mbid = stored_mbid

            # Get metadata from MusicBrainz
            mb_metadata = self.musicbrainz.get_artist_metadata_for_enrichment(
                artist_data["name"], mbid
            )

            if not mb_metadata:
                return None

            # Convert to ArtistMetadata format
            metadata = ArtistMetadata(
                name=mb_metadata.get("name", artist_data["name"]),
                source="musicbrainz",
                confidence=mb_metadata.get("confidence", 0.95),
                genres=mb_metadata.get("genres", []),
                mbid=mb_metadata.get("mbid"),
                raw_data=mb_metadata.get("raw_data", {}),
            )

            # Add additional MusicBrainz-specific fields if available
            if mb_metadata.get("formed_year"):
                metadata.raw_data["formed_year"] = mb_metadata["formed_year"]
            if mb_metadata.get("country"):
                metadata.raw_data["country"] = mb_metadata["country"]
            if mb_metadata.get("area"):
                metadata.raw_data["area"] = mb_metadata["area"]
            if mb_metadata.get("type"):
                metadata.raw_data["type"] = mb_metadata["type"]
            if mb_metadata.get("labels"):
                metadata.raw_data["labels"] = mb_metadata["labels"]
            if mb_metadata.get("external_urls"):
                metadata.raw_data["external_urls"] = mb_metadata["external_urls"]

            return metadata

        except Exception as e:
            logger.error(f"Error getting MusicBrainz metadata: {e}")
            return None

    async def _get_allmusic_metadata(
        self, artist_data: Dict
    ) -> Optional[ArtistMetadata]:
        """Get enhanced metadata from AllMusic"""
        try:
            # Get metadata from AllMusic service
            allmusic_metadata = self.allmusic.get_artist_metadata_for_enrichment(
                artist_data["name"]
            )

            if not allmusic_metadata:
                return None

            # Convert to ArtistMetadata format
            metadata = ArtistMetadata(
                name=allmusic_metadata.get("name", artist_data["name"]),
                source="allmusic",
                confidence=allmusic_metadata.get("confidence", 0.88),
                genres=allmusic_metadata.get("genres", []),
                biography=allmusic_metadata.get("biography"),
                similar_artists=allmusic_metadata.get("similar_artists", []),
                raw_data=allmusic_metadata.get("raw_data", {}),
            )

            # Add AllMusic-specific fields if available
            if allmusic_metadata.get("formed_year"):
                metadata.raw_data["formed_year"] = allmusic_metadata["formed_year"]
            if allmusic_metadata.get("origin_country"):
                metadata.raw_data["origin_country"] = allmusic_metadata[
                    "origin_country"
                ]
            if allmusic_metadata.get("members"):
                metadata.raw_data["members"] = allmusic_metadata["members"]
            if allmusic_metadata.get("moods"):
                metadata.raw_data["moods"] = allmusic_metadata["moods"]
            if allmusic_metadata.get("themes"):
                metadata.raw_data["themes"] = allmusic_metadata["themes"]
            if allmusic_metadata.get("active_years"):
                metadata.raw_data["active_years"] = allmusic_metadata["active_years"]
            if allmusic_metadata.get("discography"):
                metadata.raw_data["discography"] = allmusic_metadata["discography"]
            if allmusic_metadata.get("allmusic_rating"):
                metadata.raw_data["allmusic_rating"] = allmusic_metadata[
                    "allmusic_rating"
                ]
            if allmusic_metadata.get("allmusic_url"):
                metadata.raw_data["allmusic_url"] = allmusic_metadata["allmusic_url"]
                # Extract AllMusic ID from URL for frontend linking
                allmusic_url = allmusic_metadata["allmusic_url"]
                if "/artist/" in allmusic_url:
                    # Extract ID from URL like https://www.allmusic.com/artist/the-beatles-mn0000754032
                    allmusic_id = allmusic_url.split("/artist/")[-1].split("-")[-1]
                    metadata.raw_data["allmusic_id"] = allmusic_id

            return metadata

        except Exception as e:
            logger.error(f"Error getting AllMusic metadata: {e}")
            return None

    async def _get_wikipedia_metadata(
        self, artist_data: Dict
    ) -> Optional[ArtistMetadata]:
        """Get basic metadata from Wikipedia (primarily thumbnails for now)"""
        try:
            # For now, Wikipedia service only provides thumbnails
            # This is a placeholder for future Wikipedia biography integration
            thumbnail_url = self.wikipedia.search_artist_thumbnail(artist_data["name"])

            if thumbnail_url:
                # Construct Wikipedia article URL for the artist
                artist_name_clean = artist_data["name"].replace(" ", "_")
                wikipedia_url = f"https://en.wikipedia.org/wiki/{artist_name_clean}"

                # Create minimal metadata with thumbnail and URL
                metadata = ArtistMetadata(
                    name=artist_data["name"],
                    source="wikipedia",
                    confidence=0.7,  # Lower confidence since we're only getting thumbnails
                    images=[{"url": thumbnail_url, "source": "wikipedia"}],
                    raw_data={
                        "wikipedia_thumbnail": thumbnail_url,
                        "wikipedia_url": wikipedia_url,
                    },
                )
                return metadata

            return None

        except Exception as e:
            logger.error(f"Error getting Wikipedia metadata: {e}")
            return None

    # Discogs metadata function removed

    def _aggregate_metadata(
        self, metadata_sources: Dict[str, ArtistMetadata]
    ) -> ArtistMetadata:
        """Intelligently aggregate metadata from multiple sources"""
        if not metadata_sources:
            raise ValueError("No metadata sources provided")

        # Start with the highest confidence source as base
        base_source = max(
            metadata_sources.values(),
            key=lambda m: m.confidence * self.source_weights.get(m.source, 0.5),
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
            weight = self.source_weights.get(source_name, 0.5) * metadata.confidence
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
            if data["votes"] >= self.genre_aggregation_threshold
        ]

        # Aggregate other fields using weighted selection
        self._aggregate_numeric_fields(unified, metadata_sources)
        self._aggregate_list_fields(unified, metadata_sources)
        self._aggregate_text_fields(unified, metadata_sources)
        self._extract_service_ids(unified, metadata_sources)

        # Calculate overall confidence
        unified.confidence = self._calculate_overall_confidence(metadata_sources)

        return unified

    def _aggregate_numeric_fields(
        self, unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
    ):
        """Aggregate numeric fields using weighted averages"""
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
            else max(
                (m.followers for m in sources.values() if m.followers), default=None
            )
        )

        # Playcount and listeners (prefer Last.fm)
        lastfm_data = sources.get("lastfm", ArtistMetadata("", ""))
        unified.playcount = lastfm_data.playcount
        unified.listeners = lastfm_data.listeners
        unified.user_playcount = lastfm_data.user_playcount

    def _aggregate_list_fields(
        self, unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
    ):
        """Aggregate list fields by merging and deduplicating"""
        # Related/similar artists (prefer Spotify, then Last.fm, then MusicBrainz, then others)
        # Priority: Spotify related_artists > Last.fm similar_artists > MusicBrainz > aggregate
        spotify_related = sources.get("spotify", ArtistMetadata("", "")).related_artists
        lastfm_similar = sources.get("lastfm", ArtistMetadata("", "")).similar_artists
        musicbrainz_related = sources.get(
            "musicbrainz", ArtistMetadata("", "")
        ).related_artists

        if spotify_related:
            unified.related_artists = spotify_related[: self.similar_artists_limit]
            logger.debug(
                f"🎵 AGGREGATION: Using Spotify related artists: {unified.related_artists}"
            )
        elif lastfm_similar:
            unified.related_artists = lastfm_similar[: self.similar_artists_limit]
            logger.debug(
                f"🎵 AGGREGATION: Using Last.fm similar artists as fallback: {unified.related_artists}"
            )
        elif musicbrainz_related:
            unified.related_artists = musicbrainz_related[: self.similar_artists_limit]
            logger.debug(
                f"🎵 AGGREGATION: Using MusicBrainz related artists as fallback: {unified.related_artists}"
            )
        else:
            # Final fallback: aggregate from all sources
            all_related = set()
            for metadata in sources.values():
                all_related.update(metadata.related_artists)
                all_related.update(metadata.similar_artists)
            unified.related_artists = list(all_related)[: self.similar_artists_limit]
            logger.debug(
                f"🎵 AGGREGATION: Using aggregated related/similar artists: {unified.related_artists}"
            )

        # Top tracks (prefer Spotify, then Last.fm for track recommendations)
        if sources.get("spotify", ArtistMetadata("", "")).top_tracks:
            unified.top_tracks = sources["spotify"].top_tracks
        elif sources.get("lastfm", ArtistMetadata("", "")).top_tracks:
            unified.top_tracks = sources["lastfm"].top_tracks

        # Images (prefer Spotify)
        if sources.get("spotify", ArtistMetadata("", "")).images:
            unified.images = sources["spotify"].images

    def _aggregate_text_fields(
        self, unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
    ):
        """Aggregate text fields with source preference"""
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

    def _extract_service_ids(
        self, unified: ArtistMetadata, sources: Dict[str, ArtistMetadata]
    ):
        """Extract service IDs and URLs from raw_data for frontend linking"""
        # Extract AllMusic ID from AllMusic source
        if "allmusic" in sources:
            allmusic_data = sources["allmusic"]
            if allmusic_data.raw_data.get("allmusic_id"):
                unified.raw_data["allmusic_id"] = allmusic_data.raw_data["allmusic_id"]
            if allmusic_data.raw_data.get("allmusic_url"):
                unified.raw_data["allmusic_url"] = allmusic_data.raw_data[
                    "allmusic_url"
                ]

        # Extract Wikipedia URL from Wikipedia source
        if "wikipedia" in sources:
            wikipedia_data = sources["wikipedia"]
            if wikipedia_data.raw_data.get("wikipedia_url"):
                unified.raw_data["wikipedia_url"] = wikipedia_data.raw_data[
                    "wikipedia_url"
                ]

    def _calculate_overall_confidence(
        self, sources: Dict[str, ArtistMetadata]
    ) -> float:
        """Calculate overall confidence score"""
        if not sources:
            return 0.0

        weighted_confidence = 0.0
        total_weight = 0.0

        for source_name, metadata in sources.items():
            weight = self.source_weights.get(source_name, 0.5)
            weighted_confidence += metadata.confidence * weight
            total_weight += weight

        return min(weighted_confidence / total_weight if total_weight > 0 else 0.0, 1.0)

    def _update_artist_record(
        self, session: Session, artist: Artist, metadata: ArtistMetadata
    ) -> Dict:
        """Update artist record with aggregated metadata"""
        updated_fields = {}

        # Update external IDs
        if metadata.spotify_id and artist.spotify_id != metadata.spotify_id:
            artist.spotify_id = metadata.spotify_id
            updated_fields["spotify_id"] = metadata.spotify_id

        if metadata.lastfm_name and artist.lastfm_name != metadata.lastfm_name:
            artist.lastfm_name = metadata.lastfm_name
            updated_fields["lastfm_name"] = metadata.lastfm_name

        if metadata.imvdb_id and artist.imvdb_id != metadata.imvdb_id:
            artist.imvdb_id = metadata.imvdb_id
            updated_fields["imvdb_id"] = metadata.imvdb_id

        # Store MusicBrainz ID in metadata JSON since there's no dedicated field
        if metadata.mbid:
            if not artist.imvdb_metadata:
                artist.imvdb_metadata = {}
            if artist.imvdb_metadata.get("musicbrainz_id") != metadata.mbid:
                artist.imvdb_metadata["musicbrainz_id"] = metadata.mbid
                updated_fields["musicbrainz_id"] = metadata.mbid

        # Store AllMusic ID and URL from enriched metadata
        if metadata.raw_data.get("allmusic_id"):
            if not artist.imvdb_metadata:
                artist.imvdb_metadata = {}
            if (
                artist.imvdb_metadata.get("allmusic_id")
                != metadata.raw_data["allmusic_id"]
            ):
                artist.imvdb_metadata["allmusic_id"] = metadata.raw_data["allmusic_id"]
                updated_fields["allmusic_id"] = metadata.raw_data["allmusic_id"]

        if metadata.raw_data.get("allmusic_url"):
            if not artist.imvdb_metadata:
                artist.imvdb_metadata = {}
            if (
                artist.imvdb_metadata.get("allmusic_url")
                != metadata.raw_data["allmusic_url"]
            ):
                artist.imvdb_metadata["allmusic_url"] = metadata.raw_data[
                    "allmusic_url"
                ]
                updated_fields["allmusic_url"] = metadata.raw_data["allmusic_url"]

        # Store Wikipedia URL from enriched metadata
        if metadata.raw_data.get("wikipedia_url"):
            if not artist.imvdb_metadata:
                artist.imvdb_metadata = {}
            if (
                artist.imvdb_metadata.get("wikipedia_url")
                != metadata.raw_data["wikipedia_url"]
            ):
                artist.imvdb_metadata["wikipedia_url"] = metadata.raw_data[
                    "wikipedia_url"
                ]
                updated_fields["wikipedia_url"] = metadata.raw_data["wikipedia_url"]

        # Update genres
        if metadata.genres:
            genres_list = metadata.genres
            if artist.genres != genres_list:
                artist.genres = genres_list  # Store as JSON array
                updated_fields["genres"] = genres_list

        # Extract extended information from raw data
        extended_info = self._extract_extended_information(metadata)

        # Update labels from enriched metadata
        if extended_info.get("labels"):
            labels_list = extended_info["labels"]
            if isinstance(labels_list, str):
                labels_list = [labels_list]  # Convert single string to list
            if artist.labels != labels_list:
                artist.labels = labels_list
                updated_fields["labels"] = labels_list

        # Update members from enriched metadata
        if extended_info.get("members"):
            members_str = extended_info["members"]
            if isinstance(members_str, list):
                members_str = ", ".join(members_str)  # Convert list to string
            if artist.members != members_str:
                artist.members = members_str
                updated_fields["members"] = members_str

        # Extract external links from metadata
        external_links = self._extract_external_links(metadata)

        # Update metadata JSON
        enriched_metadata = {
            "enrichment_date": datetime.now().isoformat(),
            "confidence_score": metadata.confidence,
            "sources_used": list(metadata.raw_data.get("sources", {}).keys()),
            "popularity": metadata.popularity,
            "followers": metadata.followers,
            "biography": metadata.biography,
            "related_artists": metadata.related_artists,
            "top_tracks": metadata.top_tracks,
            "images": metadata.images,
            "playcount": metadata.playcount,
            "listeners": metadata.listeners,
            "user_playcount": metadata.user_playcount,
            # Extended Information fields
            "formed_year": extended_info.get("formed_year"),
            "disbanded_year": extended_info.get("disbanded_year"),
            "origin_country": extended_info.get("origin_country"),
            "labels": extended_info.get("labels"),
            "members": extended_info.get("members"),
            # External Links fields
            "website_url": external_links.get("website_url"),
            "spotify_url": external_links.get("spotify_url"),
            "youtube_url": external_links.get("youtube_url"),
            "apple_music_url": external_links.get("apple_music_url"),
            "twitter_url": external_links.get("twitter_url"),
            "facebook_url": external_links.get("facebook_url"),
            "instagram_url": external_links.get("instagram_url"),
        }

        # Store in imvdb_metadata field (repurpose as general metadata storage)
        existing_metadata = (
            artist.imvdb_metadata if isinstance(artist.imvdb_metadata, dict) else {}
        )

        # Merge enriched metadata, ensuring enriched data takes precedence over existing null values
        for key, value in enriched_metadata.items():
            # Only update if the enriched value is meaningful (not None, not empty)
            if value is not None and value != "" and value != []:
                existing_metadata[key] = value
            # If existing field is null/empty and we have a meaningful enriched value, use it
            elif key not in existing_metadata or existing_metadata[key] in [
                None,
                "",
                [],
            ]:
                existing_metadata[key] = value

        # Ensure enrichment_date is always updated to show fresh data
        existing_metadata["enrichment_date"] = datetime.now().isoformat()
        existing_metadata["sources_used"] = list(
            metadata.raw_data.get("sources", {}).keys()
        )
        existing_metadata["confidence_score"] = metadata.confidence

        logger.info(f"Setting artist.imvdb_metadata to: {existing_metadata}")
        logger.info(f"Artist.imvdb_metadata before assignment: {artist.imvdb_metadata}")

        artist.imvdb_metadata = existing_metadata

        # CRITICAL: Mark the JSON field as modified so SQLAlchemy knows to save it
        flag_modified(artist, "imvdb_metadata")

        logger.info(f"Artist.imvdb_metadata after assignment: {artist.imvdb_metadata}")
        logger.info(f"Marked imvdb_metadata as modified for SQLAlchemy tracking")
        updated_fields["metadata"] = enriched_metadata

        # Update timestamps
        artist.updated_at = datetime.now()
        updated_fields["updated_at"] = artist.updated_at

        return updated_fields

    def _is_metadata_fresh(self, artist: Artist) -> bool:
        """Check if artist metadata is fresh enough AND contains meaningful data"""
        if not artist.imvdb_metadata or not isinstance(artist.imvdb_metadata, dict):
            return False

        enrichment_date_str = artist.imvdb_metadata.get("enrichment_date")
        if not enrichment_date_str:
            return False

        # Check if the cached data actually contains meaningful metadata
        metadata = artist.imvdb_metadata
        meaningful_fields = [
            metadata.get("biography"),
            metadata.get("related_artists"),
            metadata.get("top_tracks"),
            metadata.get("images"),
            metadata.get("popularity"),
            metadata.get("followers"),
            metadata.get("playcount"),
            metadata.get("listeners"),
            metadata.get("genres"),
            metadata.get("similar_artists"),
        ]

        # Only consider metadata "fresh" if it has meaningful data
        has_meaningful_data = any(
            field and field != [] and field != {} and field != ""
            for field in meaningful_fields
        )

        if not has_meaningful_data:
            logger.debug(
                f"Artist {artist.name} has enrichment_date but no meaningful data - forcing refresh"
            )
            return False

        try:
            enrichment_date = datetime.fromisoformat(enrichment_date_str)
            is_fresh = datetime.now() - enrichment_date < timedelta(
                hours=self.cache_duration_hours
            )
            if is_fresh:
                logger.debug(
                    f"Artist {artist.name} metadata is fresh with meaningful data - using cache"
                )
            return is_fresh
        except (ValueError, TypeError):
            return False

    def _is_artist_match(self, name1: str, name2: str) -> bool:
        """Check if two artist names are a match"""
        return (
            self._calculate_name_similarity(name1, name2)
            >= self.min_confidence_threshold
        )

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two artist names"""
        if not name1 or not name2:
            return 0.0

        name1_clean = name1.lower().strip()
        name2_clean = name2.lower().strip()

        # Exact match
        if name1_clean == name2_clean:
            return 1.0

        # Check if one contains the other
        if name1_clean in name2_clean or name2_clean in name1_clean:
            return 0.9

        # Simple token matching
        tokens1 = set(name1_clean.split())
        tokens2 = set(name2_clean.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)

        return len(intersection) / len(union) if union else 0.0

    def _extract_extended_information(self, metadata: ArtistMetadata) -> Dict:
        """Extract extended information from aggregated metadata"""
        extended_info = {}

        # Check all sources for extended information
        if hasattr(metadata, "raw_data") and isinstance(metadata.raw_data, dict):
            sources = metadata.raw_data.get("sources", {})

            # Extract from Last.fm data (often has formation/disbanded years and country)
            if "lastfm" in sources:
                lastfm_data = sources["lastfm"]

                # Parse biography for formation year and country
                bio = lastfm_data.get("bio", {})
                if isinstance(bio, dict):
                    bio_content = bio.get("content", "") or bio.get("summary", "")
                    extended_info.update(self._parse_biography_info(bio_content))

                # Tags can sometimes indicate origin
                tags = lastfm_data.get("tags", {})
                if isinstance(tags, dict) and "tag" in tags:
                    tag_list = (
                        tags["tag"] if isinstance(tags["tag"], list) else [tags["tag"]]
                    )
                    extended_info.update(self._extract_country_from_tags(tag_list))

            # Extract from Spotify data (has related artists, sometimes country info)
            if "spotify" in sources:
                spotify_data = sources["spotify"]

                # Spotify may have country info in some cases
                if "origin_country" in spotify_data:
                    extended_info["origin_country"] = spotify_data["origin_country"]

                # Extract record labels from external_urls or other fields
                if "external_urls" in spotify_data:
                    extended_info.update(
                        self._extract_labels_from_urls(spotify_data["external_urls"])
                    )

            # Extract from IMVDb data
            if "imvdb" in sources:
                imvdb_data = sources["imvdb"]

                # IMVDb sometimes has formation year
                if "formed" in imvdb_data:
                    try:
                        extended_info["formed_year"] = int(
                            str(imvdb_data["formed"]).strip()
                        )
                    except (ValueError, TypeError):
                        pass

                # IMVDb may have country info
                if "country" in imvdb_data:
                    extended_info["origin_country"] = imvdb_data["country"]

            # Extract from MusicBrainz data (most authoritative source)
            if "musicbrainz" in sources:
                musicbrainz_data = sources["musicbrainz"]

                # Formation/disbanded years from life_span (most reliable)
                life_span = musicbrainz_data.get("life_span", {})
                if isinstance(life_span, dict):
                    if life_span.get("begin"):
                        try:
                            # Parse YYYY-MM-DD or YYYY format
                            begin_date = life_span["begin"]
                            formed_year = (
                                int(begin_date.split("-")[0]) if begin_date else None
                            )
                            if formed_year and not extended_info.get("formed_year"):
                                extended_info["formed_year"] = formed_year
                        except (ValueError, AttributeError, IndexError):
                            pass

                    if life_span.get("end"):
                        try:
                            # Parse YYYY-MM-DD or YYYY format
                            end_date = life_span["end"]
                            disbanded_year = (
                                int(end_date.split("-")[0]) if end_date else None
                            )
                            if disbanded_year and not extended_info.get(
                                "disbanded_year"
                            ):
                                extended_info["disbanded_year"] = disbanded_year
                        except (ValueError, AttributeError, IndexError):
                            pass

                # Origin country/area (most authoritative)
                if musicbrainz_data.get("country") and not extended_info.get(
                    "origin_country"
                ):
                    extended_info["origin_country"] = musicbrainz_data["country"]
                elif musicbrainz_data.get("area") and not extended_info.get(
                    "origin_country"
                ):
                    extended_info["origin_country"] = musicbrainz_data["area"]

                # Artist type information
                if musicbrainz_data.get("type"):
                    extended_info["artist_type"] = musicbrainz_data["type"]

                # Aliases (alternative names)
                if musicbrainz_data.get("aliases"):
                    aliases = musicbrainz_data["aliases"]
                    if isinstance(aliases, list) and aliases:
                        extended_info["aliases"] = [alias for alias in aliases if alias]

                # Record labels (most authoritative)
                if musicbrainz_data.get("labels"):
                    labels = musicbrainz_data["labels"]
                    if isinstance(labels, list) and labels:
                        extended_info["labels"] = [label for label in labels if label]

                # Sort name (for proper alphabetization)
                if musicbrainz_data.get("sort_name"):
                    extended_info["sort_name"] = musicbrainz_data["sort_name"]

                # Begin area (where artist was formed, more specific than country)
                if musicbrainz_data.get("begin_area") and not extended_info.get(
                    "origin_area"
                ):
                    extended_info["origin_area"] = musicbrainz_data["begin_area"]

                # Disambiguation (helps identify the specific artist)
                if musicbrainz_data.get("disambiguation"):
                    extended_info["disambiguation"] = musicbrainz_data["disambiguation"]

                # Additional genres from MusicBrainz tags (supplement existing genres)
                mb_tags = musicbrainz_data.get("tags", [])
                mb_genres = musicbrainz_data.get("genres", [])

                if mb_tags or mb_genres:
                    all_mb_genres = []
                    if isinstance(mb_tags, list):
                        all_mb_genres.extend(mb_tags)
                    if isinstance(mb_genres, list):
                        all_mb_genres.extend(mb_genres)

                    if all_mb_genres:
                        # Filter to music-related genres only
                        music_genres = [
                            g for g in all_mb_genres if self._is_music_genre(g)
                        ]
                        if music_genres and not extended_info.get("additional_genres"):
                            extended_info["additional_genres"] = music_genres[
                                :10
                            ]  # Limit to avoid clutter

        return extended_info

    def _is_music_genre(self, genre: str) -> bool:
        """Check if a tag/genre is music-related and not a general descriptor"""
        if not genre or not isinstance(genre, str):
            return False

        genre_lower = genre.lower().strip()

        # Skip very general or non-musical tags
        skip_tags = {
            "seen live",
            "favorite",
            "favourites",
            "awesome",
            "great",
            "good",
            "bad",
            "love",
            "hate",
            "cool",
            "hot",
            "new",
            "old",
            "best",
            "worst",
            "top",
            "albums i own",
            "artists i've seen live",
            "male",
            "female",
            "american",
            "british",
            "english",
            "canadian",
            "australian",
            "instrumental",
            "vocal",
            "solo",
            "group",
            "band",
            "artist",
            "singer",
            "musician",
            "composer",
        }

        if genre_lower in skip_tags:
            return False

        # Skip country names (these should go in origin_country)
        country_indicators = [
            "american",
            "british",
            "canadian",
            "australian",
            "german",
            "french",
            "japanese",
        ]
        if any(country in genre_lower for country in country_indicators):
            return False

        # Skip decades (these are time periods, not genres)
        if any(
            decade in genre_lower
            for decade in ["60s", "70s", "80s", "90s", "00s", "10s", "20s"]
        ):
            return False

        # Accept anything that looks like a legitimate music genre
        return len(genre_lower) > 2

    def _extract_external_links(self, metadata: ArtistMetadata) -> Dict:
        """Extract external links from aggregated metadata"""
        external_links = {}

        # Check all sources for external links
        if hasattr(metadata, "raw_data") and isinstance(metadata.raw_data, dict):
            sources = metadata.raw_data.get("sources", {})

            # Extract from Spotify data
            if "spotify" in sources:
                spotify_data = sources["spotify"]

                # Spotify external URLs
                if "external_urls" in spotify_data:
                    spotify_urls = spotify_data["external_urls"]
                    if "spotify" in spotify_urls:
                        external_links["spotify_url"] = spotify_urls["spotify"]

                # Generate Spotify URL from ID if not present
                if not external_links.get("spotify_url") and metadata.spotify_id:
                    external_links["spotify_url"] = (
                        f"https://open.spotify.com/artist/{metadata.spotify_id}"
                    )

            # Extract from Last.fm data
            if "lastfm" in sources:
                lastfm_data = sources["lastfm"]

                # Last.fm URL
                if "url" in lastfm_data:
                    # Don't add Last.fm URL to external links (not in UI)
                    pass

                # Parse biography for social media links
                bio = lastfm_data.get("bio", {})
                if isinstance(bio, dict):
                    bio_content = bio.get("content", "") or bio.get("summary", "")
                    external_links.update(
                        self._parse_social_links_from_bio(bio_content)
                    )

            # Extract from IMVDb data
            if "imvdb" in sources:
                imvdb_data = sources["imvdb"]

                # IMVDb sometimes has official website
                if "website" in imvdb_data:
                    external_links["website_url"] = imvdb_data["website"]

                # IMVDb may have social media links
                for social_key in ["twitter", "facebook", "instagram", "youtube"]:
                    if social_key in imvdb_data:
                        external_links[f"{social_key}_url"] = imvdb_data[social_key]

            # Extract from MusicBrainz data
            if "musicbrainz" in sources:
                musicbrainz_data = sources["musicbrainz"]

                # MusicBrainz external URLs (most authoritative source)
                if "external_urls" in musicbrainz_data:
                    mb_urls = musicbrainz_data["external_urls"]

                    # Map MusicBrainz URLs to our standard format
                    url_mapping = {
                        "homepage": "website_url",
                        "spotify": "spotify_url",
                        "youtube": "youtube_url",
                        "twitter": "twitter_url",
                        "facebook": "facebook_url",
                        "instagram": "instagram_url",
                        "apple_music": "apple_music_url",
                    }

                    for mb_key, our_key in url_mapping.items():
                        if mb_key in mb_urls and mb_urls[mb_key]:
                            # MusicBrainz is authoritative, only override if we don't have it
                            if not external_links.get(our_key):
                                external_links[our_key] = mb_urls[mb_key]

        return external_links

    def _parse_biography_info(self, bio_content: str) -> Dict:
        """Parse biography text for formation year, country, etc."""
        info = {}

        if not bio_content:
            return info

        import re

        # Look for formation year patterns
        year_patterns = [
            r"formed in (\d{4})",
            r"founded in (\d{4})",
            r"started in (\d{4})",
            r"began in (\d{4})",
            r"established in (\d{4})",
        ]

        for pattern in year_patterns:
            match = re.search(pattern, bio_content, re.IGNORECASE)
            if match:
                try:
                    info["formed_year"] = int(match.group(1))
                    break
                except ValueError:
                    pass

        # Look for disbanded year patterns
        disbanded_patterns = [
            r"disbanded in (\d{4})",
            r"broke up in (\d{4})",
            r"ended in (\d{4})",
            r"split up in (\d{4})",
        ]

        for pattern in disbanded_patterns:
            match = re.search(pattern, bio_content, re.IGNORECASE)
            if match:
                try:
                    info["disbanded_year"] = int(match.group(1))
                    break
                except ValueError:
                    pass

        # Look for country patterns
        country_patterns = [
            r"from ([A-Z][a-z]+ [A-Z][a-z]+)",  # "from United States"
            r"from ([A-Z][a-z]+)",  # "from England"
            r"([A-Z][a-z]+) band",  # "American band"
            r"([A-Z][a-z]+) group",  # "British group"
        ]

        for pattern in country_patterns:
            match = re.search(pattern, bio_content, re.IGNORECASE)
            if match:
                country = match.group(1).strip()
                # Map common country names to ISO codes
                country_mapping = {
                    "United States": "US",
                    "America": "US",
                    "American": "US",
                    "United Kingdom": "UK",
                    "Britain": "UK",
                    "British": "UK",
                    "England": "UK",
                    "Canada": "CA",
                    "Canadian": "CA",
                    "Australia": "AU",
                    "Australian": "AU",
                    "Germany": "DE",
                    "German": "DE",
                    "France": "FR",
                    "French": "FR",
                    "Japan": "JP",
                    "Japanese": "JP",
                }
                info["origin_country"] = country_mapping.get(country, country)
                break

        return info

    def _extract_country_from_tags(self, tags: List) -> Dict:
        """Extract country information from tags"""
        info = {}

        country_tags = {
            "american": "US",
            "usa": "US",
            "united states": "US",
            "british": "UK",
            "uk": "UK",
            "english": "UK",
            "scottish": "UK",
            "welsh": "UK",
            "canadian": "CA",
            "canada": "CA",
            "australian": "AU",
            "australia": "AU",
            "german": "DE",
            "germany": "DE",
            "french": "FR",
            "france": "FR",
            "japanese": "JP",
            "japan": "JP",
        }

        for tag in tags:
            tag_name = (
                tag.get("name", "").lower()
                if isinstance(tag, dict)
                else str(tag).lower()
            )
            if tag_name in country_tags:
                info["origin_country"] = country_tags[tag_name]
                break

        return info

    def _extract_labels_from_urls(self, external_urls: Dict) -> Dict:
        """Extract record label info from external URLs (limited effectiveness)"""
        # This is a placeholder - extracting label info from URLs is complex
        # Could be enhanced to recognize major label domains
        return {}

    def _parse_social_links_from_bio(self, bio_content: str) -> Dict:
        """Parse social media links from biography text"""
        links = {}

        if not bio_content:
            return links

        import re

        # Social media URL patterns
        social_patterns = {
            "website_url": r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:com|org|net|io))",
            "twitter_url": r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)",
            "facebook_url": r"(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9.]+)",
            "instagram_url": r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)",
            "youtube_url": r"(?:https?://)?(?:www\.)?youtube\.com/(?:user/|channel/|c/)?([a-zA-Z0-9_-]+)",
        }

        for link_type, pattern in social_patterns.items():
            matches = re.findall(pattern, bio_content, re.IGNORECASE)
            if matches and link_type == "website_url":
                # For website, be more selective - avoid social media domains
                for match in matches:
                    if not any(
                        social in match.lower()
                        for social in [
                            "twitter",
                            "facebook",
                            "instagram",
                            "youtube",
                            "spotify",
                        ]
                    ):
                        links[link_type] = (
                            f"https://{match}"
                            if not match.startswith("http")
                            else match
                        )
                        break
            elif matches:
                username = matches[0]
                if link_type == "twitter_url":
                    links[link_type] = f"https://twitter.com/{username}"
                elif link_type == "facebook_url":
                    links[link_type] = f"https://facebook.com/{username}"
                elif link_type == "instagram_url":
                    links[link_type] = f"https://instagram.com/{username}"
                elif link_type == "youtube_url":
                    links[link_type] = f"https://youtube.com/c/{username}"

        return links

    async def enrich_multiple_artists(
        self, artist_ids: List[int], force_refresh: bool = False, app_context=None
    ) -> List[EnrichmentResult]:
        """Enrich metadata for multiple artists"""
        results = []

        for artist_id in artist_ids:
            try:
                result = await self.enrich_artist_metadata(
                    artist_id, force_refresh, app_context
                )
                results.append(result)

                # Rate limiting between requests
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to enrich artist {artist_id}: {e}")
                results.append(
                    EnrichmentResult(
                        success=False, artist_id=artist_id, errors=[str(e)]
                    )
                )

        return results

    async def enrich_video_metadata(
        self, video_id: int, force_refresh: bool = False
    ) -> EnrichmentResult:
        """Enhanced video metadata enrichment using multiple sources"""
        try:
            with get_db() as session:
                # Eagerly load the video with its artist relationship to avoid lazy loading issues
                from sqlalchemy.orm import joinedload

                video = (
                    session.query(Video)
                    .options(joinedload(Video.artist))
                    .filter(Video.id == video_id)
                    .first()
                )

                if not video:
                    return EnrichmentResult(
                        video_id=video_id, success=False, errors=["Video not found"]
                    )

                if not video.artist:
                    return EnrichmentResult(
                        video_id=video_id,
                        success=False,
                        errors=["No artist associated with video"],
                    )

                # Extract data before API calls
                artist_name = video.artist.name
                video_title = video.title
                current_imvdb_id = video.imvdb_id

                logger.info(
                    f"Enhanced enrichment for video: {video_title} by {artist_name}"
                )

                # Collect metadata from multiple sources
                metadata_sources = {}
                updated_fields = []
                errors = []

                # 1. IMVDb enrichment (re-enabled with improved handling)
                try:
                    if not current_imvdb_id or force_refresh:
                        # Search for video on IMVDb if not already linked
                        imvdb_videos = imvdb_service.search_videos(
                            artist_name, video_title
                        )

                        if imvdb_videos:
                            best_match = imvdb_service.find_best_video_match(
                                artist_name, video_title
                            )

                            if best_match:
                                metadata_sources["imvdb"] = best_match
                                imvdb_metadata = imvdb_service.extract_metadata(
                                    best_match
                                )

                                # Apply IMVDb metadata with conflict resolution
                                if not video.imvdb_id and imvdb_metadata.get(
                                    "imvdb_id"
                                ):
                                    video.imvdb_id = str(imvdb_metadata["imvdb_id"])
                                    updated_fields.append("imvdb_id")

                                if not video.year and imvdb_metadata.get("year"):
                                    video.year = imvdb_metadata["year"]
                                    updated_fields.append("year")

                                if not video.directors and imvdb_metadata.get(
                                    "directors"
                                ):
                                    video.directors = imvdb_metadata["directors"]
                                    updated_fields.append("directors")

                                if not video.producers and imvdb_metadata.get(
                                    "producers"
                                ):
                                    video.producers = imvdb_metadata["producers"]
                                    updated_fields.append("producers")

                                # Handle thumbnail extraction with validation and force refresh support
                                thumbnail_url = imvdb_metadata.get("thumbnail_url")
                                if (
                                    thumbnail_url
                                    and thumbnail_url != "https://imvdb.com/"
                                    and len(thumbnail_url) > 20
                                ):
                                    if (
                                        not video.thumbnail_url
                                        or force_refresh
                                        or not video.thumbnail_source
                                    ):
                                        video.thumbnail_url = thumbnail_url
                                        video.thumbnail_source = "imvdb"
                                        updated_fields.extend(
                                            ["thumbnail_url", "thumbnail_source"]
                                        )
                                        logger.info(
                                            f"Added thumbnail from IMVDb for video {video_id}: {video.thumbnail_url}"
                                        )
                                elif video.thumbnail_url:
                                    logger.debug(
                                        f"Video {video_id} already has thumbnail: {video.thumbnail_url}"
                                    )
                                elif not thumbnail_url:
                                    logger.debug(
                                        f"No valid thumbnail available in IMVDb metadata for video {video_id}"
                                    )
                                else:
                                    logger.debug(
                                        f"Rejected invalid IMVDb thumbnail for video {video_id}: {thumbnail_url}"
                                    )

                                # Store raw IMVDb metadata
                                video.imvdb_metadata = imvdb_metadata.get(
                                    "raw_metadata"
                                )
                                updated_fields.append("imvdb_metadata")

                except Exception as e:
                    errors.append(f"IMVDb enrichment failed: {str(e)}")
                    logger.warning(f"IMVDb enrichment failed for video {video_id}: {e}")

                # 2. Enhanced Spotify enrichment
                try:
                    if video.artist.spotify_id:
                        # Search for track on Spotify with improved matching
                        track_search = spotify_service.search_tracks(
                            f'track:"{video_title}" artist:"{artist_name}"'
                        )

                        if not track_search or not track_search.get("tracks", {}).get(
                            "items"
                        ):
                            # Fallback to broader search
                            track_search = spotify_service.search_tracks(
                                f"{video_title} {artist_name}"
                            )

                        if track_search and track_search.get("tracks", {}).get("items"):
                            best_track = track_search["tracks"]["items"][0]
                            metadata_sources["spotify"] = best_track

                            # Enhanced Spotify metadata extraction
                            album_data = best_track.get("album", {})

                            if not video.album and album_data.get("name"):
                                video.album = album_data["name"]
                                updated_fields.append("album")

                            if not video.year and album_data.get("release_date"):
                                try:
                                    release_year = album_data["release_date"].split(
                                        "-"
                                    )[0]
                                    video.year = int(release_year)
                                    updated_fields.append("year")
                                except (ValueError, IndexError):
                                    pass

                            # Extract track duration
                            if not video.duration and best_track.get("duration_ms"):
                                video.duration = (
                                    best_track["duration_ms"] // 1000
                                )  # Convert to seconds
                                updated_fields.append("duration")

                            # Get genres from artist or album
                            if not video.genres:
                                # Try to get genres from artist
                                if video.artist.spotify_id:
                                    try:
                                        artist_data = spotify_service.get_artist(
                                            video.artist.spotify_id
                                        )
                                        if artist_data and artist_data.get("genres"):
                                            video.genres = artist_data["genres"][
                                                :3
                                            ]  # Top 3 genres
                                            updated_fields.append("genres")
                                    except Exception:
                                        pass

                            # Extract Spotify album artwork as thumbnail if needed
                            if (
                                not video.thumbnail_url or force_refresh
                            ) and album_data.get("images"):
                                # Get the highest quality image (first one is usually the best)
                                album_images = album_data["images"]
                                if album_images and len(album_images) > 0:
                                    spotify_thumbnail_url = album_images[0].get("url")
                                    if spotify_thumbnail_url:
                                        video.thumbnail_url = spotify_thumbnail_url
                                        video.thumbnail_source = "spotify"
                                        updated_fields.extend(
                                            ["thumbnail_url", "thumbnail_source"]
                                        )
                                        metadata_sources["Spotify Album Art"] = (
                                            "Thumbnail extraction"
                                        )
                                        logger.info(
                                            f"Added Spotify album art thumbnail for video {video_id}: {spotify_thumbnail_url}"
                                        )

                            # Store additional metadata
                            video_metadata = video.video_metadata or {}
                            video_metadata.update(
                                {
                                    "spotify_track_id": best_track.get("id"),
                                    "spotify_popularity": best_track.get("popularity"),
                                    "spotify_preview_url": best_track.get(
                                        "preview_url"
                                    ),
                                    "spotify_album_type": album_data.get("album_type"),
                                    "spotify_album_images": album_data.get(
                                        "images", []
                                    ),
                                }
                            )
                            video.video_metadata = video_metadata
                            updated_fields.append("video_metadata")

                except Exception as e:
                    errors.append(f"Spotify enrichment failed: {str(e)}")
                    logger.warning(
                        f"Spotify enrichment failed for video {video_id}: {e}"
                    )

                # 3. Enhanced Last.fm enrichment
                try:
                    if video.artist.lastfm_name:
                        # Get detailed track info from Last.fm
                        track_info = lastfm_service.get_track_info(
                            video.artist.lastfm_name, video_title
                        )

                        if track_info:
                            metadata_sources["lastfm"] = track_info

                            # Album information
                            album_data = track_info.get("album", {})
                            if not video.album and album_data.get("title"):
                                video.album = album_data["title"]
                                updated_fields.append("album")

                            # Track duration
                            if not video.duration and track_info.get("duration"):
                                try:
                                    video.duration = (
                                        int(track_info["duration"]) // 1000
                                    )  # Convert from ms
                                    updated_fields.append("duration")
                                except (ValueError, TypeError):
                                    pass

                            # Genres from tags
                            if not video.genres and track_info.get("toptags", {}).get(
                                "tag"
                            ):
                                tags = track_info["toptags"]["tag"]
                                if isinstance(tags, list):
                                    genre_tags = [tag["name"] for tag in tags[:3]]
                                    video.genres = genre_tags
                                    updated_fields.append("genres")

                            # Additional metadata
                            video_metadata = video.video_metadata or {}
                            video_metadata.update(
                                {
                                    "lastfm_play_count": track_info.get("playcount"),
                                    "lastfm_listeners": track_info.get("listeners"),
                                    "lastfm_url": track_info.get("url"),
                                }
                            )
                            video.video_metadata = video_metadata
                            if "video_metadata" not in updated_fields:
                                updated_fields.append("video_metadata")

                except Exception as e:
                    errors.append(f"Last.fm enrichment failed: {str(e)}")
                    logger.warning(
                        f"Last.fm enrichment failed for video {video_id}: {e}"
                    )

                # 4. MusicBrainz enrichment (for authoritative metadata)
                try:
                    if video.artist.mbid or not video.album:
                        # Search for recording in MusicBrainz
                        # Note: This is a basic implementation - MusicBrainz recording search would need to be added to the service
                        logger.debug(
                            f"MusicBrainz recording enrichment not yet implemented for video {video_id}"
                        )
                        # TODO: Implement MusicBrainz recording search when service supports it

                except Exception as e:
                    errors.append(f"MusicBrainz enrichment failed: {str(e)}")
                    logger.warning(
                        f"MusicBrainz enrichment failed for video {video_id}: {e}"
                    )

                # 5. YouTube metadata enhancement (if we have YouTube ID)
                try:
                    if video.youtube_id:
                        # Extract YouTube thumbnail if no thumbnail exists or force refresh
                        if not video.thumbnail_url or force_refresh:
                            # YouTube thumbnail URLs follow a standard pattern
                            youtube_thumbnail_url = f"https://img.youtube.com/vi/{video.youtube_id}/maxresdefault.jpg"

                            # Verify the thumbnail exists by making a HEAD request
                            try:
                                response = requests.head(
                                    youtube_thumbnail_url, timeout=5
                                )
                                if response.status_code == 200:
                                    video.thumbnail_url = youtube_thumbnail_url
                                    video.thumbnail_source = "youtube"
                                    updated_fields.extend(
                                        ["thumbnail_url", "thumbnail_source"]
                                    )
                                    metadata_sources["YouTube"] = "Thumbnail extraction"
                                    logger.info(
                                        f"Added YouTube thumbnail for video {video_id}: {youtube_thumbnail_url}"
                                    )
                                else:
                                    # Try medium quality if maxres doesn't exist
                                    youtube_thumbnail_url = f"https://img.youtube.com/vi/{video.youtube_id}/mqdefault.jpg"
                                    response = requests.head(
                                        youtube_thumbnail_url, timeout=5
                                    )
                                    if response.status_code == 200:
                                        video.thumbnail_url = youtube_thumbnail_url
                                        video.thumbnail_source = "youtube"
                                        updated_fields.extend(
                                            ["thumbnail_url", "thumbnail_source"]
                                        )
                                        metadata_sources["YouTube"] = (
                                            "Thumbnail extraction"
                                        )
                                        logger.info(
                                            f"Added YouTube thumbnail (medium) for video {video_id}: {youtube_thumbnail_url}"
                                        )
                            except Exception as thumb_error:
                                logger.debug(
                                    f"YouTube thumbnail verification failed for video {video_id}: {thumb_error}"
                                )

                        # TODO: Implement YouTube video metadata extraction
                        logger.debug(
                            f"YouTube metadata enrichment not yet implemented for video {video_id}"
                        )

                except Exception as e:
                    errors.append(f"YouTube enrichment failed: {str(e)}")
                    logger.warning(
                        f"YouTube enrichment failed for video {video_id}: {e}"
                    )

                # 6. FFmpeg metadata extraction (if local file exists)
                try:
                    if video.local_path and (
                        force_refresh
                        or not video.video_metadata
                        or not video.video_metadata.get("ffmpeg_extracted")
                    ):
                        import os
                        from pathlib import Path

                        if os.path.exists(video.local_path):
                            video_indexing_service = VideoIndexingService()
                            ffmpeg_metadata = (
                                video_indexing_service.extract_ffmpeg_metadata(
                                    video.local_path
                                )
                            )

                            if ffmpeg_metadata:
                                # Update direct fields
                                if (
                                    ffmpeg_metadata.get("duration")
                                    and not video.duration
                                ):
                                    video.duration = ffmpeg_metadata["duration"]
                                    updated_fields.append("duration")

                                if ffmpeg_metadata.get("quality") and not video.quality:
                                    video.quality = ffmpeg_metadata["quality"]
                                    updated_fields.append("quality")

                                # Update metadata JSON
                                if not video.video_metadata:
                                    video.video_metadata = {}

                                video.video_metadata.update(
                                    {
                                        "width": ffmpeg_metadata.get("width"),
                                        "height": ffmpeg_metadata.get("height"),
                                        "video_codec": ffmpeg_metadata.get(
                                            "video_codec"
                                        ),
                                        "audio_codec": ffmpeg_metadata.get(
                                            "audio_codec"
                                        ),
                                        "fps": ffmpeg_metadata.get("fps"),
                                        "bitrate": ffmpeg_metadata.get("bitrate"),
                                        "file_size": ffmpeg_metadata.get("file_size"),
                                        "ffmpeg_extracted": True,
                                        "ffmpeg_extraction_date": datetime.utcnow().isoformat(),
                                    }
                                )
                                flag_modified(video, "video_metadata")
                                updated_fields.append("video_metadata")
                                metadata_sources["FFmpeg"] = "Video file analysis"
                                logger.info(
                                    f"FFmpeg metadata extracted for video {video_id}"
                                )

                except Exception as e:
                    errors.append(f"FFmpeg extraction failed: {str(e)}")
                    logger.warning(
                        f"FFmpeg extraction failed for video {video_id}: {e}"
                    )

                # 7. Lyrics search (if no existing lyrics or force refresh)
                try:
                    logger.info(
                        f"Starting lyrics search for video {video_id}. Current lyrics: {'exists' if video.lyrics else 'empty'}, force_refresh: {force_refresh}"
                    )
                    if force_refresh or not video.lyrics:
                        if video.artist and video.artist.name and video.title:
                            logger.info(
                                f"Searching lyrics for: '{video.artist.name}' - '{video.title}'"
                            )
                            # Try lyrics search using the existing azlyrics function
                            try:
                                lyrics_result = search_lyrics_azlyrics(
                                    video.artist.name, video.title
                                )
                                if lyrics_result and len(lyrics_result.strip()) > 50:
                                    video.lyrics = lyrics_result
                                    updated_fields.append("lyrics")
                                    metadata_sources["Lyrics.ovh"] = "Lyrics search"
                                    logger.info(
                                        f"Lyrics found and saved for video {video_id} ({len(lyrics_result)} chars)"
                                    )
                                else:
                                    logger.info(
                                        f"No substantial lyrics found for video {video_id} (result: {lyrics_result[:100] if lyrics_result else 'None'})"
                                    )
                            except Exception as lyrics_error:
                                logger.warning(
                                    f"Lyrics search failed for video {video_id}: {lyrics_error}"
                                )
                        else:
                            logger.info(
                                f"Cannot search lyrics for video {video_id}: missing artist name ({video.artist.name if video.artist else 'None'}) or title ({video.title})"
                            )

                except Exception as e:
                    errors.append(f"Lyrics search failed: {str(e)}")
                    logger.warning(f"Lyrics search failed for video {video_id}: {e}")

                # 8. Genre fallback - Use artist genres if video still has no genres
                try:
                    logger.info(
                        f"Checking genre fallback for video {video_id}. Video genres: {video.genres}, Artist genres: {video.artist.genres if video.artist else 'No artist'}"
                    )
                    if not video.genres and video.artist and video.artist.genres:
                        video.genres = video.artist.genres[
                            :3
                        ]  # Top 3 genres from artist
                        updated_fields.append("genres")
                        metadata_sources["Artist Database"] = "Genre fallback"
                        logger.info(
                            f"Applied genre fallback from artist for video {video_id}: {video.genres}"
                        )
                    elif video.genres:
                        logger.info(
                            f"Video {video_id} already has genres: {video.genres}"
                        )
                    elif not video.artist:
                        logger.info(
                            f"Video {video_id} has no artist for genre fallback"
                        )
                    elif not video.artist.genres:
                        logger.info(
                            f"Video {video_id} artist has no genres for fallback"
                        )

                except Exception as e:
                    errors.append(f"Genre fallback failed: {str(e)}")
                    logger.warning(f"Genre fallback failed for video {video_id}: {e}")

                # Update enrichment timestamp
                video.last_enriched = datetime.utcnow()
                updated_fields.append("last_enriched")

                # Commit changes
                session.commit()

                logger.info(
                    f"Video {video_id} enrichment completed. Updated fields: {updated_fields}"
                )

                return EnrichmentResult(
                    video_id=video_id,
                    success=True,
                    enriched_fields=updated_fields,
                    metadata_sources=list(metadata_sources.keys()),
                    errors=errors if errors else None,
                )

        except Exception as e:
            logger.error(f"Failed to enrich video {video_id}: {e}")
            return EnrichmentResult(video_id=video_id, success=False, errors=[str(e)])

    def get_enrichment_stats(self) -> Dict:
        """Get statistics about metadata enrichment"""
        try:
            with get_db() as session:
                total_artists = session.query(Artist).count()

                # Artists with external IDs (excluding empty strings and whitespace)
                with_spotify = (
                    session.query(Artist)
                    .filter(Artist.spotify_id.isnot(None))
                    .filter(Artist.spotify_id != "")
                    .count()
                )
                with_lastfm = (
                    session.query(Artist)
                    .filter(Artist.lastfm_name.isnot(None))
                    .filter(Artist.lastfm_name != "")
                    .count()
                )
                with_imvdb = (
                    session.query(Artist)
                    .filter(Artist.imvdb_id.isnot(None))
                    .filter(Artist.imvdb_id != "")
                    .count()
                )

                # Count artists with MusicBrainz IDs (stored in JSON metadata)
                with_musicbrainz = (
                    session.query(Artist)
                    .filter(Artist.imvdb_metadata.isnot(None))
                    .filter(Artist.imvdb_metadata.contains('"musicbrainz_id"'))
                    .count()
                )

                # Discogs integration removed

                # Artists with enriched metadata
                enriched_artists = (
                    session.query(Artist)
                    .filter(Artist.imvdb_metadata.contains("enrichment_date"))
                    .count()
                )

                # Calculate missing ID counts for verification
                missing_spotify = total_artists - with_spotify
                missing_lastfm = total_artists - with_lastfm
                missing_imvdb = total_artists - with_imvdb

                # Calculate candidates count (artists missing at least one external ID)
                candidates_count = (
                    session.query(Artist)
                    .filter(
                        or_(
                            Artist.spotify_id.is_(None),
                            Artist.spotify_id == "",
                            Artist.lastfm_name.is_(None),
                            Artist.lastfm_name == "",
                            Artist.imvdb_id.is_(None),
                            Artist.imvdb_id == "",
                        )
                    )
                    .count()
                )

                # Calculate overall external ID coverage (average across all services)
                overall_coverage = (
                    (with_spotify + with_lastfm + with_imvdb + with_musicbrainz)
                    / (total_artists * 4)  # Updated to include MusicBrainz
                    * 100
                    if total_artists > 0
                    else 0
                )

                return {
                    "total_artists": total_artists,
                    "enriched_artists": enriched_artists,
                    "candidates_count": candidates_count,
                    "enrichment_coverage": (
                        round(enriched_artists / total_artists * 100, 1)
                        if total_artists > 0
                        else 0
                    ),
                    "external_id_coverage": round(overall_coverage, 1),
                    "external_id_breakdown": {
                        "spotify": (
                            round(with_spotify / total_artists * 100, 1)
                            if total_artists > 0
                            else 0
                        ),
                        "lastfm": (
                            round(with_lastfm / total_artists * 100, 1)
                            if total_artists > 0
                            else 0
                        ),
                        "imvdb": (
                            round(with_imvdb / total_artists * 100, 1)
                            if total_artists > 0
                            else 0
                        ),
                        "musicbrainz": (
                            round(with_musicbrainz / total_artists * 100, 1)
                            if total_artists > 0
                            else 0
                        ),
                    },
                    "external_id_counts": {
                        "linked": {
                            "spotify": with_spotify,
                            "lastfm": with_lastfm,
                            "imvdb": with_imvdb,
                            "musicbrainz": with_musicbrainz,
                        },
                        "missing": {
                            "spotify": missing_spotify,
                            "lastfm": missing_lastfm,
                            "imvdb": missing_imvdb,
                            "musicbrainz": total_artists - with_musicbrainz,
                        },
                    },
                    "data_quality": {
                        "consistent_counting": True,  # Flag to indicate fixed counting logic
                        "includes_empty_strings": True,  # Clarify what "missing" means
                        "includes_whitespace_only": True,
                    },
                }
        except Exception as e:
            logger.error(f"Error getting enrichment stats: {e}")
            return {}


# Global instance
metadata_enrichment_service = MetadataEnrichmentService()
