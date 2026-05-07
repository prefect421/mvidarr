"""
Enhanced Metadata Enrichment Service for MVidarr - Refactored
Multi-source artist discovery and metadata aggregation system with intelligent conflict resolution

Refactored from monolithic 3,015-line file into modular architecture:
- metadata_models: Data classes and helper functions
- metadata_source_fetchers: API integrations for external sources
- metadata_aggregators: Metadata aggregation and confidence calculation
- metadata_parsers: Parsing utilities for extracting structured data
- metadata_artist_enricher: Artist enrichment logic
- metadata_video_enricher: Video enrichment logic
- metadata_enrichment_service: Main service aggregator (this file)

Original file: 3,015 lines with 34 methods
Refactored into: 7 specialized modules for better maintainability
"""

from typing import Dict

from sqlalchemy import or_

from src.database.connection import get_db
from src.database.models import Artist
from src.services.allmusic_service import allmusic_service
from src.services.imvdb_service import imvdb_service
from src.services.lastfm_service import lastfm_service

# Import refactored modules
from src.services.metadata_artist_enricher import (
    _calculate_name_similarity,
    _is_artist_match,
    _is_metadata_fresh,
    enrich_artist_metadata,
    enrich_multiple_artists,
)
from src.services.metadata_models import ArtistMetadata, EnrichmentResult
from src.services.metadata_source_fetchers import gather_all_sources_metadata
from src.services.metadata_video_enricher import enrich_video_metadata
from src.services.musicbrainz_service import musicbrainz_service
from src.services.settings_service import settings
from src.services.spotify_service import spotify_service
from src.services.thumbnail_service import ThumbnailService
from src.services.wikipedia_service import WikipediaService
from src.services.youtube_search_service import YouTubeSearchService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_enrichment")


class MetadataEnrichmentService:
    """Service for intelligent multi-source metadata enrichment"""

    def __init__(self):
        # Service integrations
        self.spotify = spotify_service
        self.lastfm = lastfm_service
        self.imvdb = imvdb_service
        self.musicbrainz = musicbrainz_service
        self.allmusic = allmusic_service
        self.wikipedia = WikipediaService()
        self.thumbnail_service = ThumbnailService()
        self.youtube_search = YouTubeSearchService()

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

    # ============================================================================
    # ARTIST ENRICHMENT METHODS (delegated to metadata_artist_enricher module)
    # ============================================================================

    async def enrich_artist_metadata(
        self,
        artist_id: int,
        force_refresh: bool = False,
        app_context=None,
        progress_callback=None,
        session=None,
    ) -> EnrichmentResult:
        """Enrich artist metadata from multiple sources"""
        return await enrich_artist_metadata(
            self, artist_id, force_refresh, app_context, progress_callback, session
        )

    async def enrich_multiple_artists(
        self, artist_ids: list, force_refresh: bool = False
    ) -> Dict:
        """Enrich multiple artists in batch"""
        return await enrich_multiple_artists(self, artist_ids, force_refresh)

    # Helper methods used by artist enricher
    def _is_metadata_fresh(self, artist: Artist) -> bool:
        """Check if artist metadata is fresh"""
        return _is_metadata_fresh(self, artist)

    def _is_artist_match(self, name1: str, name2: str) -> bool:
        """Check if two artist names match"""
        return _is_artist_match(name1, name2)

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity score between two names"""
        return _calculate_name_similarity(name1, name2)

    # ============================================================================
    # VIDEO ENRICHMENT METHODS (delegated to metadata_video_enricher module)
    # ============================================================================

    async def enrich_video_metadata(
        self, video_id: int, force_refresh: bool = False
    ) -> EnrichmentResult:
        """Enrich video metadata from multiple sources"""
        return await enrich_video_metadata(video_id, self.youtube_search, force_refresh)

    # ============================================================================
    # SOURCE FETCHING METHODS (delegated to metadata_source_fetchers module)
    # ============================================================================

    async def _gather_all_sources_metadata(
        self, artist_data: Dict, progress_callback=None
    ) -> Dict[str, ArtistMetadata]:
        """Gather metadata from all available sources"""
        return await gather_all_sources_metadata(self, artist_data, progress_callback)

    # ============================================================================
    # STATISTICS AND REPORTING
    # ============================================================================

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
