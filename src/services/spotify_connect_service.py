"""
Spotify Connect integration service for playback control
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from src.services.spotify_service import spotify_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.spotify_connect")


class SpotifyConnectService:
    """Service for Spotify Connect playback control"""

    def __init__(self):
        self.base_url = "https://api.spotify.com/v1/me/player"
        self._cached_devices = []
        self._last_device_fetch = None
        self._cache_duration = 30  # seconds

    def _make_request(
        self, endpoint: str = "", method: str = "GET", data: Dict = None
    ) -> Dict:
        """Make authenticated request to Spotify Connect API"""
        spotify_service._ensure_valid_token()

        headers = {
            "Authorization": f"Bearer {spotify_service.access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/{endpoint}" if endpoint else self.base_url

        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Handle 204 No Content responses (common for player endpoints)
            if response.status_code == 204:
                return {"success": True}

            if response.status_code == 404:
                return {"error": "No active device found"}

            response.raise_for_status()

            # Some endpoints return empty response
            try:
                return response.json()
            except:
                return {"success": True}

        except requests.RequestException as e:
            logger.error(f"Spotify Connect API request failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_data = e.response.json()
                    return {"error": error_data.get("error", {}).get("message", str(e))}
                except:
                    return {"error": str(e)}
            return {"error": str(e)}

    def get_available_devices(self, refresh_cache: bool = False) -> Dict:
        """Get available Spotify Connect devices"""
        try:
            # Check cache first
            now = time.time()
            if (
                not refresh_cache
                and self._cached_devices
                and self._last_device_fetch
                and (now - self._last_device_fetch) < self._cache_duration
            ):
                return {"devices": self._cached_devices, "cached": True}

            response = self._make_request("devices")

            if "error" in response:
                return response

            devices = response.get("devices", [])

            # Update cache
            self._cached_devices = devices
            self._last_device_fetch = now

            logger.info(f"Found {len(devices)} available Spotify devices")
            return {"devices": devices, "cached": False}

        except Exception as e:
            logger.error(f"Failed to get available devices: {e}")
            return {"error": str(e)}

    def get_playback_state(self) -> Dict:
        """Get current playback state"""
        try:
            response = self._make_request()

            if "error" in response:
                return response

            # Handle case when no playback is active
            if not response:
                return {
                    "is_playing": False,
                    "device": None,
                    "track": None,
                    "message": "No active playback",
                }

            return response

        except Exception as e:
            logger.error(f"Failed to get playback state: {e}")
            return {"error": str(e)}

    def transfer_playback(self, device_id: str, force_play: bool = False) -> Dict:
        """Transfer playback to specified device"""
        try:
            data = {"device_ids": [device_id], "play": force_play}

            response = self._make_request("", method="PUT", data=data)

            if "success" in response:
                logger.info(f"Playback transferred to device: {device_id}")
                # Clear device cache to force refresh
                self._cached_devices = []

            return response

        except Exception as e:
            logger.error(f"Failed to transfer playback: {e}")
            return {"error": str(e)}

    def play_track(self, track_uri: str, device_id: str = None) -> Dict:
        """Play a specific track"""
        try:
            data = {"uris": [track_uri]}

            endpoint = "play"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="PUT", data=data)

            if "success" in response:
                logger.info(f"Started playing track: {track_uri}")

            return response

        except Exception as e:
            logger.error(f"Failed to play track: {e}")
            return {"error": str(e)}

    def play_playlist(
        self, playlist_uri: str, device_id: str = None, offset: int = 0
    ) -> Dict:
        """Play a playlist"""
        try:
            data = {"context_uri": playlist_uri}

            if offset > 0:
                data["offset"] = {"position": offset}

            endpoint = "play"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="PUT", data=data)

            if "success" in response:
                logger.info(f"Started playing playlist: {playlist_uri}")

            return response

        except Exception as e:
            logger.error(f"Failed to play playlist: {e}")
            return {"error": str(e)}

    def pause_playback(self, device_id: str = None) -> Dict:
        """Pause current playback"""
        try:
            endpoint = "pause"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info("Playback paused")

            return response

        except Exception as e:
            logger.error(f"Failed to pause playback: {e}")
            return {"error": str(e)}

    def resume_playback(self, device_id: str = None) -> Dict:
        """Resume current playback"""
        try:
            endpoint = "play"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info("Playback resumed")

            return response

        except Exception as e:
            logger.error(f"Failed to resume playback: {e}")
            return {"error": str(e)}

    def skip_to_next(self, device_id: str = None) -> Dict:
        """Skip to next track"""
        try:
            endpoint = "next"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="POST")

            if "success" in response:
                logger.info("Skipped to next track")

            return response

        except Exception as e:
            logger.error(f"Failed to skip to next: {e}")
            return {"error": str(e)}

    def skip_to_previous(self, device_id: str = None) -> Dict:
        """Skip to previous track"""
        try:
            endpoint = "previous"
            if device_id:
                endpoint += f"?device_id={device_id}"

            response = self._make_request(endpoint, method="POST")

            if "success" in response:
                logger.info("Skipped to previous track")

            return response

        except Exception as e:
            logger.error(f"Failed to skip to previous: {e}")
            return {"error": str(e)}

    def set_volume(self, volume_percent: int, device_id: str = None) -> Dict:
        """Set playback volume (0-100)"""
        try:
            if not 0 <= volume_percent <= 100:
                return {"error": "Volume must be between 0 and 100"}

            endpoint = f"volume?volume_percent={volume_percent}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info(f"Volume set to {volume_percent}%")

            return response

        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
            return {"error": str(e)}

    def set_repeat_mode(self, state: str, device_id: str = None) -> Dict:
        """Set repeat mode ('track', 'context', 'off')"""
        try:
            if state not in ["track", "context", "off"]:
                return {"error": "Repeat state must be 'track', 'context', or 'off'"}

            endpoint = f"repeat?state={state}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info(f"Repeat mode set to: {state}")

            return response

        except Exception as e:
            logger.error(f"Failed to set repeat mode: {e}")
            return {"error": str(e)}

    def set_shuffle_mode(self, state: bool, device_id: str = None) -> Dict:
        """Set shuffle mode"""
        try:
            endpoint = f"shuffle?state={'true' if state else 'false'}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info(f"Shuffle mode set to: {'on' if state else 'off'}")

            return response

        except Exception as e:
            logger.error(f"Failed to set shuffle mode: {e}")
            return {"error": str(e)}

    def seek_to_position(self, position_ms: int, device_id: str = None) -> Dict:
        """Seek to position in current track"""
        try:
            if position_ms < 0:
                return {"error": "Position must be non-negative"}

            endpoint = f"seek?position_ms={position_ms}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            response = self._make_request(endpoint, method="PUT")

            if "success" in response:
                logger.info(f"Seeked to position: {position_ms}ms")

            return response

        except Exception as e:
            logger.error(f"Failed to seek to position: {e}")
            return {"error": str(e)}

    def get_recently_played(self, limit: int = 20) -> Dict:
        """Get recently played tracks"""
        try:
            endpoint = f"recently-played?limit={min(limit, 50)}"
            response = self._make_request(endpoint)

            if "error" in response:
                return response

            return response

        except Exception as e:
            logger.error(f"Failed to get recently played: {e}")
            return {"error": str(e)}

    def add_to_queue(self, track_uri: str, device_id: str = None) -> Dict:
        """Add track to the user's playback queue"""
        try:
            endpoint = f"queue?uri={track_uri}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            response = self._make_request(endpoint, method="POST")

            if "success" in response:
                logger.info(f"Added track to queue: {track_uri}")

            return response

        except Exception as e:
            logger.error(f"Failed to add to queue: {e}")
            return {"error": str(e)}


# Global instance
spotify_connect_service = SpotifyConnectService()
