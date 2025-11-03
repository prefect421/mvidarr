"""
IMVDb API client - Core HTTP client and authentication
"""

import time
from typing import Dict, Optional

import requests

from src.utils.logger import get_logger

logger = get_logger("mvidarr.imvdb_client")


class IMVDbClient:
    """Core HTTP client for IMVDb API interactions"""

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
