"""
IMVDb API service for fetching music video metadata
"""

import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.imvdb_service")


class IMVDbService:
    """Service for interacting with the IMVDb API"""

    def __init__(self):
        self.base_url = "https://imvdb.com/api/v1"
        self.rate_limit_delay = 1.0  # Seconds between requests
        self.last_request_time = 0
        self._api_key = None

    def get_api_key(self):
        """Get API key from settings"""
        # Use SettingsService class methods directly for better Flask context handling
        from src.services.settings_service import SettingsService

        # Force reload settings cache
        SettingsService.reload_cache()
        api_key = SettingsService.get("imvdb_api_key", "")
        self._api_key = api_key  # Cache for consistency
        logger.debug(f"IMVDb API key: {'SET' if api_key else 'NOT SET'}")
        return api_key

    @property
    def api_key(self):
        """Property to access API key consistently"""
        if self._api_key is None:
            return self.get_api_key()
        return self._api_key

    def _rate_limit(self):
        """Implement rate limiting for API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Dict = None, retry_auth: bool = True
    ) -> Optional[Dict]:
        """Make a request to the IMVDb API"""
        api_key = self.get_api_key()
        if not api_key:
            logger.error(
                "IMVDb API key not configured. Please configure your API key in Settings > External Services. Get your API key from https://imvdb.com/developers/api"
            )
            return None

        self._rate_limit()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"User-Agent": "MVidarr/1.0", "Authorization": f"Bearer {api_key}"}

        if params is None:
            params = {}

        try:
            logger.debug(f"Making request to IMVDb: {url} with params: {params}")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Authentication error - try refreshing API key once
                if retry_auth:
                    logger.info(
                        "IMVDb authentication failed, refreshing API key and retrying"
                    )
                    old_key = self._api_key
                    new_key = self.get_api_key()
                    if new_key != old_key:
                        return self._make_request(endpoint, params, retry_auth=False)

                logger.error(
                    "IMVDb API authentication failed. Please check your API key in Settings > External Services. Get your API key from https://imvdb.com/developers/api"
                )
                return None
            elif response.status_code == 403:
                logger.error(
                    f"IMVDb API access forbidden for {endpoint}. Your API key may lack permissions for this endpoint."
                )
                return None
            elif response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"IMVDb rate limit exceeded, waiting {retry_after}s")
                time.sleep(retry_after)
                return self._make_request(
                    endpoint, params, retry_auth=False
                )  # Retry once
            elif response.status_code == 404:
                logger.debug(f"IMVDb API returned 404 for {endpoint}")
                return None
            else:
                logger.error(
                    f"IMVDb API error: {response.status_code} - {response.text[:200]}"
                )
                return None

        except requests.exceptions.Timeout as e:
            logger.error(f"IMVDb API request timed out: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Failed to connect to IMVDb API - check internet connection: {e}"
            )
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"IMVDb API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in IMVDb request: {e}")
            return None

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

    def get_video_by_id(self, imvdb_id: str) -> Optional[Dict]:
        """
        Get detailed video information by IMVDb ID

        Args:
            imvdb_id: IMVDb video ID

        Returns:
            Video metadata dictionary or None
        """
        response = self._make_request(f"video/{imvdb_id}")

        if response:
            logger.info(f"Retrieved video details for IMVDb ID: {imvdb_id}")
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
                extracted_name = self._extract_artist_name(artist)
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
                            extracted_name = self._extract_artist_name(artist)
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

    def _extract_artist_name(self, artist_data: Dict) -> Optional[str]:
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

    def get_artist(self, artist_id: str) -> Optional[Dict]:
        """
        Get detailed artist information by IMVDb ID

        Args:
            artist_id: IMVDb artist ID

        Returns:
            Artist metadata dictionary or None
        """
        response = self._make_request(f"entity/{artist_id}")

        if response:
            # Extract and normalize the artist name
            artist_name = self._extract_artist_name(response)
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

    def extract_metadata(self, video_data: Dict) -> Dict:
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

        return metadata

    def advanced_search_videos(self, filters: Dict) -> Dict:
        """
        Advanced video search with multiple filter criteria

        Args:
            filters: Dictionary containing search filters:
                - query: Text search query
                - year_min: Minimum year (int)
                - year_max: Maximum year (int)
                - genre: Genre filter (string)
                - directors: Director names (list or string)
                - artists: Artist names (list or string)
                - limit: Maximum results (default 50)
                - offset: Result offset for pagination (default 0)
                - sort_by: Sort criteria (year, title, artist, relevance)
                - sort_order: asc or desc

        Returns:
            Dictionary with filtered video results and metadata
        """
        # Build base query
        query = filters.get("query", "")

        # Make initial request with broader search
        params = {"q": query, "limit": 200}  # Get more results for filtering
        response = self._make_request("search/videos", params)

        if not response or "results" not in response:
            return {
                "videos": [],
                "total_results": 0,
                "filters_applied": filters,
                "search_method": "advanced_search_no_results",
            }

        videos = response["results"]
        filtered_videos = []

        # Apply filters
        for video in videos:
            if not self._video_matches_filters(video, filters):
                continue

            # Add relevance score
            video["relevance_score"] = self._calculate_video_relevance(video, filters)
            filtered_videos.append(video)

        # Sort results
        sort_by = filters.get("sort_by", "relevance")
        sort_order = filters.get("sort_order", "desc")
        filtered_videos = self._sort_videos(filtered_videos, sort_by, sort_order)

        # Apply pagination
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        paginated_videos = filtered_videos[offset : offset + limit]

        logger.info(
            f"Advanced search found {len(filtered_videos)} videos matching filters "
            f"(showing {len(paginated_videos)} after pagination)"
        )

        return {
            "videos": paginated_videos,
            "total_results": len(filtered_videos),
            "total_before_filters": len(videos),
            "filters_applied": filters,
            "search_method": "advanced_search",
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < len(filtered_videos),
            },
        }

    def _video_matches_filters(self, video: Dict, filters: Dict) -> bool:
        """Check if a video matches the given filter criteria"""

        # Year range filter
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        if year_min or year_max:
            video_year = video.get("year")
            if video_year:
                try:
                    video_year = int(video_year)
                    if year_min and video_year < int(year_min):
                        return False
                    if year_max and video_year > int(year_max):
                        return False
                except (ValueError, TypeError):
                    if (
                        year_min or year_max
                    ):  # If year filters specified but video has no valid year
                        return False

        # Genre filter
        genre_filter = filters.get("genre")
        if genre_filter:
            video_genre = str(video.get("genre", "")).lower()
            if genre_filter.lower() not in video_genre:
                return False

        # Directors filter
        directors_filter = filters.get("directors")
        if directors_filter:
            if isinstance(directors_filter, str):
                directors_filter = [directors_filter]

            video_directors = video.get("directors", [])
            video_director_names = []

            for director in video_directors:
                if isinstance(director, dict):
                    video_director_names.append(director.get("name", "").lower())
                else:
                    video_director_names.append(str(director).lower())

            # Check if any specified director is in the video
            found_director = False
            for director_filter in directors_filter:
                director_filter = director_filter.lower()
                for video_director in video_director_names:
                    if (
                        director_filter in video_director
                        or video_director in director_filter
                    ):
                        found_director = True
                        break
                if found_director:
                    break

            if not found_director:
                return False

        # Artists filter (additional artist filtering beyond the main search)
        artists_filter = filters.get("artists")
        if artists_filter:
            if isinstance(artists_filter, str):
                artists_filter = [artists_filter]

            # Get video artists
            video_artists = []
            if "artist" in video and isinstance(video["artist"], dict):
                video_artists.append(video["artist"].get("name", "").lower())
            elif "artists" in video and isinstance(video["artists"], list):
                for artist in video["artists"]:
                    if isinstance(artist, dict):
                        video_artists.append(artist.get("name", "").lower())
                    else:
                        video_artists.append(str(artist).lower())

            # Check if any specified artist matches
            found_artist = False
            for artist_filter in artists_filter:
                artist_filter = artist_filter.lower()
                for video_artist in video_artists:
                    if artist_filter in video_artist or video_artist in artist_filter:
                        found_artist = True
                        break
                if found_artist:
                    break

            if not found_artist:
                return False

        return True

    def _calculate_video_relevance(self, video: Dict, filters: Dict) -> float:
        """Calculate relevance score for a video based on search criteria"""
        score = 0.0
        query = filters.get("query", "").lower()

        if not query:
            return 1.0  # Default score when no query

        # Title relevance
        title = str(video.get("song_title", "")).lower()
        if query in title:
            score += 10.0
        if title == query:
            score += 5.0

        # Artist relevance
        artist_name = ""
        if "artist" in video and isinstance(video["artist"], dict):
            artist_name = video["artist"].get("name", "").lower()

        if query in artist_name:
            score += 8.0
        if artist_name == query:
            score += 4.0

        # Bonus for complete metadata
        if video.get("year"):
            score += 1.0
        if video.get("directors"):
            score += 0.5
        if video.get("image_url") or video.get("image"):
            score += 0.5

        return score

    def _sort_videos(
        self, videos: List[Dict], sort_by: str, sort_order: str
    ) -> List[Dict]:
        """Sort videos by specified criteria"""
        reverse = sort_order.lower() == "desc"

        if sort_by == "year":
            return sorted(videos, key=lambda v: v.get("year") or 0, reverse=reverse)
        elif sort_by == "title":
            return sorted(
                videos, key=lambda v: v.get("song_title", "").lower(), reverse=reverse
            )
        elif sort_by == "artist":

            def get_artist_name(v):
                if "artist" in v and isinstance(v["artist"], dict):
                    return v["artist"].get("name", "").lower()
                return ""

            return sorted(videos, key=get_artist_name, reverse=reverse)
        elif sort_by == "relevance":
            return sorted(
                videos, key=lambda v: v.get("relevance_score", 0), reverse=reverse
            )
        else:
            # Default to relevance
            return sorted(
                videos, key=lambda v: v.get("relevance_score", 0), reverse=reverse
            )

    def search_videos_by_genre(self, genre: str, limit: int = 50) -> List[Dict]:
        """
        Search for videos by genre

        Args:
            genre: Genre to search for
            limit: Maximum number of results

        Returns:
            List of videos matching the genre
        """
        filters = {"genre": genre, "limit": limit, "sort_by": "relevance"}

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def search_videos_by_year_range(
        self, year_min: int, year_max: int, limit: int = 50
    ) -> List[Dict]:
        """
        Search for videos within a year range

        Args:
            year_min: Minimum year (inclusive)
            year_max: Maximum year (inclusive)
            limit: Maximum number of results

        Returns:
            List of videos from the specified year range
        """
        filters = {
            "year_min": year_min,
            "year_max": year_max,
            "limit": limit,
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def search_videos_by_director(self, director: str, limit: int = 50) -> List[Dict]:
        """
        Search for videos by director

        Args:
            director: Director name to search for
            limit: Maximum number of results

        Returns:
            List of videos by the specified director
        """
        filters = {
            "directors": [director],
            "limit": limit,
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        return result["videos"]

    def get_trending_videos(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """
        Get trending/popular videos (simulated with recent high-quality videos)

        Args:
            days: Number of days to look back (currently used for reference)
            limit: Maximum number of results

        Returns:
            List of trending videos
        """
        # Since IMVDb doesn't have a specific trending endpoint,
        # we'll simulate this by getting recent videos with good metadata
        from datetime import datetime, timedelta

        current_year = datetime.now().year
        # Look for videos from recent years with complete metadata

        filters = {
            "year_min": current_year - 2,  # Last 2 years
            "year_max": current_year,
            "limit": limit * 3,  # Get more to filter for quality
            "sort_by": "year",
            "sort_order": "desc",
        }

        result = self.advanced_search_videos(filters)
        videos = result["videos"]

        # Filter for videos with good metadata (likely to be popular/well-maintained)
        quality_videos = []
        for video in videos:
            quality_score = 0

            # Videos with directors are often more notable
            if video.get("directors"):
                quality_score += 3

            # Videos with images are more likely to be popular
            if video.get("image_url") or video.get("image"):
                quality_score += 2

            # Videos with genre info
            if video.get("genre"):
                quality_score += 1

            # Videos with complete artist info
            if isinstance(video.get("artist"), dict) and video["artist"].get("name"):
                quality_score += 2

            if quality_score >= 4:  # Minimum quality threshold
                video["quality_score"] = quality_score
                quality_videos.append(video)

        # Sort by quality score and return top results
        quality_videos.sort(key=lambda v: v.get("quality_score", 0), reverse=True)

        logger.info(f"Found {len(quality_videos)} trending/quality videos")
        return quality_videos[:limit]

    def analyze_video_quality(self, video_data: Dict) -> Dict:
        """
        Analyze video quality and source preferences

        Args:
            video_data: IMVDb video metadata

        Returns:
            Dictionary with quality analysis
        """
        quality_analysis = {
            "overall_score": 0.0,
            "metadata_completeness": 0.0,
            "source_quality": 0.0,
            "production_quality": 0.0,
            "factors": [],
        }

        # Metadata completeness score (0-40 points)
        metadata_score = 0
        if video_data.get("song_title"):
            metadata_score += 10
            quality_analysis["factors"].append("Complete title information")

        if video_data.get("year"):
            metadata_score += 10
            quality_analysis["factors"].append("Release year available")

        if video_data.get("genre"):
            metadata_score += 5
            quality_analysis["factors"].append("Genre information")

        if video_data.get("directors"):
            metadata_score += 10
            quality_analysis["factors"].append("Director information")

        if video_data.get("image") or video_data.get("image_url"):
            metadata_score += 5
            quality_analysis["factors"].append("Thumbnail available")

        quality_analysis["metadata_completeness"] = min(metadata_score, 40)

        # Production quality score (0-30 points)
        production_score = 0
        directors = video_data.get("directors", [])
        if directors and len(directors) > 0:
            production_score += 15
            if len(directors) > 1:
                production_score += 5  # Multiple directors often indicate higher budget

        if video_data.get("producers"):
            production_score += 10
            quality_analysis["factors"].append("Producer information available")

        quality_analysis["production_quality"] = min(production_score, 30)

        # Source quality score (0-30 points)
        source_score = 0

        # Year-based quality (newer videos often have better quality)
        year = video_data.get("year")
        if year:
            try:
                year_int = int(year)
                if year_int >= 2020:
                    source_score += 15
                elif year_int >= 2015:
                    source_score += 12
                elif year_int >= 2010:
                    source_score += 8
                elif year_int >= 2005:
                    source_score += 5
                else:
                    source_score += 2
            except (ValueError, TypeError):
                pass

        # Artist popularity indicator (having an IMVDB artist page suggests more popular/quality content)
        if isinstance(video_data.get("artist"), dict) and video_data["artist"].get(
            "id"
        ):
            source_score += 10
            quality_analysis["factors"].append("Artist has dedicated IMVDB profile")

        # Genre-based quality weighting
        genre = video_data.get("genre", "").lower()
        if genre in ["pop", "rock", "hip-hop", "electronic", "r&b"]:
            source_score += 5  # Popular genres often have higher production values

        quality_analysis["source_quality"] = min(source_score, 30)

        # Calculate overall score
        quality_analysis["overall_score"] = (
            quality_analysis["metadata_completeness"]
            + quality_analysis["production_quality"]
            + quality_analysis["source_quality"]
        )

        return quality_analysis

    def get_user_preferences(self, user_id: Optional[int] = None) -> Dict:
        """
        Get user preferences for video quality and sources

        Args:
            user_id: Optional user ID for personalized preferences

        Returns:
            Dictionary with user preferences
        """
        # Default preferences - in a full implementation, these would come from user settings
        default_preferences = {
            "min_quality_score": 50.0,
            "preferred_years": {"min": 2000, "max": 2024},
            "preferred_genres": [
                "pop",
                "rock",
                "hip-hop",
                "electronic",
                "indie",
                "alternative",
            ],
            "require_directors": False,
            "require_thumbnails": True,
            "source_preferences": {
                "high_metadata": 1.0,  # Prefer videos with complete metadata
                "recent_years": 0.8,  # Slight preference for newer videos
                "popular_artists": 0.9,  # Prefer videos from artists with IMVDB profiles
                "complete_production": 0.7,  # Prefer videos with director/producer info
            },
        }

        # In a full implementation, you would query user preferences from database here
        # For now, return defaults
        return default_preferences

    def rank_videos_by_preferences(
        self, videos: List[Dict], user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Rank videos based on user preferences and quality analysis

        Args:
            videos: List of IMVDb video data
            user_id: Optional user ID for personalized ranking

        Returns:
            List of videos ranked by preference score
        """
        preferences = self.get_user_preferences(user_id)
        ranked_videos = []

        for video in videos:
            # Analyze video quality
            quality_analysis = self.analyze_video_quality(video)

            # Calculate preference score
            preference_score = quality_analysis["overall_score"]

            # Apply user preference multipliers
            source_prefs = preferences.get("source_preferences", {})

            # Bonus for high metadata completeness
            if quality_analysis["metadata_completeness"] >= 30:
                preference_score *= source_prefs.get("high_metadata", 1.0)

            # Year preference bonus
            year = video.get("year")
            if year:
                try:
                    year_int = int(year)
                    year_prefs = preferences.get("preferred_years", {})
                    if (
                        year_prefs.get("min", 0)
                        <= year_int
                        <= year_prefs.get("max", 9999)
                    ):
                        preference_score *= source_prefs.get("recent_years", 1.0)
                except (ValueError, TypeError):
                    pass

            # Genre preference bonus
            genre = video.get("genre", "").lower()
            preferred_genres = [
                g.lower() for g in preferences.get("preferred_genres", [])
            ]
            if genre in preferred_genres:
                preference_score *= 1.1

            # Apply minimum quality threshold
            min_quality = preferences.get("min_quality_score", 0)
            if quality_analysis["overall_score"] < min_quality:
                preference_score *= 0.5  # Penalty for low quality

            # Add enhanced video data
            enhanced_video = video.copy()
            enhanced_video.update(
                {
                    "quality_analysis": quality_analysis,
                    "preference_score": preference_score,
                    "meets_quality_threshold": quality_analysis["overall_score"]
                    >= min_quality,
                }
            )

            ranked_videos.append(enhanced_video)

        # Sort by preference score (highest first)
        ranked_videos.sort(key=lambda v: v.get("preference_score", 0), reverse=True)

        logger.info(f"Ranked {len(ranked_videos)} videos by user preferences")
        return ranked_videos

    def get_quality_statistics(self, videos: List[Dict]) -> Dict:
        """
        Get quality statistics for a list of videos

        Args:
            videos: List of videos to analyze

        Returns:
            Dictionary with quality statistics
        """
        if not videos:
            return {"total_videos": 0}

        quality_scores = []
        metadata_scores = []
        production_scores = []
        source_scores = []

        year_distribution = {}
        genre_distribution = {}
        director_count = 0
        thumbnail_count = 0

        for video in videos:
            analysis = self.analyze_video_quality(video)
            quality_scores.append(analysis["overall_score"])
            metadata_scores.append(analysis["metadata_completeness"])
            production_scores.append(analysis["production_quality"])
            source_scores.append(analysis["source_quality"])

            # Year distribution
            year = video.get("year")
            if year:
                try:
                    decade = (int(year) // 10) * 10
                    year_distribution[f"{decade}s"] = (
                        year_distribution.get(f"{decade}s", 0) + 1
                    )
                except (ValueError, TypeError):
                    pass

            # Genre distribution
            genre = video.get("genre", "Unknown").title()
            if genre:
                genre_distribution[genre] = genre_distribution.get(genre, 0) + 1

            # Feature counts
            if video.get("directors"):
                director_count += 1
            if video.get("image") or video.get("image_url"):
                thumbnail_count += 1

        return {
            "total_videos": len(videos),
            "quality_stats": {
                "average_overall": sum(quality_scores) / len(quality_scores),
                "average_metadata": sum(metadata_scores) / len(metadata_scores),
                "average_production": sum(production_scores) / len(production_scores),
                "average_source": sum(source_scores) / len(source_scores),
                "high_quality_count": len([s for s in quality_scores if s >= 70]),
                "medium_quality_count": len(
                    [s for s in quality_scores if 40 <= s < 70]
                ),
                "low_quality_count": len([s for s in quality_scores if s < 40]),
            },
            "feature_stats": {
                "videos_with_directors": director_count,
                "videos_with_thumbnails": thumbnail_count,
                "director_percentage": (director_count / len(videos)) * 100,
                "thumbnail_percentage": (thumbnail_count / len(videos)) * 100,
            },
            "distribution": {
                "by_decade": dict(sorted(year_distribution.items())),
                "by_genre": dict(
                    sorted(genre_distribution.items(), key=lambda x: x[1], reverse=True)
                ),
            },
        }

    def test_connection(self) -> Dict:
        """
        Test the connection to IMVDb API

        Returns:
            Dictionary with connection status
        """
        status = {
            "service": "IMVDb",
            "status": "unknown",
            "message": "",
            "authenticated": False,
            "help_url": "https://imvdb.com/developers/api",
        }

        # Get the latest API key
        api_key = self.get_api_key()

        if not api_key:
            status.update(
                {
                    "status": "error",
                    "message": "IMVDb API key not configured. Please configure your API key in Settings > External Services.",
                }
            )
            return status

        # Try a simple search request
        try:
            logger.debug("Testing IMVDb API connection...")
            response = self._make_request(
                "search/videos", {"q": "test", "limit": 1}, retry_auth=False
            )

            if response is not None:
                status.update(
                    {
                        "status": "success",
                        "message": "IMVDb API connection successful",
                        "authenticated": True,
                        "results_returned": len(response.get("results", [])),
                        "api_key_configured": True,
                    }
                )

                # Try to get additional API info if available
                try:
                    # Test with a known artist search to validate broader functionality
                    artist_test = self._make_request(
                        "search/entities", {"q": "test", "limit": 1}, retry_auth=False
                    )
                    if artist_test:
                        status["artist_search_working"] = True
                        status["message"] += " (full API functionality confirmed)"
                    else:
                        status["artist_search_working"] = False
                        status[
                            "message"
                        ] += " (video search working, artist search may have issues)"
                except Exception as e:
                    logger.debug(f"IMVDb artist search test failed: {e}")
                    status["artist_search_working"] = False

            else:
                status.update(
                    {
                        "status": "error",
                        "message": "Failed to connect to IMVDb API. Please check your API key and internet connection.",
                    }
                )

        except Exception as e:
            logger.error(f"IMVDb connection test failed: {e}")
            status.update(
                {"status": "error", "message": f"Connection test failed: {str(e)}"}
            )

        return status

    def get_service_status(self) -> Dict:
        """Get comprehensive service status information"""
        return {
            "service": "IMVDb",
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "rate_limit_delay": self.rate_limit_delay,
            "last_request_time": self.last_request_time,
            "user_agent": "MVidarr/1.0",
        }


# Convenience instance
imvdb_service = IMVDbService()
