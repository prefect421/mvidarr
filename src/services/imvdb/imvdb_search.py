"""
IMVDb search operations - Video and artist search functionality
"""

from typing import Dict, List, Optional

from src.services.imvdb.imvdb_client import IMVDbClient
from src.utils.logger import get_logger

logger = get_logger("mvidarr.imvdb_search")


class IMVDbSearch(IMVDbClient):
    """Search operations for videos and artists"""

    def search_videos(self, artist: str, title: str = None) -> List[Dict]:
        """
        Search for music videos by artist and optionally title

        Args:
            artist: Artist name
            title: Optional song title

        Returns:
            List of video metadata dictionaries
        """
        # Ensure parameters are strings and handle special characters
        if not isinstance(artist, str):
            logger.warning(
                f"Artist parameter is not a string: {type(artist)} = {artist}"
            )
            artist = str(artist) if artist is not None else ""

        if title is not None and not isinstance(title, str):
            logger.warning(f"Title parameter is not a string: {type(title)} = {title}")
            title = str(title) if title is not None else ""

        params = {"q": artist}
        if title:
            params["q"] = f"{artist} {title}"

        response = self._make_request("search/videos", params)

        if response and "results" in response:
            videos = response["results"]
            logger.info(f"Found {len(videos)} videos for '{params['q']}'")
            return videos

        return []

    def search_artist_videos(self, artist: str, limit: int = 10) -> Dict:
        """
        Search for all videos by a specific artist

        First tries to find the artist by ID, then gets their videos.
        Falls back to filtered search if artist ID not found.

        Args:
            artist: Artist name
            limit: Maximum number of results to return

        Returns:
            Dictionary containing videos list
        """
        # First, try to find the artist to get their ID
        artist_info = self.search_artist(artist)

        if artist_info and artist_info.get("id"):
            # Get videos by artist ID (more accurate)
            artist_id = artist_info["id"]
            result = self.get_artist_videos_by_id(str(artist_id), limit)

            if result["total_results"] > 0:
                logger.info(
                    f"Found {result['total_results']} videos for artist '{artist}' (by ID: {artist_id})"
                )
                return result
            else:
                logger.info(
                    f"No videos found by ID for artist '{artist}' (ID: {artist_id}), trying fallback search"
                )

        # Fallback: search by name and filter results
        params = {"q": artist, "limit": limit * 3}  # Get more results to filter
        response = self._make_request("search/videos", params)

        if response and "results" in response:
            all_videos = response["results"]

            # Log sample video structure for debugging
            if all_videos:
                logger.debug(f"Sample video structure: {all_videos[0]}")

            # Filter videos to only include those actually by the artist
            filtered_videos = []
            artist_lower = str(artist).lower()

            for video in all_videos:
                # Check multiple possible artist field names
                video_artists = []

                # Try different field names for artists
                if "artists" in video:
                    video_artists = video["artists"]
                elif "artist" in video:
                    artist_data = video["artist"]
                    if isinstance(artist_data, dict):
                        video_artists = [artist_data]
                    else:
                        video_artists = [{"name": artist_data}]

                # Handle both string and list formats for artists
                if isinstance(video_artists, str):
                    video_artists = [{"name": video_artists}]
                elif not isinstance(video_artists, list):
                    video_artists = []

                # Check if our artist name matches any of the video's artists
                found_match = False
                for video_artist in video_artists:
                    if isinstance(video_artist, dict):
                        artist_name = video_artist.get("name", "").lower()
                    else:
                        artist_name = str(video_artist).lower()

                    # More flexible matching
                    if (
                        artist_lower in artist_name
                        or artist_name in artist_lower
                        or artist_lower.replace('"', "") in artist_name
                        or artist_name in artist_lower.replace('"', "")
                    ):
                        filtered_videos.append(video)
                        found_match = True
                        break

                if found_match:
                    continue

                if len(filtered_videos) >= limit:
                    break

            logger.info(
                f"Found {len(filtered_videos)} videos for artist '{artist}' (filtered from {len(all_videos)} total)"
            )
            return {
                "videos": filtered_videos[:limit],
                "total_results": len(filtered_videos),
                "search_method": "filtered_search",
                "artist": artist,
            }

        return {
            "videos": [],
            "total_results": 0,
            "search_method": "no_results",
            "artist": artist,
        }

    def get_artist_videos_by_id(self, artist_id: str, limit: int = 50) -> Dict:
        """
        Get videos by a specific artist using their IMVDb ID (most accurate method)

        Args:
            artist_id: IMVDb artist ID
            limit: Maximum number of results to return

        Returns:
            Dictionary containing videos list
        """
        # First, get the artist information to get their name
        artist_info = self.get_artist(artist_id)
        if not artist_info:
            logger.warning(f"Could not get artist info for ID {artist_id}")
            return {
                "videos": [],
                "total_results": 0,
                "search_method": "no_artist_info",
                "artist_id": artist_id,
            }

        # Get the artist name for searching - use slug as fallback if name is None
        artist_name = artist_info.get("name", "")
        # Ensure artist_name is a string (fix for integer name issue)
        if artist_name:
            artist_name = str(artist_name)
        if not artist_name:
            # Try to use the slug as the artist name (convert from slug format)
            artist_slug = artist_info.get("slug", "")
            if artist_slug:
                # Ensure slug is a string (fix for integer slug issue)
                artist_slug = str(artist_slug)
                # Convert slug to proper name (e.g., "eurythmics" -> "Eurythmics")
                artist_name = artist_slug.replace("-", " ").title()
                logger.info(
                    f"Using slug '{artist_slug}' as artist name '{artist_name}' for ID {artist_id}"
                )
            else:
                logger.warning(
                    f"Artist ID {artist_id} has no name or slug, cannot search for videos"
                )
                return {
                    "videos": [],
                    "total_results": 0,
                    "search_method": "no_artist_name",
                    "artist_id": artist_id,
                }

        # Use the same proven search method as name-based search
        params = {"q": artist_name, "limit": limit * 3}  # Get more results to filter
        response = self._make_request("search/videos", params)

        if not response or "results" not in response:
            logger.info(
                f"No videos found by ID for artist '{artist_name}' (ID: {artist_id}), trying fallback search"
            )
            return {
                "videos": [],
                "total_results": 0,
                "search_method": "no_results",
                "artist_id": artist_id,
            }

        all_videos = response["results"]

        # Log sample video structure for debugging
        if all_videos:
            logger.debug(f"Sample video structure: {all_videos[0]}")

        # Filter videos to only include those actually by the artist
        # This is the same robust filtering logic from search_artist_videos
        filtered_videos = []
        artist_lower = str(artist_name).lower()

        for video in all_videos:
            # Check multiple possible artist field names
            video_artists = []

            # Try different field names for artists
            if "artists" in video:
                video_artists = video["artists"]
            elif "artist" in video:
                artist_data = video["artist"]
                if isinstance(artist_data, dict):
                    video_artists = [artist_data]
                else:
                    video_artists = [{"name": artist_data}]

            # Handle both string and list formats for artists
            if isinstance(video_artists, str):
                video_artists = [{"name": video_artists}]
            elif not isinstance(video_artists, list):
                video_artists = []

            # Check if our artist name matches any of the video's artists
            found_match = False
            for video_artist in video_artists:
                if isinstance(video_artist, dict) and "name" in video_artist:
                    # Ensure artist name is a string (fix for integer name issue)
                    artist_video_name = str(video_artist["name"]).lower()

                    # Check for exact match or if one name contains the other
                    # Also handle special cases like "blink-182" vs "blink 182"
                    normalized_artist = artist_lower.replace("-", " ").replace("_", " ")
                    normalized_video_artist = artist_video_name.replace(
                        "-", " "
                    ).replace("_", " ")

                    if (
                        artist_lower == artist_video_name
                        or artist_lower in artist_video_name
                        or artist_video_name in artist_lower
                        or normalized_artist == normalized_video_artist
                        or normalized_artist in normalized_video_artist
                        or normalized_video_artist in normalized_artist
                    ):
                        found_match = True
                        break

                    # Also check if the video artist has the same IMVDb ID
                    if "id" in video_artist and str(video_artist["id"]) == str(
                        artist_id
                    ):
                        found_match = True
                        break

            if found_match:
                filtered_videos.append(video)

                # Stop if we have enough results
                if len(filtered_videos) >= limit:
                    break

        logger.info(
            f"Found {len(filtered_videos)} videos for artist '{artist_name}' (ID: {artist_id}) (filtered from {len(all_videos)} total)"
        )

        return {
            "videos": filtered_videos[:limit],
            "total_results": len(filtered_videos),
            "search_method": "by_artist_id",
            "artist_id": artist_id,
            "artist_name": artist_name,
        }

    def get_video_by_id(
        self, imvdb_id: str, include_sources: bool = True
    ) -> Optional[Dict]:
        """
        Get detailed video information by IMVDb ID

        Args:
            imvdb_id: IMVDb video ID
            include_sources: Whether to include video sources (YouTube, etc.)

        Returns:
            Video metadata dictionary or None
        """
        params = {}
        if include_sources:
            params["include_sources"] = 1

        response = self._make_request(f"video/{imvdb_id}", params)

        if response:
            logger.info(
                f"Retrieved video details for IMVDb ID: {imvdb_id} (sources: {include_sources})"
            )
            return response

        return None

    def search_artist(
        self, artist_name: str, return_multiple: bool = False
    ) -> Optional[Dict]:
        """
        Search for artist information

        Args:
            artist_name: Name of the artist
            return_multiple: If True, return all matches instead of just the first

        Returns:
            Artist metadata dictionary (or list if return_multiple=True) or None
        """
        from src.services.imvdb.imvdb_metadata import extract_artist_name

        # Try original name first
        params = {"q": artist_name}
        response = self._make_request("search/entities", params)

        if response and "results" in response and len(response["results"]) > 0:
            if return_multiple:
                artists = response["results"]
                logger.info(f"Found {len(artists)} artists for search '{artist_name}'")
                return artists
            else:
                # Return the first (best) match
                artist = response["results"][0]

                # Extract and normalize the artist name
                extracted_name = extract_artist_name(artist)
                if extracted_name and not artist.get("name"):
                    artist["name"] = extracted_name

                logger.info(
                    f"Found artist: {extracted_name or artist.get('name', artist_name)}, ID: {artist.get('id')}"
                )
                return artist

        # If no results and the name contains common YouTube suffixes, try without them
        if not response or not response.get("results"):
            # Try removing common YouTube channel suffixes
            suffixes_to_remove = ["VEVO", "Official", "Records", "Music", "Channel"]
            for suffix in suffixes_to_remove:
                if artist_name.endswith(suffix):
                    cleaned_name = artist_name[: -len(suffix)].strip()
                    logger.info(
                        f"Trying search without '{suffix}' suffix: '{cleaned_name}'"
                    )

                    params = {"q": cleaned_name}
                    response = self._make_request("search/entities", params)

                    if (
                        response
                        and "results" in response
                        and len(response["results"]) > 0
                    ):
                        if return_multiple:
                            artists = response["results"]
                            logger.info(
                                f"Found {len(artists)} artists for cleaned search '{cleaned_name}'"
                            )
                            return artists
                        else:
                            # Return the first (best) match
                            artist = response["results"][0]

                            # Extract and normalize the artist name
                            extracted_name = extract_artist_name(artist)
                            if extracted_name and not artist.get("name"):
                                artist["name"] = extracted_name

                            logger.info(
                                f"Found artist with cleaned name: {extracted_name or artist.get('name', cleaned_name)}, ID: {artist.get('id')}"
                            )
                            return artist

        return None

    def search_artists(self, artist_name: str, limit: int = 50) -> List[Dict]:
        """
        Search for multiple artists by name

        Args:
            artist_name: Name to search for
            limit: Maximum number of results to return

        Returns:
            List of artist metadata dictionaries
        """
        params = {"q": artist_name, "limit": limit}
        response = self._make_request("search/entities", params)

        if response and "results" in response:
            artists = response["results"][:limit]  # Limit results
            logger.info(f"Found {len(artists)} artists for search '{artist_name}'")
            logger.debug(
                f"Sample artist data: {artists[0] if artists else 'No results'}"
            )
            return artists

        logger.warning(
            f"No results found for artist search '{artist_name}'. Response: {response}"
        )
        return []

    def get_artist(self, artist_id: str) -> Optional[Dict]:
        """
        Get detailed artist information by IMVDb ID

        Args:
            artist_id: IMVDb artist ID

        Returns:
            Artist metadata dictionary or None
        """
        from src.services.imvdb.imvdb_metadata import extract_artist_name

        response = self._make_request(f"entity/{artist_id}")

        if response:
            # Extract and normalize the artist name
            artist_name = extract_artist_name(response)
            if artist_name and not response.get("name"):
                # If we extracted a name but the response doesn't have one at the top level,
                # add it for consistency
                response["name"] = artist_name

            logger.info(
                f"Retrieved artist details for IMVDb ID: {artist_id}, Name: {artist_name}"
            )
            return response

        logger.warning(f"Failed to retrieve artist details for IMVDb ID: {artist_id}")
        return None

    def find_best_video_match(self, artist: str, title: str) -> Optional[Dict]:
        """
        Find the best matching video for an artist and title

        Args:
            artist: Artist name
            title: Song title

        Returns:
            Best matching video metadata or None
        """
        # Ensure parameters are strings to handle edge cases
        if not isinstance(artist, str):
            logger.warning(
                f"Artist parameter is not a string: {type(artist)} = {artist}"
            )
            artist = str(artist) if artist is not None else ""

        if not isinstance(title, str):
            logger.warning(f"Title parameter is not a string: {type(title)} = {title}")
            title = str(title) if title is not None else ""

        # First try searching with both artist and title
        videos = self.search_videos(artist, title)

        if not videos:
            # Try searching with just the artist
            videos = self.search_videos(artist)

        if not videos:
            return None

        # Score and rank videos by relevance
        def calculate_match_score(video: Dict) -> float:
            score = 0.0

            video_artist = str(video.get("artist", {}).get("name", "")).lower()
            video_title = str(video.get("song_title", "")).lower()

            artist_lower = str(artist).lower()
            title_lower = str(title).lower()

            # Artist name match (most important)
            if artist_lower in video_artist or video_artist in artist_lower:
                score += 10.0

            # Exact artist match bonus
            if video_artist == artist_lower:
                score += 5.0

            # Title match
            if title_lower in video_title or video_title in title_lower:
                score += 8.0

            # Exact title match bonus
            if video_title == title_lower:
                score += 4.0

            # Prefer videos with more complete metadata
            if video.get("year"):
                score += 1.0
            if video.get("directors"):
                score += 0.5
            if video.get("image_url"):
                score += 0.5

            return score

        # Sort videos by match score
        scored_videos = [(video, calculate_match_score(video)) for video in videos]
        scored_videos.sort(key=lambda x: x[1], reverse=True)

        best_video, best_score = scored_videos[0]

        if best_score > 5.0:  # Minimum threshold for a good match
            logger.info(
                f"Best match for '{artist} - {title}': {best_video.get('song_title', 'Unknown')} (score: {best_score})"
            )
            return best_video
        else:
            logger.debug(
                f"No good match found for '{artist} - {title}' (best score: {best_score})"
            )
            return None
