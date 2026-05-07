"""
Duplicate Artist Detection and Merging Service for MVidarr 0.9.7 - Issue #75
Intelligent detection and merging of duplicate artists across different sources.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from src.database.connection import get_db
from src.database.models import Artist, Download, Video
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.duplicate_detection")


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate artist match"""

    artist1_id: int
    artist2_id: int
    artist1_name: str
    artist2_name: str
    similarity_score: float
    match_confidence: float
    match_reasons: List[str] = field(default_factory=list)
    external_id_matches: Dict[str, bool] = field(default_factory=dict)
    metadata_overlap: float = 0.0
    recommended_action: str = "review"  # auto_merge, review, ignore


@dataclass
class MergeResult:
    """Result of merging duplicate artists"""

    primary_artist_id: int
    merged_artist_id: int
    success: bool
    videos_moved: int = 0
    downloads_moved: int = 0
    metadata_merged: bool = False
    errors: List[str] = field(default_factory=list)


class DuplicateDetectionService:
    """Service for detecting and merging duplicate artists"""

    def __init__(self):
        # Similarity thresholds
        self.high_confidence_threshold = 0.9
        self.medium_confidence_threshold = 0.7
        self.low_confidence_threshold = 0.5

        # Auto-merge thresholds
        self.auto_merge_threshold = 0.95
        self.external_id_match_weight = 0.4
        self.name_similarity_weight = 0.4
        self.metadata_overlap_weight = 0.2

        # Name normalization patterns
        self.normalize_patterns = [
            (r"\bthe\b", ""),  # Remove "the"
            (r"\band\b", "&"),  # Convert "and" to "&"
            (r"[^\w\s&]", ""),  # Remove punctuation except &
            (r"\s+", " "),  # Normalize whitespace
        ]

    def find_duplicate_candidates(self, limit: int = 100) -> List[DuplicateMatch]:
        """Find potential duplicate artists"""
        try:
            with get_db() as session:
                # Get all artists for comparison
                artists = (
                    session.query(Artist).order_by(Artist.id).limit(limit * 2).all()
                )

                duplicates = []
                processed_pairs = set()

                for i, artist1 in enumerate(artists):
                    for j, artist2 in enumerate(artists[i + 1 :], i + 1):
                        pair_key = tuple(sorted([artist1.id, artist2.id]))

                        if pair_key in processed_pairs:
                            continue

                        processed_pairs.add(pair_key)

                        # Calculate similarity
                        match = self._calculate_similarity(artist1, artist2)

                        if match.match_confidence >= self.low_confidence_threshold:
                            duplicates.append(match)

                # Sort by confidence score
                duplicates.sort(key=lambda x: x.match_confidence, reverse=True)

                return duplicates[:limit]

        except Exception as e:
            logger.error(f"Error finding duplicate candidates: {e}")
            return []

    def _calculate_similarity(self, artist1: Artist, artist2: Artist) -> DuplicateMatch:
        """Calculate similarity between two artists"""
        match = DuplicateMatch(
            artist1_id=artist1.id,
            artist2_id=artist2.id,
            artist1_name=artist1.name,
            artist2_name=artist2.name,
            similarity_score=0.0,
            match_confidence=0.0,
        )

        # Calculate name similarity
        name_sim = self._calculate_name_similarity(artist1.name, artist2.name)
        match.similarity_score = name_sim

        # Check external ID matches
        external_matches = self._check_external_id_matches(artist1, artist2)
        match.external_id_matches = external_matches

        # Calculate metadata overlap
        metadata_overlap = self._calculate_metadata_overlap(artist1, artist2)
        match.metadata_overlap = metadata_overlap

        # Calculate overall confidence
        confidence_score = (
            name_sim * self.name_similarity_weight
            + self._get_external_id_score(external_matches)
            * self.external_id_match_weight
            + metadata_overlap * self.metadata_overlap_weight
        )

        match.match_confidence = confidence_score

        # Determine match reasons and recommendation
        self._analyze_match_reasons(match, artist1, artist2)

        return match

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between artist names with normalization"""
        # Normalize names
        norm1 = self._normalize_artist_name(name1)
        norm2 = self._normalize_artist_name(name2)

        # Exact match after normalization
        if norm1 == norm2:
            return 1.0

        # Check if one is substring of the other
        if norm1 in norm2 or norm2 in norm1:
            return 0.9

        # Use sequence matcher for fuzzy matching
        similarity = SequenceMatcher(None, norm1.lower(), norm2.lower()).ratio()

        # Check for common variations
        variation_bonus = self._check_name_variations(norm1, norm2)

        return min(1.0, similarity + variation_bonus)

    def _normalize_artist_name(self, name: str) -> str:
        """Normalize artist name for comparison"""
        if not name:
            return ""

        # Unicode normalization
        normalized = unicodedata.normalize("NFKD", name)

        # Apply normalization patterns
        for pattern, replacement in self.normalize_patterns:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        return normalized.strip().lower()

    def _check_name_variations(self, name1: str, name2: str) -> float:
        """Check for common name variations"""
        bonus = 0.0

        # Check for abbreviations (e.g., "Dr." vs "Doctor")
        abbreviations = {
            "dr": "doctor",
            "st": "saint",
            "mt": "mount",
            "ft": "featuring",
            "&": "and",
        }

        words1 = set(name1.split())
        words2 = set(name2.split())

        for abbr, full in abbreviations.items():
            if (abbr in words1 and full in words2) or (
                full in words1 and abbr in words2
            ):
                bonus += 0.1

        return min(bonus, 0.3)  # Cap bonus at 0.3

    def _check_external_id_matches(
        self, artist1: Artist, artist2: Artist
    ) -> Dict[str, bool]:
        """Check if external IDs match between artists"""
        matches = {}

        # Spotify ID match
        if artist1.spotify_id and artist2.spotify_id:
            matches["spotify"] = artist1.spotify_id == artist2.spotify_id

        # Last.fm name match
        if artist1.lastfm_name and artist2.lastfm_name:
            matches["lastfm"] = self._normalize_artist_name(
                artist1.lastfm_name
            ) == self._normalize_artist_name(artist2.lastfm_name)

        # IMVDb ID match
        if artist1.imvdb_id and artist2.imvdb_id:
            matches["imvdb"] = artist1.imvdb_id == artist2.imvdb_id

        return matches

    def _get_external_id_score(self, external_matches: Dict[str, bool]) -> float:
        """Calculate score based on external ID matches"""
        if not external_matches:
            return 0.0

        # If any external ID matches, it's very likely the same artist
        if any(external_matches.values()):
            return 1.0

        # If IDs exist but don't match, it's likely different artists
        if any(match is False for match in external_matches.values()):
            return 0.0

        return 0.5  # No conclusive external ID information

    def _calculate_metadata_overlap(self, artist1: Artist, artist2: Artist) -> float:
        """Calculate metadata overlap between artists"""
        overlap_score = 0.0
        total_checks = 0

        # Genre overlap
        if artist1.genres and artist2.genres:
            genres1 = set(g.strip().lower() for g in artist1.genres.split(","))
            genres2 = set(g.strip().lower() for g in artist2.genres.split(","))

            if genres1 and genres2:
                intersection = len(genres1.intersection(genres2))
                union = len(genres1.union(genres2))
                overlap_score += intersection / union if union > 0 else 0
                total_checks += 1

        # Check enriched metadata if available
        meta1 = (
            artist1.imvdb_metadata if isinstance(artist1.imvdb_metadata, dict) else {}
        )
        meta2 = (
            artist2.imvdb_metadata if isinstance(artist2.imvdb_metadata, dict) else {}
        )

        if meta1 and meta2:
            # Related artists overlap
            related1 = set(meta1.get("related_artists", []))
            related2 = set(meta2.get("related_artists", []))

            if related1 and related2:
                intersection = len(related1.intersection(related2))
                union = len(related1.union(related2))
                overlap_score += intersection / union if union > 0 else 0
                total_checks += 1

        return overlap_score / total_checks if total_checks > 0 else 0.0

    def _analyze_match_reasons(
        self, match: DuplicateMatch, artist1: Artist, artist2: Artist
    ):
        """Analyze and add reasons for the match"""
        reasons = []

        # High name similarity
        if match.similarity_score >= 0.9:
            reasons.append("Very high name similarity")
        elif match.similarity_score >= 0.7:
            reasons.append("High name similarity")

        # External ID matches
        for source, is_match in match.external_id_matches.items():
            if is_match:
                reasons.append(f"Matching {source} ID")

        # Metadata overlap
        if match.metadata_overlap > 0.5:
            reasons.append("Significant metadata overlap")

        # Same source
        if artist1.source == artist2.source and artist1.source:
            reasons.append(f"Both from {artist1.source}")

        match.match_reasons = reasons

        # Determine recommended action
        if match.match_confidence >= self.auto_merge_threshold:
            match.recommended_action = "auto_merge"
        elif match.match_confidence >= self.medium_confidence_threshold:
            match.recommended_action = "review"
        else:
            match.recommended_action = "ignore"

    def merge_duplicate_artists(
        self, primary_artist_id: int, duplicate_artist_id: int, auto_merge: bool = False
    ) -> MergeResult:
        """Merge duplicate artist into primary artist"""
        try:
            with get_db() as session:
                primary_artist = (
                    session.query(Artist).filter(Artist.id == primary_artist_id).first()
                )
                duplicate_artist = (
                    session.query(Artist)
                    .filter(Artist.id == duplicate_artist_id)
                    .first()
                )

                if not primary_artist or not duplicate_artist:
                    return MergeResult(
                        primary_artist_id=primary_artist_id,
                        merged_artist_id=duplicate_artist_id,
                        success=False,
                        errors=["One or both artists not found"],
                    )

                if primary_artist_id == duplicate_artist_id:
                    return MergeResult(
                        primary_artist_id=primary_artist_id,
                        merged_artist_id=duplicate_artist_id,
                        success=False,
                        errors=["Cannot merge artist with itself"],
                    )

                result = MergeResult(
                    primary_artist_id=primary_artist_id,
                    merged_artist_id=duplicate_artist_id,
                    success=False,
                )

                # Verify this is a good merge candidate if auto_merge is False
                if not auto_merge:
                    match = self._calculate_similarity(primary_artist, duplicate_artist)
                    if match.match_confidence < self.medium_confidence_threshold:
                        result.errors.append(
                            f"Low confidence match: {match.match_confidence:.2f}"
                        )
                        return result

                # Move videos from duplicate to primary
                videos_to_move = (
                    session.query(Video)
                    .filter(Video.artist_id == duplicate_artist_id)
                    .all()
                )
                for video in videos_to_move:
                    # Check if primary artist already has this video
                    existing_video = (
                        session.query(Video)
                        .filter(
                            and_(
                                Video.artist_id == primary_artist_id,
                                or_(
                                    Video.imvdb_id == video.imvdb_id,
                                    and_(
                                        Video.title == video.title,
                                        Video.year == video.year,
                                    ),
                                ),
                            )
                        )
                        .first()
                    )

                    if existing_video:
                        # Remove duplicate video
                        session.delete(video)
                    else:
                        # Move video to primary artist
                        video.artist_id = primary_artist_id
                        result.videos_moved += 1

                # Move downloads from duplicate to primary
                downloads_to_move = (
                    session.query(Download)
                    .filter(Download.artist_id == duplicate_artist_id)
                    .all()
                )
                for download in downloads_to_move:
                    download.artist_id = primary_artist_id
                    result.downloads_moved += 1

                # Merge metadata
                result.metadata_merged = self._merge_artist_metadata(
                    session, primary_artist, duplicate_artist
                )

                # Delete the duplicate artist
                session.delete(duplicate_artist)

                # Commit changes
                session.commit()

                result.success = True
                logger.info(
                    f"Successfully merged artist {duplicate_artist_id} into {primary_artist_id}"
                )

                return result

        except Exception as e:
            logger.error(
                f"Error merging artists {duplicate_artist_id} -> {primary_artist_id}: {e}"
            )
            return MergeResult(
                primary_artist_id=primary_artist_id,
                merged_artist_id=duplicate_artist_id,
                success=False,
                errors=[str(e)],
            )

    def _merge_artist_metadata(
        self, session: Session, primary_artist: Artist, duplicate_artist: Artist
    ) -> bool:
        """Merge metadata from duplicate artist into primary artist"""
        try:
            updated = False

            # Merge external IDs (keep non-null values)
            if not primary_artist.spotify_id and duplicate_artist.spotify_id:
                primary_artist.spotify_id = duplicate_artist.spotify_id
                updated = True

            if not primary_artist.lastfm_name and duplicate_artist.lastfm_name:
                primary_artist.lastfm_name = duplicate_artist.lastfm_name
                updated = True

            if not primary_artist.imvdb_id and duplicate_artist.imvdb_id:
                primary_artist.imvdb_id = duplicate_artist.imvdb_id
                updated = True

            # Merge genres
            if duplicate_artist.genres and duplicate_artist.genres.strip():
                if not primary_artist.genres:
                    primary_artist.genres = duplicate_artist.genres
                    updated = True
                else:
                    # Merge genre lists
                    primary_genres = set(
                        g.strip() for g in primary_artist.genres.split(",")
                    )
                    duplicate_genres = set(
                        g.strip() for g in duplicate_artist.genres.split(",")
                    )

                    merged_genres = primary_genres.union(duplicate_genres)
                    primary_artist.genres = ", ".join(sorted(merged_genres))
                    updated = True

            # Merge enriched metadata
            primary_meta = (
                primary_artist.imvdb_metadata
                if isinstance(primary_artist.imvdb_metadata, dict)
                else {}
            )
            duplicate_meta = (
                duplicate_artist.imvdb_metadata
                if isinstance(duplicate_artist.imvdb_metadata, dict)
                else {}
            )

            if duplicate_meta:
                # Merge metadata dictionaries
                for key, value in duplicate_meta.items():
                    if key not in primary_meta or not primary_meta[key]:
                        primary_meta[key] = value
                        updated = True

                primary_artist.imvdb_metadata = primary_meta

            # Update timestamp
            if updated:
                primary_artist.updated_at = datetime.now()

            return updated

        except Exception as e:
            logger.error(f"Error merging metadata: {e}")
            return False

    def get_duplicate_stats(self) -> Dict:
        """Get statistics about potential duplicates"""
        try:
            candidates = self.find_duplicate_candidates(limit=1000)

            high_confidence = [
                c
                for c in candidates
                if c.match_confidence >= self.high_confidence_threshold
            ]
            medium_confidence = [
                c
                for c in candidates
                if self.medium_confidence_threshold
                <= c.match_confidence
                < self.high_confidence_threshold
            ]
            low_confidence = [
                c
                for c in candidates
                if self.low_confidence_threshold
                <= c.match_confidence
                < self.medium_confidence_threshold
            ]

            auto_merge_candidates = [
                c for c in candidates if c.recommended_action == "auto_merge"
            ]

            return {
                "total_candidates": len(candidates),
                "high_confidence": len(high_confidence),
                "medium_confidence": len(medium_confidence),
                "low_confidence": len(low_confidence),
                "auto_merge_candidates": len(auto_merge_candidates),
                "confidence_distribution": {
                    "high": (
                        round(len(high_confidence) / len(candidates) * 100, 1)
                        if candidates
                        else 0
                    ),
                    "medium": (
                        round(len(medium_confidence) / len(candidates) * 100, 1)
                        if candidates
                        else 0
                    ),
                    "low": (
                        round(len(low_confidence) / len(candidates) * 100, 1)
                        if candidates
                        else 0
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Error getting duplicate stats: {e}")
            return {"error": str(e)}

    def auto_merge_high_confidence_duplicates(
        self, limit: int = 10
    ) -> List[MergeResult]:
        """Automatically merge high-confidence duplicate pairs"""
        try:
            candidates = self.find_duplicate_candidates(limit=100)
            auto_merge_candidates = [
                c for c in candidates if c.recommended_action == "auto_merge"
            ][:limit]

            results = []

            for candidate in auto_merge_candidates:
                # Use the artist with more videos as primary
                with get_db() as session:
                    artist1_videos = (
                        session.query(Video)
                        .filter(Video.artist_id == candidate.artist1_id)
                        .count()
                    )
                    artist2_videos = (
                        session.query(Video)
                        .filter(Video.artist_id == candidate.artist2_id)
                        .count()
                    )

                    if artist1_videos >= artist2_videos:
                        primary_id = candidate.artist1_id
                        duplicate_id = candidate.artist2_id
                    else:
                        primary_id = candidate.artist2_id
                        duplicate_id = candidate.artist1_id

                    result = self.merge_duplicate_artists(
                        primary_id, duplicate_id, auto_merge=True
                    )
                    results.append(result)

                    if result.success:
                        logger.info(
                            f"Auto-merged duplicate: {duplicate_id} -> {primary_id}"
                        )

            return results

        except Exception as e:
            logger.error(f"Error in auto-merge process: {e}")
            return []


# Global instance
duplicate_detection_service = DuplicateDetectionService()
