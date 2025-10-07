"""
Enhanced Artist Discovery Service for MVidarr 0.9.7 - Issue #75
Multi-source artist discovery with metadata enrichment and intelligence.
"""

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import requests
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.services.imvdb_service import imvdb_service
from src.services.lastfm_service import LastFmService
from src.services.settings_service import settings
from src.services.spotify_service import SpotifyService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.enhanced_artist_discovery")


class DiscoverySource(Enum):
    """Sources for artist discovery"""

    IMVDB = "imvdb"
    SPOTIFY = "spotify"
    LASTFM = "lastfm"
    WIKIPEDIA = "wikipedia"
    MANUAL = "manual"


class MetadataQuality(Enum):
    """Quality levels for metadata"""

    EXCELLENT = 5
    GOOD = 4
    FAIR = 3
    POOR = 2
    MINIMAL = 1


@dataclass
class ArtistMetadata:
    """Comprehensive artist metadata from multiple sources"""

    name: str
    source: DiscoverySource
    confidence: float  # 0.0 to 1.0
    genres: List[str] = None
    biography: str = ""
    formed_year: int = None
    country: str = ""
    image_url: str = ""
    external_ids: Dict[str, str] = None
    similar_artists: List[str] = None
    popularity_score: float = 0.0
    last_updated: datetime = None
    quality_score: MetadataQuality = MetadataQuality.MINIMAL

    def __post_init__(self):
        if self.genres is None:
            self.genres = []
        if self.external_ids is None:
            self.external_ids = {}
        if self.similar_artists is None:
            self.similar_artists = []
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()


@dataclass
class DuplicateCandidate:
    """Potential duplicate artist candidate"""

    artist_id: int
    candidate_id: int
    similarity_score: float
    matching_factors: List[str]
    confidence: float
    suggested_action: str  # merge, review, ignore


class EnhancedArtistDiscoveryService:
    """Enhanced artist discovery with multi-source integration"""

    def __init__(self):
        self.spotify_service = SpotifyService()
        self.lastfm_service = LastFmService()
        self.discovery_cache = {}
        self.enrichment_cache = {}

        # Discovery configuration
        self.min_confidence_threshold = 0.7
        self.max_results_per_source = 25
        self.cache_duration_hours = 24

    def discover_artists_multi_source(
        self, search_query: str, max_results: int = 50
    ) -> List[ArtistMetadata]:
        """
        Discover artists from multiple sources with intelligent merging

        Args:
            search_query: Artist name or search term
            max_results: Maximum number of results to return

        Returns:
            List of ArtistMetadata objects with enriched information
        """
        logger.info(f"Starting multi-source artist discovery for: {search_query}")

        # Check cache first
        cache_key = f"discovery:{search_query}:{max_results}"
        if cache_key in self.discovery_cache:
            cache_entry = self.discovery_cache[cache_key]
            if datetime.utcnow() - cache_entry["timestamp"] < timedelta(
                hours=self.cache_duration_hours
            ):
                logger.debug(f"Returning cached discovery results for: {search_query}")
                return cache_entry["results"]

        discovered_artists = []

        # 1. IMVDb Discovery (existing integration)
        try:
            imvdb_results = self._discover_from_imvdb(search_query)
            discovered_artists.extend(imvdb_results)
            logger.info(
                f"IMVDb returned {len(imvdb_results)} artists for: {search_query}"
            )
        except Exception as e:
            logger.error(f"Error discovering from IMVDb: {e}")

        # 2. Spotify Discovery
        try:
            spotify_results = self._discover_from_spotify(search_query)
            discovered_artists.extend(spotify_results)
            logger.info(
                f"Spotify returned {len(spotify_results)} artists for: {search_query}"
            )
        except Exception as e:
            logger.error(f"Error discovering from Spotify: {e}")

        # 3. Last.fm Discovery
        try:
            lastfm_results = self._discover_from_lastfm(search_query)
            discovered_artists.extend(lastfm_results)
            logger.info(
                f"Last.fm returned {len(lastfm_results)} artists for: {search_query}"
            )
        except Exception as e:
            logger.error(f"Error discovering from Last.fm: {e}")

        # 4. Wikipedia Discovery (for additional metadata)
        try:
            wikipedia_results = self._discover_from_wikipedia(search_query)
            discovered_artists.extend(wikipedia_results)
            logger.info(
                f"Wikipedia returned {len(wikipedia_results)} artists for: {search_query}"
            )
        except Exception as e:
            logger.error(f"Error discovering from Wikipedia: {e}")

        # 5. Intelligent deduplication and merging
        merged_artists = self._merge_duplicate_discoveries(discovered_artists)

        # 6. Quality scoring and ranking
        ranked_artists = self._rank_and_score_discoveries(merged_artists)

        # 7. Limit results and apply confidence threshold
        filtered_artists = [
            artist
            for artist in ranked_artists
            if artist.confidence >= self.min_confidence_threshold
        ][:max_results]

        # Cache results
        self.discovery_cache[cache_key] = {
            "results": filtered_artists,
            "timestamp": datetime.utcnow(),
        }

        logger.info(
            f"Multi-source discovery completed: {len(filtered_artists)} high-quality results"
        )
        return filtered_artists

    def enrich_artist_metadata(self, artist_id: int) -> bool:
        """
        Enrich existing artist with metadata from multiple sources

        Args:
            artist_id: ID of artist to enrich

        Returns:
            True if enrichment was successful
        """
        try:
            with get_db() as db:
                artist = db.query(Artist).filter(Artist.id == artist_id).first()
                if not artist:
                    logger.warning(f"Artist {artist_id} not found for enrichment")
                    return False

                logger.info(f"Starting metadata enrichment for artist: {artist.name}")

                # Gather metadata from all sources
                enrichment_data = []

                # IMVDb enrichment - DISABLED per user requirements
                # IMVDb should only be used for searching, not as a metadata source
                logger.debug(
                    f"IMVDb enrichment disabled per configuration for artist: {artist.name}"
                )

                # Spotify enrichment
                try:
                    spotify_data = self._enrich_from_spotify(artist.name)
                    if spotify_data:
                        enrichment_data.append(spotify_data)
                except Exception as e:
                    logger.error(f"Spotify enrichment error for {artist.name}: {e}")

                # Last.fm enrichment
                try:
                    lastfm_data = self._enrich_from_lastfm(artist.name)
                    if lastfm_data:
                        enrichment_data.append(lastfm_data)
                except Exception as e:
                    logger.error(f"Last.fm enrichment error for {artist.name}: {e}")

                # Wikipedia enrichment
                try:
                    wikipedia_data = self._enrich_from_wikipedia(artist.name)
                    if wikipedia_data:
                        enrichment_data.append(wikipedia_data)
                except Exception as e:
                    logger.error(f"Wikipedia enrichment error for {artist.name}: {e}")

                # Merge and apply enrichment
                if enrichment_data:
                    merged_metadata = self._merge_enrichment_data(enrichment_data)
                    applied_fields = self._apply_enrichment_to_artist(
                        artist, merged_metadata
                    )

                    db.commit()

                    logger.info(
                        f"Artist {artist.name} enriched with fields: {applied_fields}"
                    )
                    return True
                else:
                    logger.warning(
                        f"No enrichment data found for artist: {artist.name}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error enriching artist {artist_id}: {e}")
            return False

    def detect_duplicate_artists(self, limit: int = 100) -> List[DuplicateCandidate]:
        """
        Detect potential duplicate artists in the library

        Args:
            limit: Maximum number of duplicate pairs to analyze

        Returns:
            List of DuplicateCandidate objects
        """
        logger.info(f"Starting duplicate artist detection (limit: {limit})")

        try:
            with get_db() as db:
                # Get all artists sorted by most recently added
                artists = (
                    db.query(Artist).order_by(desc(Artist.id)).limit(limit * 2).all()
                )

                duplicates = []
                processed_pairs = set()

                for i, artist1 in enumerate(artists):
                    for j, artist2 in enumerate(artists[i + 1 :], i + 1):
                        pair_key = tuple(sorted([artist1.id, artist2.id]))

                        if pair_key in processed_pairs:
                            continue
                        processed_pairs.add(pair_key)

                        similarity = self._calculate_artist_similarity(artist1, artist2)

                        if (
                            similarity.similarity_score >= 0.8
                        ):  # High similarity threshold
                            duplicates.append(similarity)

                        if len(duplicates) >= limit:
                            break

                    if len(duplicates) >= limit:
                        break

                logger.info(f"Detected {len(duplicates)} potential duplicate pairs")
                return duplicates

        except Exception as e:
            logger.error(f"Error detecting duplicate artists: {e}")
            return []

    def get_artist_recommendations(
        self, artist_id: int, limit: int = 20
    ) -> List[ArtistMetadata]:
        """
        Get artist recommendations based on library content and similar artists

        Args:
            artist_id: Base artist for recommendations
            limit: Maximum number of recommendations

        Returns:
            List of recommended ArtistMetadata objects
        """
        try:
            with get_db() as db:
                artist = db.query(Artist).filter(Artist.id == artist_id).first()
                if not artist:
                    return []

                logger.info(f"Generating recommendations for artist: {artist.name}")

                recommendations = []

                # 1. Genre-based recommendations
                if artist.genres:
                    genre_recs = self._get_genre_based_recommendations(
                        artist.genres.split(","), limit // 2
                    )
                    recommendations.extend(genre_recs)

                # 2. Similar artist recommendations from Last.fm
                try:
                    similar_recs = self._get_similar_artist_recommendations(
                        artist.name, limit // 2
                    )
                    recommendations.extend(similar_recs)
                except Exception as e:
                    logger.error(f"Error getting similar artist recommendations: {e}")

                # 3. Collaborative filtering based on library
                try:
                    collab_recs = self._get_collaborative_recommendations(
                        artist_id, limit // 4
                    )
                    recommendations.extend(collab_recs)
                except Exception as e:
                    logger.error(f"Error getting collaborative recommendations: {e}")

                # Remove duplicates and rank
                unique_recommendations = self._deduplicate_recommendations(
                    recommendations
                )
                ranked_recommendations = sorted(
                    unique_recommendations, key=lambda x: x.confidence, reverse=True
                )[:limit]

                logger.info(
                    f"Generated {len(ranked_recommendations)} recommendations for {artist.name}"
                )
                return ranked_recommendations

        except Exception as e:
            logger.error(
                f"Error generating recommendations for artist {artist_id}: {e}"
            )
            return []

    # Private helper methods for different discovery sources

    def _discover_from_imvdb(self, search_query: str) -> List[ArtistMetadata]:
        """Discover artists from IMVDb"""
        try:
            results = imvdb_service.search_artists(
                search_query, self.max_results_per_source
            )

            artist_metadata = []
            for artist_data in results.get("artists", []):
                metadata = ArtistMetadata(
                    name=artist_data.get("name", ""),
                    source=DiscoverySource.IMVDB,
                    confidence=0.9,  # IMVDb is high quality for music videos
                    external_ids={"imvdb_id": str(artist_data.get("id", ""))},
                    image_url=artist_data.get("image_url", ""),
                    quality_score=MetadataQuality.GOOD,
                )
                artist_metadata.append(metadata)

            return artist_metadata

        except Exception as e:
            logger.error(f"IMVDb discovery error: {e}")
            return []

    def _discover_from_spotify(self, search_query: str) -> List[ArtistMetadata]:
        """Discover artists from Spotify"""
        try:
            # Use existing Spotify service
            artists = self.spotify_service.search_artist(
                search_query, limit=self.max_results_per_source
            )

            artist_metadata = []
            for artist in artists.get("artists", {}).get("items", []):
                genres = artist.get("genres", [])

                metadata = ArtistMetadata(
                    name=artist.get("name", ""),
                    source=DiscoverySource.SPOTIFY,
                    confidence=0.8,  # Spotify is reliable but focused on streaming
                    genres=genres,
                    external_ids={"spotify_id": artist.get("id", "")},
                    image_url=(
                        artist.get("images", [{}])[0].get("url", "")
                        if artist.get("images")
                        else ""
                    ),
                    popularity_score=artist.get("popularity", 0) / 100.0,
                    quality_score=(
                        MetadataQuality.GOOD if genres else MetadataQuality.FAIR
                    ),
                )
                artist_metadata.append(metadata)

            return artist_metadata

        except Exception as e:
            logger.error(f"Spotify discovery error: {e}")
            return []

    def _discover_from_lastfm(self, search_query: str) -> List[ArtistMetadata]:
        """Discover artists from Last.fm"""
        try:
            # Use existing Last.fm service - search via artist info
            artist_info = self.lastfm_service.get_artist_info(search_query)
            results = {
                "results": {
                    "artistmatches": {"artist": [artist_info] if artist_info else []}
                }
            }

            artist_metadata = []
            for artist in (
                results.get("results", {}).get("artistmatches", {}).get("artist", [])
            ):
                metadata = ArtistMetadata(
                    name=artist.get("name", ""),
                    source=DiscoverySource.LASTFM,
                    confidence=0.7,  # Last.fm is good for metadata but less reliable for discovery
                    external_ids={"lastfm_mbid": artist.get("mbid", "")},
                    image_url=(
                        artist.get("image", [{}])[-1].get("#text", "")
                        if artist.get("image")
                        else ""
                    ),
                    quality_score=MetadataQuality.FAIR,
                )
                artist_metadata.append(metadata)

            return artist_metadata

        except Exception as e:
            logger.error(f"Last.fm discovery error: {e}")
            return []

    def _discover_from_wikipedia(self, search_query: str) -> List[ArtistMetadata]:
        """Discover artists from Wikipedia"""
        try:
            # Wikipedia API search
            search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
            search_term = search_query.replace(" ", "_")

            response = requests.get(f"{search_url}{search_term}", timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Basic heuristic to determine if this is a music artist page
                extract = data.get("extract", "").lower()
                title = data.get("title", "")

                music_keywords = [
                    "singer",
                    "musician",
                    "band",
                    "artist",
                    "album",
                    "song",
                    "music",
                ]
                is_music_related = any(keyword in extract for keyword in music_keywords)

                if is_music_related:
                    metadata = ArtistMetadata(
                        name=title,
                        source=DiscoverySource.WIKIPEDIA,
                        confidence=0.6,  # Wikipedia requires validation
                        biography=data.get("extract", ""),
                        image_url=(
                            data.get("thumbnail", {}).get("source", "")
                            if data.get("thumbnail")
                            else ""
                        ),
                        external_ids={
                            "wikipedia_url": data.get("content_urls", {})
                            .get("desktop", {})
                            .get("page", "")
                        },
                        quality_score=MetadataQuality.FAIR,
                    )
                    return [metadata]

            return []

        except Exception as e:
            logger.error(f"Wikipedia discovery error: {e}")
            return []

    def _merge_duplicate_discoveries(
        self, discoveries: List[ArtistMetadata]
    ) -> List[ArtistMetadata]:
        """Merge duplicate artist discoveries from different sources"""
        if not discoveries:
            return []

        # Group by similar artist names
        name_groups = {}
        for discovery in discoveries:
            normalized_name = self._normalize_artist_name(discovery.name)
            if normalized_name not in name_groups:
                name_groups[normalized_name] = []
            name_groups[normalized_name].append(discovery)

        merged_results = []
        for group_name, group_discoveries in name_groups.items():
            if len(group_discoveries) == 1:
                merged_results.append(group_discoveries[0])
            else:
                # Merge multiple discoveries of the same artist
                merged_artist = self._merge_artist_metadata(group_discoveries)
                merged_results.append(merged_artist)

        return merged_results

    def _normalize_artist_name(self, name: str) -> str:
        """Normalize artist name for comparison"""
        if not name:
            return ""

        # Convert to lowercase and remove common variations
        normalized = name.lower().strip()

        # Remove common prefixes/suffixes
        prefixes = ["the ", "a "]
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]

        # Remove special characters but keep spaces
        normalized = re.sub(r"[^\w\s]", "", normalized)

        return normalized

    def _merge_artist_metadata(
        self, discoveries: List[ArtistMetadata]
    ) -> ArtistMetadata:
        """Merge multiple discoveries of the same artist"""
        if not discoveries:
            return None

        if len(discoveries) == 1:
            return discoveries[0]

        # Use the discovery with highest confidence as base
        base_discovery = max(discoveries, key=lambda x: x.confidence)

        # Merge data from other sources
        merged = ArtistMetadata(
            name=base_discovery.name,
            source=base_discovery.source,
            confidence=min(
                1.0, sum(d.confidence for d in discoveries) / len(discoveries) * 1.2
            ),
            genres=[],
            biography=base_discovery.biography,
            formed_year=base_discovery.formed_year,
            country=base_discovery.country,
            image_url=base_discovery.image_url,
            external_ids={},
            similar_artists=[],
            popularity_score=max(d.popularity_score for d in discoveries),
            quality_score=max(d.quality_score for d in discoveries),
        )

        # Merge genres from all sources
        all_genres = set()
        for discovery in discoveries:
            if discovery.genres:
                all_genres.update(discovery.genres)
        merged.genres = list(all_genres)

        # Merge external IDs
        for discovery in discoveries:
            if discovery.external_ids:
                merged.external_ids.update(discovery.external_ids)

        # Use best available biography
        for discovery in discoveries:
            if discovery.biography and len(discovery.biography) > len(
                merged.biography or ""
            ):
                merged.biography = discovery.biography

        # Use best available image
        for discovery in discoveries:
            if discovery.image_url and not merged.image_url:
                merged.image_url = discovery.image_url

        return merged

    def _rank_and_score_discoveries(
        self, discoveries: List[ArtistMetadata]
    ) -> List[ArtistMetadata]:
        """Rank and score discoveries based on quality metrics"""
        for discovery in discoveries:
            score = self._calculate_quality_score(discovery)
            discovery.confidence = min(1.0, discovery.confidence * score)

        return sorted(discoveries, key=lambda x: x.confidence, reverse=True)

    def _calculate_quality_score(self, metadata: ArtistMetadata) -> float:
        """Calculate quality score for artist metadata"""
        score = 0.0
        max_score = 10.0

        # Name quality (required)
        if metadata.name and len(metadata.name.strip()) > 0:
            score += 2.0

        # Genre information
        if metadata.genres and len(metadata.genres) > 0:
            score += 2.0

        # Biography
        if metadata.biography and len(metadata.biography) > 50:
            score += 1.5

        # Image
        if metadata.image_url:
            score += 1.0

        # External IDs
        if metadata.external_ids and len(metadata.external_ids) > 0:
            score += 1.5

        # Popularity score
        if metadata.popularity_score > 0.5:
            score += 1.0

        # Additional metadata
        if metadata.formed_year:
            score += 0.5
        if metadata.country:
            score += 0.5

        return score / max_score

    def _calculate_artist_similarity(
        self, artist1: Artist, artist2: Artist
    ) -> DuplicateCandidate:
        """Calculate similarity between two artists"""
        similarity_score = 0.0
        matching_factors = []

        # Name similarity (most important)
        name_sim = self._calculate_name_similarity(artist1.name, artist2.name)
        similarity_score += name_sim * 0.6
        if name_sim > 0.8:
            matching_factors.append("similar_name")

        # Genre similarity
        if artist1.genres and artist2.genres:
            genre_sim = self._calculate_genre_similarity(artist1.genres, artist2.genres)
            similarity_score += genre_sim * 0.2
            if genre_sim > 0.5:
                matching_factors.append("similar_genres")

        # Formed year similarity
        if artist1.formed_year and artist2.formed_year:
            year_diff = abs(artist1.formed_year - artist2.formed_year)
            year_sim = max(0, 1 - year_diff / 10.0)  # Within 10 years is good
            similarity_score += year_sim * 0.1
            if year_sim > 0.8:
                matching_factors.append("similar_year")

        # Country similarity
        if artist1.country and artist2.country:
            country_sim = (
                1.0 if artist1.country.lower() == artist2.country.lower() else 0.0
            )
            similarity_score += country_sim * 0.1
            if country_sim > 0:
                matching_factors.append("same_country")

        # Determine suggested action
        if similarity_score >= 0.9:
            suggested_action = "merge"
        elif similarity_score >= 0.8:
            suggested_action = "review"
        else:
            suggested_action = "ignore"

        return DuplicateCandidate(
            artist_id=artist1.id,
            candidate_id=artist2.id,
            similarity_score=similarity_score,
            matching_factors=matching_factors,
            confidence=similarity_score,
            suggested_action=suggested_action,
        )

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two artist names"""
        if not name1 or not name2:
            return 0.0

        norm1 = self._normalize_artist_name(name1)
        norm2 = self._normalize_artist_name(name2)

        if norm1 == norm2:
            return 1.0

        # Simple character-based similarity
        max_len = max(len(norm1), len(norm2))
        if max_len == 0:
            return 0.0

        # Count matching characters
        matching_chars = sum(c1 == c2 for c1, c2 in zip(norm1, norm2))

        return matching_chars / max_len

    def _calculate_genre_similarity(self, genres1: str, genres2: str) -> float:
        """Calculate similarity between genre strings"""
        if not genres1 or not genres2:
            return 0.0

        set1 = set(g.strip().lower() for g in genres1.split(","))
        set2 = set(g.strip().lower() for g in genres2.split(","))

        if not set1 or not set2:
            return 0.0

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        return intersection / union if union > 0 else 0.0

    # Enrichment helper methods

    def _enrich_from_imvdb(self, artist_name: str) -> Optional[ArtistMetadata]:
        """Enrich artist from IMVDb - DISABLED per user requirements"""
        # IMVDb should only be used for searching, not as a metadata source
        logger.debug(
            f"IMVDb enrichment method disabled per configuration for artist: {artist_name}"
        )
        return None

    def _enrich_from_spotify(self, artist_name: str) -> Optional[ArtistMetadata]:
        """Enrich artist from Spotify"""
        try:
            results = self.spotify_service.search_artist(artist_name, limit=1)
            if results and results.get("artists", {}).get("items"):
                artist = results["artists"]["items"][0]
                return ArtistMetadata(
                    name=artist.get("name", artist_name),
                    source=DiscoverySource.SPOTIFY,
                    confidence=0.8,
                    genres=artist.get("genres", []),
                    external_ids={"spotify_id": artist.get("id", "")},
                    image_url=(
                        artist.get("images", [{}])[0].get("url", "")
                        if artist.get("images")
                        else ""
                    ),
                    popularity_score=artist.get("popularity", 0) / 100.0,
                    quality_score=MetadataQuality.GOOD,
                )
        except Exception as e:
            logger.error(f"Spotify enrichment error: {e}")
        return None

    def _enrich_from_lastfm(self, artist_name: str) -> Optional[ArtistMetadata]:
        """Enrich artist from Last.fm"""
        try:
            artist_info = self.lastfm_service.get_artist_info(artist_name)
            if artist_info:
                return ArtistMetadata(
                    name=artist_info.get("name", artist_name),
                    source=DiscoverySource.LASTFM,
                    confidence=0.7,
                    biography=artist_info.get("bio", {}).get("summary", ""),
                    external_ids={"lastfm_mbid": artist_info.get("mbid", "")},
                    image_url=(
                        artist_info.get("image", [{}])[-1].get("#text", "")
                        if artist_info.get("image")
                        else ""
                    ),
                    similar_artists=[
                        a.get("name", "")
                        for a in artist_info.get("similar", {}).get("artist", [])
                    ],
                    quality_score=(
                        MetadataQuality.GOOD
                        if artist_info.get("bio")
                        else MetadataQuality.FAIR
                    ),
                )
        except Exception as e:
            logger.error(f"Last.fm enrichment error: {e}")
        return None

    def _enrich_from_wikipedia(self, artist_name: str) -> Optional[ArtistMetadata]:
        """Enrich artist from Wikipedia"""
        try:
            search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
            search_term = artist_name.replace(" ", "_")

            response = requests.get(f"{search_url}{search_term}", timeout=10)

            if response.status_code == 200:
                data = response.json()
                extract = data.get("extract", "").lower()

                # Verify it's a music artist page
                music_keywords = [
                    "singer",
                    "musician",
                    "band",
                    "artist",
                    "album",
                    "song",
                ]
                if any(keyword in extract for keyword in music_keywords):
                    return ArtistMetadata(
                        name=data.get("title", artist_name),
                        source=DiscoverySource.WIKIPEDIA,
                        confidence=0.6,
                        biography=data.get("extract", ""),
                        image_url=(
                            data.get("thumbnail", {}).get("source", "")
                            if data.get("thumbnail")
                            else ""
                        ),
                        external_ids={
                            "wikipedia_url": data.get("content_urls", {})
                            .get("desktop", {})
                            .get("page", "")
                        },
                        quality_score=MetadataQuality.FAIR,
                    )
        except Exception as e:
            logger.error(f"Wikipedia enrichment error: {e}")
        return None

    def _merge_enrichment_data(
        self, enrichment_data: List[ArtistMetadata]
    ) -> ArtistMetadata:
        """Merge enrichment data from multiple sources"""
        if not enrichment_data:
            return None

        if len(enrichment_data) == 1:
            return enrichment_data[0]

        # Use highest quality source as base
        base_data = max(enrichment_data, key=lambda x: x.quality_score.value)

        merged = ArtistMetadata(
            name=base_data.name,
            source=base_data.source,
            confidence=min(
                1.0, sum(d.confidence for d in enrichment_data) / len(enrichment_data)
            ),
            genres=[],
            biography=base_data.biography,
            external_ids={},
            similar_artists=[],
            quality_score=base_data.quality_score,
        )

        # Merge all data
        for data in enrichment_data:
            # Genres
            if data.genres:
                merged.genres.extend(data.genres)

            # External IDs
            if data.external_ids:
                merged.external_ids.update(data.external_ids)

            # Biography (use longest)
            if data.biography and len(data.biography) > len(merged.biography or ""):
                merged.biography = data.biography

            # Image (use first available)
            if data.image_url and not merged.image_url:
                merged.image_url = data.image_url

            # Similar artists
            if data.similar_artists:
                merged.similar_artists.extend(data.similar_artists)

        # Clean up duplicates
        merged.genres = list(set(merged.genres))
        merged.similar_artists = list(set(merged.similar_artists))

        return merged

    def _apply_enrichment_to_artist(
        self, artist: Artist, metadata: ArtistMetadata
    ) -> List[str]:
        """Apply enrichment metadata to artist object"""
        applied_fields = []

        # Genres
        if metadata.genres and not artist.genres:
            artist.genres = ", ".join(metadata.genres[:5])  # Limit to 5 genres
            applied_fields.append("genres")

        # Biography
        if metadata.biography and not artist.biography:
            artist.biography = metadata.biography[:1000]  # Limit length
            applied_fields.append("biography")

        # Country (extract from biography or other sources)
        if not artist.country and metadata.biography:
            country = self._extract_country_from_text(metadata.biography)
            if country:
                artist.country = country
                applied_fields.append("country")

        # Image URL (if we have a field for it)
        if metadata.image_url and hasattr(artist, "image_url") and not artist.image_url:
            artist.image_url = metadata.image_url
            applied_fields.append("image_url")

        return applied_fields

    def _extract_country_from_text(self, text: str) -> Optional[str]:
        """Extract country from biography text"""
        if not text:
            return None

        # Simple country extraction - could be enhanced with NLP
        countries = [
            "United States",
            "United Kingdom",
            "Canada",
            "Australia",
            "Germany",
            "France",
            "Italy",
            "Spain",
            "Sweden",
            "Norway",
            "Denmark",
            "Japan",
            "South Korea",
            "Brazil",
            "Mexico",
            "Argentina",
            "India",
            "Russia",
        ]

        text_lower = text.lower()
        for country in countries:
            if country.lower() in text_lower:
                return country

        return None

    def _get_genre_based_recommendations(
        self, genres: List[str], limit: int
    ) -> List[ArtistMetadata]:
        """Get recommendations based on genres"""
        if not genres:
            return []

        recommendations = []

        # This would ideally query external APIs for genre-based artist recommendations
        # For now, return a placeholder implementation
        try:
            for genre in genres[:3]:  # Limit to first 3 genres
                spotify_recs = self._get_spotify_genre_recommendations(
                    genre.strip(), limit // len(genres)
                )
                recommendations.extend(spotify_recs)
        except Exception as e:
            logger.error(f"Error getting genre recommendations: {e}")

        return recommendations

    def _get_spotify_genre_recommendations(
        self, genre: str, limit: int
    ) -> List[ArtistMetadata]:
        """Get Spotify recommendations for a genre"""
        try:
            # Use Spotify's recommendation API (if available in spotify_service)
            # This is a placeholder - would need to implement in spotify_service
            return []
        except Exception as e:
            logger.error(f"Spotify genre recommendation error: {e}")
            return []

    def _get_similar_artist_recommendations(
        self, artist_name: str, limit: int
    ) -> List[ArtistMetadata]:
        """Get similar artist recommendations from Last.fm"""
        try:
            # Direct Last.fm API call since the service doesn't have similar artists method
            if (
                not hasattr(self.lastfm_service, "api_key")
                or not self.lastfm_service.api_key
            ):
                logger.warning("Last.fm API key not configured")
                return []

            params = {
                "method": "artist.getSimilar",
                "artist": artist_name,
                "api_key": self.lastfm_service.api_key,
                "format": "json",
                "limit": limit,
            }

            response = requests.get(
                self.lastfm_service.base_url, params=params, timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                recommendations = []

                for similar_artist in data.get("similarartists", {}).get("artist", []):
                    metadata = ArtistMetadata(
                        name=similar_artist.get("name", ""),
                        source=DiscoverySource.LASTFM,
                        confidence=float(similar_artist.get("match", 0.5)),
                        external_ids={"lastfm_mbid": similar_artist.get("mbid", "")},
                        image_url=(
                            similar_artist.get("image", [{}])[-1].get("#text", "")
                            if similar_artist.get("image")
                            else ""
                        ),
                        quality_score=MetadataQuality.FAIR,
                    )
                    recommendations.append(metadata)

                return recommendations
            else:
                logger.warning(
                    f"Last.fm similar artists request failed: {response.status_code}"
                )
                return []

        except Exception as e:
            logger.error(f"Similar artist recommendation error: {e}")
            return []

    def _get_collaborative_recommendations(
        self, artist_id: int, limit: int
    ) -> List[ArtistMetadata]:
        """Get collaborative filtering recommendations based on library"""
        try:
            with get_db() as db:
                # Find artists that appear in the same playlists or have similar video patterns
                # This is a simplified implementation
                artist = db.query(Artist).filter(Artist.id == artist_id).first()
                if not artist or not artist.genres:
                    return []

                # Find other artists with similar genres
                similar_artists = (
                    db.query(Artist)
                    .filter(
                        and_(
                            Artist.id != artist_id,
                            Artist.genres.ilike(
                                f'%{artist.genres.split(",")[0].strip()}%'
                            ),
                        )
                    )
                    .limit(limit)
                    .all()
                )

                recommendations = []
                for similar_artist in similar_artists:
                    metadata = ArtistMetadata(
                        name=similar_artist.name,
                        source=DiscoverySource.MANUAL,  # From existing library
                        confidence=0.5,
                        genres=(
                            similar_artist.genres.split(",")
                            if similar_artist.genres
                            else []
                        ),
                        quality_score=MetadataQuality.FAIR,
                    )
                    recommendations.append(metadata)

                return recommendations

        except Exception as e:
            logger.error(f"Collaborative recommendation error: {e}")
            return []

    def _deduplicate_recommendations(
        self, recommendations: List[ArtistMetadata]
    ) -> List[ArtistMetadata]:
        """Remove duplicate recommendations"""
        seen_names = set()
        unique_recommendations = []

        for recommendation in recommendations:
            normalized_name = self._normalize_artist_name(recommendation.name)
            if normalized_name not in seen_names:
                seen_names.add(normalized_name)
                unique_recommendations.append(recommendation)

        return unique_recommendations


# Initialize service instance
enhanced_artist_discovery_service = EnhancedArtistDiscoveryService()


async def get_enhanced_artist_discovery() -> EnhancedArtistDiscoveryService:
    """
    Get the enhanced artist discovery service instance

    Returns:
        EnhancedArtistDiscoveryService: Configured service instance
    """
    return enhanced_artist_discovery_service
