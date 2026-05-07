"""
Discogs API Integration Service for MVidarr 0.9.9
Provides comprehensive music metadata from the Discogs database.

API Documentation: https://www.discogs.com/developers
Rate Limits: 25 requests/minute (unauthenticated), 60 requests/minute (authenticated)
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.discogs")


class DiscogsService:
    """Service for Discogs API integration and metadata enrichment"""

    def __init__(self):
        self.base_url = "https://api.discogs.com"
        self.user_agent = "MVidarr/0.9.9 (https://github.com/prefect421/mvidarr)"
        # Rate limit: 25 requests per minute for unauthenticated, 60 for authenticated
        self.rate_limit_delay = 2.4
        self.last_request_time = 0

        # Load settings
        self._settings_loaded = False
        self._enabled = None
        self._token = None

    def _load_settings(self):
        """Load Discogs settings from database and environment"""
        if self._settings_loaded:
            return

        import os

        # Try to load from database settings first
        try:
            from src.database.connection import get_db
            from src.database.models import Setting

            with get_db() as db:
                # Check if enabled
                enabled_setting = (
                    db.query(Setting).filter(Setting.key == "discogs_enabled").first()
                )
                if enabled_setting:
                    self._enabled = enabled_setting.value.lower() == "true"
                else:
                    self._enabled = True  # Default to enabled

                # Load token from database
                token_setting = (
                    db.query(Setting).filter(Setting.key == "discogs_token").first()
                )
                if token_setting and token_setting.value:
                    self._token = token_setting.value

                # Load rate limit
                rate_limit_setting = (
                    db.query(Setting)
                    .filter(Setting.key == "discogs_rate_limit")
                    .first()
                )
                if rate_limit_setting:
                    requests_per_minute = int(rate_limit_setting.value)
                    self.rate_limit_delay = 60.0 / requests_per_minute

        except Exception as e:
            logger.debug(f"Could not load Discogs settings from database: {e}")
            self._enabled = True  # Default to enabled

        # Fallback to environment variable if not in database
        if not self._token:
            self._token = os.environ.get("DISCOGS_TOKEN")

        if self._token and self._enabled:
            # Authenticated requests: 60 per minute default
            if not hasattr(self, "rate_limit_delay") or self.rate_limit_delay == 2.4:
                self.rate_limit_delay = 1.0
            logger.info(
                "Discogs integration enabled with authentication (top priority for release dates)"
            )
        elif self._enabled:
            # Discogs requires authentication
            logger.warning(
                "Discogs integration enabled but no API token configured. "
                "Some requests may fail. Configure token in Settings > Services > Metadata Services"
            )
        else:
            logger.info("Discogs integration disabled in settings")

        self._settings_loaded = True

    @property
    def enabled(self):
        """Check if Discogs integration is enabled"""
        self._load_settings()
        return self._enabled

    def _respect_rate_limit(self):
        """Ensure we respect Discogs rate limiting (25 requests per minute)"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make rate-limited request to Discogs API"""
        if not self.enabled:
            logger.warning("Discogs integration is disabled - returning None")
            return None

        self._respect_rate_limit()

        if params is None:
            params = {}

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        # Add authentication token if available
        if self._token:
            headers["Authorization"] = f"Discogs token={self._token}"
            logger.debug(f"Using Discogs authentication token: {self._token[:10]}...")
        else:
            logger.warning("No Discogs token available - request may be rate limited")

        url = f"{self.base_url}/{endpoint}"

        try:
            logger.debug(f"Making Discogs request to: {url} with params: {params}")
            logger.debug(f"Request headers: {headers}")
            response = requests.get(url, params=params, headers=headers, timeout=30)

            # Log response details before raising for status
            logger.debug(f"Discogs API response status: {response.status_code}")
            logger.debug(f"Discogs API response headers: {dict(response.headers)}")

            response.raise_for_status()

            result = response.json()
            logger.debug(
                f"Discogs API returned {len(result.get('results', []))} results"
            )
            return result

        except requests.RequestException as e:
            logger.error(
                f"Discogs API request failed for {url}: {e}\n"
                f"Status code: {getattr(e.response, 'status_code', 'N/A')}\n"
                f"Response text: {getattr(e.response, 'text', 'N/A')[:500]}"
            )
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Discogs response: {e}")
            return None

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two artist/track names"""
        name1_lower = name1.lower().strip()
        name2_lower = name2.lower().strip()

        # Exact match
        if name1_lower == name2_lower:
            return 1.0

        # Remove common prefixes/suffixes
        for prefix in ["the ", "a ", "an "]:
            if name1_lower.startswith(prefix):
                name1_lower = name1_lower[len(prefix) :]
            if name2_lower.startswith(prefix):
                name2_lower = name2_lower[len(prefix) :]

        # Check again after cleaning
        if name1_lower == name2_lower:
            return 0.95

        # Substring match
        if name1_lower in name2_lower or name2_lower in name1_lower:
            return 0.8

        # Calculate simple similarity score
        common_words = set(name1_lower.split()) & set(name2_lower.split())
        if common_words:
            total_words = len(set(name1_lower.split()) | set(name2_lower.split()))
            return 0.6 * (len(common_words) / total_words)

        return 0.0

    def search_release(
        self, track_name: str, artist_name: str, limit: int = 10
    ) -> List[Dict]:
        """
        Search for releases (albums/singles) by track name and artist name.
        Returns list of releases with release dates and other metadata.
        """
        if not track_name or not artist_name:
            return []

        # Build search query - broad search works better than field-specific queries
        # Track name might be a single or on an album
        query = f"{artist_name} {track_name}"

        params = {
            "q": query,
            "type": "release",
            "per_page": limit,
        }

        data = self._make_request("database/search", params)
        if not data or "results" not in data:
            return []

        releases = []
        for release in data.get("results", []):
            # Extract release information
            release_info = {
                "id": release.get("id"),
                "title": release.get("title"),
                "year": release.get("year"),  # Release year
                "format": release.get("format", []),
                "label": release.get("label", []),
                "country": release.get("country"),
                "genre": release.get("genre", []),
                "style": release.get("style", []),
                "uri": release.get("uri"),
                "resource_url": release.get("resource_url"),
                "type": release.get("type"),
                "confidence": self._calculate_name_similarity(
                    track_name, release.get("title", "")
                ),
            }

            releases.append(release_info)

        # Sort by confidence (best matches first)
        releases.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        logger.debug(
            f"Found {len(releases)} releases for '{track_name}' by '{artist_name}'"
        )
        return releases

    def get_release_details(self, release_id: int) -> Optional[Dict]:
        """
        Get detailed information about a specific release by ID.
        Provides full release information including exact release date.
        """
        data = self._make_request(f"releases/{release_id}")
        if not data:
            return None

        release_details = {
            "id": data.get("id"),
            "title": data.get("title"),
            "released": data.get("released"),  # Full release date (YYYY-MM-DD)
            "released_formatted": data.get("released_formatted"),
            "year": data.get("year"),
            "artists": [
                {"name": artist.get("name"), "id": artist.get("id")}
                for artist in data.get("artists", [])
            ],
            "genres": data.get("genres", []),
            "styles": data.get("styles", []),
            "labels": [
                {"name": label.get("name"), "catno": label.get("catno")}
                for label in data.get("labels", [])
            ],
            "formats": data.get("formats", []),
            "country": data.get("country"),
            "tracklist": [
                {"position": track.get("position"), "title": track.get("title")}
                for track in data.get("tracklist", [])
            ],
            "uri": data.get("uri"),
            "resource_url": data.get("resource_url"),
        }

        return release_details

    def get_track_release_date(
        self, track_name: str, artist_name: str
    ) -> Optional[Dict]:
        """
        Get the release date for a specific track.
        Returns a dict with year and full release date if available.
        Prefers album releases over singles to provide better album metadata.
        """
        # Search for releases
        releases = self.search_release(track_name, artist_name, limit=10)
        if not releases:
            logger.debug(
                f"No releases found for '{track_name}' by '{artist_name}' on Discogs"
            )
            return None

        # Prefer album releases over singles for better metadata
        # Albums provide more context and are more useful for library organization
        album_releases = [
            r
            for r in releases
            if any("album" in str(fmt).lower() for fmt in r.get("format", []))
        ]
        single_releases = [
            r
            for r in releases
            if any("single" in str(fmt).lower() for fmt in r.get("format", []))
        ]

        # Prioritize: albums first, then singles, then any other releases
        if album_releases:
            best_release = album_releases[0]
            logger.debug(f"Selected album release: {best_release.get('title')}")
        elif single_releases:
            best_release = single_releases[0]
            logger.debug(f"Selected single release: {best_release.get('title')}")
        else:
            best_release = releases[0]
            logger.debug(
                f"Selected first available release: {best_release.get('title')}"
            )

        # If we have a release ID, get detailed information for exact release date
        release_id = best_release.get("id")
        if release_id:
            details = self.get_release_details(release_id)
            if details:
                released = details.get("released")  # YYYY-MM-DD format
                year = details.get("year")

                if released or year:
                    result = {
                        "release_date": released,  # Full date if available
                        "year": year,
                        "title": details.get("title"),
                        "genres": details.get("genres", []),
                        "styles": details.get("styles", []),
                        "country": details.get("country"),
                        "confidence": best_release.get("confidence", 0.7),
                    }

                    logger.info(
                        f"Found Discogs release date for '{track_name}': {released or year}"
                    )
                    return result

        # Fallback to just year from search results
        year = best_release.get("year")
        if year:
            result = {
                "release_date": None,
                "year": year,
                "title": best_release.get("title"),
                "genres": best_release.get("genre", []),
                "confidence": best_release.get("confidence", 0.7),
            }

            logger.info(
                f"Found Discogs release year for '{track_name}': {year} (confidence: {result['confidence']:.2f})"
            )
            return result

        logger.debug(f"No release date found for '{track_name}' by '{artist_name}'")
        return None

    def search_artist(self, artist_name: str, limit: int = 10) -> List[Dict]:
        """
        Search for artists by name in Discogs database.
        Returns list of matching artists with metadata.
        """
        if not artist_name:
            return []

        params = {
            "q": artist_name,
            "type": "artist",
            "per_page": limit,
        }

        data = self._make_request("database/search", params)
        if not data or "results" not in data:
            return []

        artists = []
        for artist in data.get("results", []):
            artist_info = {
                "id": artist.get("id"),
                "name": artist.get("title"),
                "uri": artist.get("uri"),
                "resource_url": artist.get("resource_url"),
                "type": artist.get("type"),
                "confidence": self._calculate_name_similarity(
                    artist_name, artist.get("title", "")
                ),
            }

            artists.append(artist_info)

        # Sort by confidence
        artists.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        logger.debug(f"Found {len(artists)} artists matching '{artist_name}'")
        return artists

    def get_artist_details(self, artist_id: int) -> Optional[Dict]:
        """Get detailed information about a specific artist by ID"""
        data = self._make_request(f"artists/{artist_id}")
        if not data:
            return None

        artist_details = {
            "id": data.get("id"),
            "name": data.get("name"),
            "realname": data.get("realname"),
            "profile": data.get("profile"),
            "members": [
                {"name": member.get("name"), "id": member.get("id")}
                for member in data.get("members", [])
            ],
            "aliases": [
                {"name": alias.get("name"), "id": alias.get("id")}
                for alias in data.get("aliases", [])
            ],
            "urls": data.get("urls", []),
            "images": data.get("images", []),
            "uri": data.get("uri"),
            "resource_url": data.get("resource_url"),
        }

        return artist_details

    def test_connection(self) -> bool:
        """Test Discogs API connectivity"""
        try:
            if not self.enabled:
                logger.warning("Discogs is disabled, test connection returning False")
                return False

            # Simple test query - search for a well-known artist
            data = self._make_request(
                "database/search", params={"q": "The Beatles", "type": "artist"}
            )

            # Check if we got a valid response with results
            if data and "results" in data:
                logger.info("Discogs connection test successful")
                return True
            else:
                logger.warning("Discogs connection test failed - no results returned")
                return False

        except Exception as e:
            logger.error(f"Discogs connection test failed: {e}")
            return False


# Singleton instance
discogs_service = DiscogsService()
