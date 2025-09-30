"""
YouTube OAuth2 Authentication Service
Complete solution for YouTube's 2025 bot detection using official OAuth2 flow
"""

import http.server
import json
import os
import socketserver
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.youtube_oauth")


class YouTubeOAuthService:
    """
    Handles YouTube OAuth2 authentication for legitimate API access
    This completely bypasses bot detection by using official YouTube API authentication
    """

    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = "http://localhost:8080/oauth/callback"
        self.oauth_server = None
        self.auth_code = None
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.oauth_cache_file = "data/oauth/youtube_oauth_tokens.json"

        # Load existing tokens
        self._load_cached_tokens()

        logger.info("YouTube OAuth2 service initialized")

    def setup_oauth_credentials(self, client_id: str, client_secret: str) -> bool:
        """
        Set up OAuth2 credentials (user must provide these from Google Console)
        """
        try:
            self.client_id = client_id
            self.client_secret = client_secret

            # Save to settings
            settings.set("youtube_oauth_client_id", client_id)
            settings.set("youtube_oauth_client_secret", client_secret)

            logger.info("OAuth2 credentials configured")
            return True

        except Exception as e:
            logger.error(f"Failed to setup OAuth credentials: {e}")
            return False

    def _load_cached_tokens(self):
        """Load cached OAuth tokens"""
        try:
            if os.path.exists(self.oauth_cache_file):
                with open(self.oauth_cache_file, "r") as f:
                    tokens = json.load(f)

                self.access_token = tokens.get("access_token")
                self.refresh_token = tokens.get("refresh_token")

                if tokens.get("expires_at"):
                    self.token_expires_at = datetime.fromisoformat(tokens["expires_at"])

                logger.info("Loaded cached OAuth tokens")

        except Exception as e:
            logger.warning(f"Could not load cached tokens: {e}")

    def _save_tokens(self):
        """Save OAuth tokens to cache"""
        try:
            os.makedirs(os.path.dirname(self.oauth_cache_file), exist_ok=True)

            tokens = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": (
                    self.token_expires_at.isoformat() if self.token_expires_at else None
                ),
                "created_at": datetime.now().isoformat(),
            }

            with open(self.oauth_cache_file, "w") as f:
                json.dump(tokens, f, indent=2)

            logger.info("Saved OAuth tokens to cache")

        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")

    def is_authenticated(self) -> bool:
        """Check if we have valid authentication"""
        if not self.access_token:
            return False

        if self.token_expires_at and datetime.now() >= self.token_expires_at:
            # Token expired, try to refresh
            return self.refresh_access_token()

        return True

    def start_oauth_flow(self) -> str:
        """
        Start OAuth2 authorization flow
        Returns authorization URL for user to visit
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("OAuth credentials not configured")

        # Start local server to receive callback
        self._start_callback_server()

        # Construct authorization URL
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            "scope=https://www.googleapis.com/auth/youtube.readonly&"
            "response_type=code&"
            "access_type=offline&"
            "prompt=consent"
        )

        logger.info(f"OAuth flow started, redirect URI: {self.redirect_uri}")
        return auth_url

    def _start_callback_server(self):
        """Start local server to handle OAuth callback"""

        class OAuthHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, oauth_service, *args, **kwargs):
                self.oauth_service = oauth_service
                super().__init__(*args, **kwargs)

            def do_GET(self):
                if "/oauth/callback" in self.path:
                    # Parse authorization code from callback
                    parsed_url = urlparse(self.path)
                    query_params = parse_qs(parsed_url.query)

                    if "code" in query_params:
                        self.oauth_service.auth_code = query_params["code"][0]

                        # Send success response
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            b"""
                            <html><body>
                            <h1>Authorization Successful!</h1>
                            <p>You can close this window and return to MVidarr.</p>
                            <script>window.close();</script>
                            </body></html>
                        """
                        )

                        logger.info("OAuth authorization code received")
                    else:
                        # Handle error
                        error = query_params.get("error", ["Unknown error"])[0]
                        logger.error(f"OAuth error: {error}")

                        self.send_response(400)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            f"<h1>Authorization Failed</h1><p>Error: {error}</p>".encode()
                        )
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress server logs

        # Bind handler to service instance
        handler = lambda *args, **kwargs: OAuthHandler(self, *args, **kwargs)

        self.oauth_server = socketserver.TCPServer(("localhost", 8080), handler)

        # Start server in background thread
        server_thread = threading.Thread(
            target=self.oauth_server.serve_forever, daemon=True
        )
        server_thread.start()

        logger.info("OAuth callback server started on localhost:8080")

    def complete_oauth_flow(self, timeout: int = 300) -> bool:
        """
        Wait for and complete OAuth flow
        Returns True if successful
        """
        start_time = time.time()

        while not self.auth_code and (time.time() - start_time) < timeout:
            time.sleep(1)

        if not self.auth_code:
            logger.error("OAuth flow timed out waiting for authorization code")
            return False

        # Exchange code for tokens
        return self._exchange_code_for_tokens()

    def _exchange_code_for_tokens(self) -> bool:
        """Exchange authorization code for access/refresh tokens"""
        try:
            import requests

            token_url = "https://oauth2.googleapis.com/token"

            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": self.auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            }

            response = requests.post(token_url, data=data)

            if response.status_code == 200:
                tokens = response.json()

                self.access_token = tokens["access_token"]
                self.refresh_token = tokens.get("refresh_token")

                # Calculate expiration
                expires_in = tokens.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

                self._save_tokens()

                logger.info("Successfully exchanged code for OAuth tokens")
                return True
            else:
                logger.error(
                    f"Token exchange failed: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error exchanging code for tokens: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh expired access token"""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            import requests

            token_url = "https://oauth2.googleapis.com/token"

            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }

            response = requests.post(token_url, data=data)

            if response.status_code == 200:
                tokens = response.json()

                self.access_token = tokens["access_token"]

                # Update expiration
                expires_in = tokens.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

                self._save_tokens()

                logger.info("Successfully refreshed access token")
                return True
            else:
                logger.error(
                    f"Token refresh failed: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False

    def get_authenticated_yt_dlp_args(self) -> list:
        """Get yt-dlp arguments for authenticated requests"""
        if not self.is_authenticated():
            logger.warning("Not authenticated, using fallback arguments")
            return self._get_fallback_args()

        return [
            "--add-header",
            f"Authorization:Bearer {self.access_token}",
            "--extractor-args",
            "youtube:player_client=tv,android",  # Use TV/Android clients for better format availability (web client forces SABR streaming)
        ]

    def _get_fallback_args(self) -> list:
        """Fallback arguments when OAuth is not available"""
        return [
            "--extractor-args",
            "youtube:player_client=tv,android,web",
            "--socket-timeout",
            "30",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--retry-sleep",
            "2",
        ]


# Global service instance
youtube_oauth_service = YouTubeOAuthService()
