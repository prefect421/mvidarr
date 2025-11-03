"""
Artist Identification Service for MVidarr

This service attempts to identify the correct artist for songs currently assigned to "Unknown Artist"
by using song titles and various matching algorithms.
"""

import difflib
import re
from typing import Dict, List

from src.database.models import Artist, Video
from src.services.imvdb_service import imvdb_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.artist_identification")


class ArtistIdentificationService:
    """Service for identifying artists based on song titles"""

    def __init__(self):
        self.imvdb_service = imvdb_service
        self.confidence_threshold = 0.7  # Minimum confidence for automatic assignment

    def identify_artist_from_title(self, song_title: str) -> List[Dict]:
        """
        Identify possible artists for a given song title

        Args:
            song_title: The song title to search for

        Returns:
            List of possible artist matches with confidence scores
        """
        candidates = []

        # Method 1: IMVDb search
        imvdb_candidates = self._search_imvdb_by_title(song_title)
        candidates.extend(imvdb_candidates)

        # Method 2: Parse title for artist clues
        parsed_candidates = self._parse_title_for_artist_clues(song_title)
        candidates.extend(parsed_candidates)

        # Method 3: Search existing artists in database
        db_candidates = self._search_existing_artists(song_title)
        candidates.extend(db_candidates)

        # Deduplicate and score candidates
        final_candidates = self._deduplicate_and_score(candidates, song_title)

        # Sort by confidence score (highest first)
        final_candidates.sort(key=lambda x: x["confidence"], reverse=True)

        return final_candidates[:5]  # Return top 5 candidates

    def _search_imvdb_by_title(self, song_title: str) -> List[Dict]:
        """Search IMVDb for songs with this title"""
        candidates = []

        try:
            # Check if IMVDb is configured
            if not self.imvdb_service.api_key:
                logger.debug("IMVDb API key not configured, skipping IMVDb search")
                return candidates

            # Search for videos with this title
            videos = self.imvdb_service.search_videos("", song_title)

            if not videos:
                logger.debug(f"No IMVDb results for '{song_title}'")
                return candidates

            for video in videos:
                metadata = self.imvdb_service.extract_metadata(video)

                if metadata["artist_name"] and metadata["title"]:
                    # Calculate title similarity
                    title_similarity = self._calculate_similarity(
                        song_title.lower(), metadata["title"].lower()
                    )

                    if title_similarity > 0.5:  # Minimum similarity threshold
                        candidates.append(
                            {
                                "artist_name": metadata["artist_name"],
                                "source": "imvdb",
                                "confidence": title_similarity
                                * 0.9,  # Slightly reduce for API uncertainty
                                "metadata": metadata,
                                "match_reason": f"IMVDb title match: {metadata['title']}",
                            }
                        )

        except Exception as e:
            logger.warning(f"IMVDb search failed for '{song_title}': {e}")

        return candidates

    def _parse_title_for_artist_clues(self, song_title: str) -> List[Dict]:
        """Parse song title for embedded artist information"""
        candidates = []

        # Common patterns where artist might be embedded
        patterns = [
            r"^(.+?)\s*-\s*(.+)$",  # Artist - Song
            r"^(.+?)\s*:\s*(.+)$",  # Artist : Song
            r"^(.+?)\s*\|\s*(.+)$",  # Artist | Song
            r"^(.+?)\s*by\s+(.+)$",  # Song by Artist
            r"^(.+?)\s*\((.+?)\)$",  # Song (Artist)
            r"^(.+?)\s*\[(.+?)\]$",  # Song [Artist]
            r"^(.+?)\s*feat\.?\s+(.+)$",  # Song feat Artist
            r"^(.+?)\s*featuring\s+(.+)$",  # Song featuring Artist
            r"^(.+?)\s*ft\.?\s+(.+)$",  # Song ft Artist
        ]

        for pattern in patterns:
            match = re.search(pattern, song_title, re.IGNORECASE)
            if match:
                part1, part2 = match.groups()

                # Determine which part is likely the artist
                if "by" in pattern:
                    # "Song by Artist" pattern
                    potential_artist = part2.strip()
                    confidence = 0.8
                elif any(word in pattern for word in ["feat", "featuring", "ft"]):
                    # Featuring patterns - main artist is usually first
                    potential_artist = part1.strip()
                    confidence = 0.6
                elif "(" in pattern or "[" in pattern:
                    # Song (Artist) or Song [Artist] - artist is in brackets
                    potential_artist = part2.strip()
                    confidence = 0.7
                else:
                    # Artist - Song patterns
                    potential_artist = part1.strip()
                    confidence = 0.8

                # Validate potential artist name
                if self._is_valid_artist_name(potential_artist):
                    candidates.append(
                        {
                            "artist_name": potential_artist,
                            "source": "title_parsing",
                            "confidence": confidence,
                            "metadata": {},
                            "match_reason": f"Parsed from title pattern: {pattern}",
                        }
                    )

        return candidates

    def _search_existing_artists(self, song_title: str) -> List[Dict]:
        """Search existing artists in database for potential matches"""
        candidates = []

        try:
            from src.database.connection import get_db

            with get_db() as session:
                # Get all artists except "Unknown Artist"
                artists = (
                    session.query(Artist).filter(Artist.name != "Unknown Artist").all()
                )

                for artist in artists:
                    # Check if any of the artist's videos have similar titles
                    for video in artist.videos:
                        similarity = self._calculate_similarity(
                            song_title.lower(), video.title.lower()
                        )

                        if similarity > 0.8:  # High similarity threshold
                            candidates.append(
                                {
                                    "artist_name": artist.name,
                                    "source": "database_match",
                                    "confidence": similarity * 0.85,
                                    "metadata": {"artist_id": artist.id},
                                    "match_reason": f"Similar title in database: {video.title}",
                                }
                            )
                            break  # Only add once per artist

        except Exception as e:
            logger.warning(f"Database search failed for '{song_title}': {e}")

        return candidates

    def _deduplicate_and_score(
        self, candidates: List[Dict], song_title: str
    ) -> List[Dict]:
        """Remove duplicates and adjust confidence scores"""
        # Group by artist name (case insensitive)
        artist_groups = {}

        for candidate in candidates:
            artist_key = candidate["artist_name"].lower()
            if artist_key not in artist_groups:
                artist_groups[artist_key] = []
            artist_groups[artist_key].append(candidate)

        # For each artist, keep the best candidate and boost confidence if multiple sources agree
        final_candidates = []

        for artist_key, group in artist_groups.items():
            # Sort by confidence
            group.sort(key=lambda x: x["confidence"], reverse=True)
            best_candidate = group[0]

            # Boost confidence if multiple sources agree
            if len(group) > 1:
                source_bonus = min(0.2, (len(group) - 1) * 0.1)
                best_candidate["confidence"] = min(
                    1.0, best_candidate["confidence"] + source_bonus
                )

                # Update match reason to include multiple sources
                sources = list(set(c["source"] for c in group))
                best_candidate[
                    "match_reason"
                ] += f" (confirmed by {', '.join(sources)})"

            # Additional scoring based on artist name quality
            name_quality_score = self._assess_artist_name_quality(
                best_candidate["artist_name"]
            )
            best_candidate["confidence"] *= name_quality_score

            final_candidates.append(best_candidate)

        return final_candidates

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings"""
        # Use difflib for sequence matching
        similarity = difflib.SequenceMatcher(None, str1, str2).ratio()

        # Boost score for exact matches
        if str1 == str2:
            similarity = 1.0
        elif str1 in str2 or str2 in str1:
            similarity = max(similarity, 0.8)

        return similarity

    def _is_valid_artist_name(self, name: str) -> bool:
        """Check if a string looks like a valid artist name"""
        name = name.strip()

        # Basic validation
        if len(name) < 2 or len(name) > 100:
            return False

        # Skip obvious non-artist terms
        invalid_terms = [
            "video",
            "lyrics",
            "official",
            "music",
            "live",
            "acoustic",
            "remix",
            "cover",
            "instrumental",
            "karaoke",
            "version",
            "hd",
            "hq",
            "full",
            "complete",
            "extended",
            "radio",
            "edit",
        ]

        name_lower = name.lower()
        for term in invalid_terms:
            if term in name_lower:
                return False

        # Check for reasonable character composition
        alpha_ratio = sum(c.isalpha() or c.isspace() for c in name) / len(name)
        if alpha_ratio < 0.7:  # Should be mostly letters and spaces
            return False

        return True

    def _assess_artist_name_quality(self, name: str) -> float:
        """Assess the quality/likelihood of an artist name"""
        score = 1.0

        # Penalize very short names
        if len(name) < 3:
            score *= 0.7

        # Penalize very long names
        if len(name) > 50:
            score *= 0.8

        # Penalize names with too many special characters
        special_char_ratio = sum(not (c.isalnum() or c.isspace()) for c in name) / len(
            name
        )
        if special_char_ratio > 0.3:
            score *= 0.7

        # Boost common artist name patterns
        if any(word in name.lower() for word in ["the ", "and", "&"]):
            score *= 1.1

        return min(1.0, score)

    def get_identification_summary(self, session, limit: int = 20) -> Dict:
        """Get a summary of songs that could be identified"""
        try:
            # Get videos assigned to "Unknown Artist"
            unknown_artist = (
                session.query(Artist).filter(Artist.name == "Unknown Artist").first()
            )

            if not unknown_artist:
                return {
                    "total_unknown_videos": 0,
                    "identifiable_videos": [],
                    "summary": "No Unknown Artist found",
                }

            # Get a sample of videos
            videos = (
                session.query(Video)
                .filter(Video.artist_id == unknown_artist.id)
                .limit(limit)
                .all()
            )

            identifiable_videos = []

            for video in videos:
                candidates = self.identify_artist_from_title(video.title)

                if candidates and candidates[0]["confidence"] > 0.5:
                    identifiable_videos.append(
                        {
                            "video_id": video.id,
                            "title": video.title,
                            "best_candidate": candidates[0],
                            "all_candidates": candidates,
                        }
                    )

            return {
                "total_unknown_videos": len(unknown_artist.videos),
                "sampled_videos": len(videos),
                "identifiable_videos": identifiable_videos,
                "identification_rate": (
                    len(identifiable_videos) / len(videos) if videos else 0
                ),
                "summary": f"Found {len(identifiable_videos)} identifiable videos out of {len(videos)} sampled",
            }

        except Exception as e:
            logger.error(f"Error getting identification summary: {e}")
            return {
                "total_unknown_videos": 0,
                "identifiable_videos": [],
                "summary": f"Error: {str(e)}",
            }


# Convenience instance
artist_identification_service = ArtistIdentificationService()
