"""
OAuth authentication service for MVidarr
Supports multiple OAuth providers including Authentik, Google, GitHub, etc.
"""

import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

from src.database.connection import get_db
from src.database.models import User, UserRole, UserSession
from src.utils.logger import get_logger

logger = get_logger("mvidarr.oauth")

# Default timeout for HTTP requests (in seconds)
DEFAULT_REQUEST_TIMEOUT = 30

# Short-lived server-side store for OAuth CSRF state. No cookie needed —
# the state token round-trips through the provider's own redirect back to
# our callback URL. Replaces the old flask_session-based storage, which
# always failed (no Flask request context exists in this FastAPI-only
# process) — see #312.
_oauth_states: Dict[str, Dict[str, Any]] = {}
_OAUTH_STATE_EXPIRY_MINUTES = 10


def _cleanup_expired_oauth_states() -> None:
    now = datetime.utcnow()
    expired = [
        state for state, data in _oauth_states.items() if data["expires_at"] < now
    ]
    for state in expired:
        _oauth_states.pop(state, None)


class OAuthError(Exception):
    """OAuth related errors"""

    pass


class OAuthProvider:
    """Base OAuth provider class"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.redirect_uri = config.get("redirect_uri")
        self.scope = config.get("scope", "openid email profile")
        self.authorize_url = config.get("authorize_url")
        self.token_url = config.get("token_url")
        self.userinfo_url = config.get("userinfo_url")
        self.issuer = config.get("issuer")

    def get_authorization_url(self, state: str = None) -> str:
        """Generate OAuth authorization URL"""
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }

        return f"{self.authorize_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, state: str = None) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        if state:
            data["state"] = state

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(
            self.token_url, data=data, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        return response.json()

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from OAuth provider"""
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(
            self.userinfo_url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        return response.json()


class AuthentikProvider(OAuthProvider):
    """Authentik OAuth provider"""

    def __init__(self, config: Dict[str, Any]):
        # Authentik-specific configuration
        base_url = config.get("base_url", "").rstrip("/")

        authentik_config = {
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "redirect_uri": config.get("redirect_uri"),
            "scope": config.get("scope", "openid email profile groups"),
            "authorize_url": f"{base_url}/application/o/authorize/",
            "token_url": f"{base_url}/application/o/token/",
            "userinfo_url": f"{base_url}/application/o/userinfo/",
            "issuer": base_url,
        }

        super().__init__("authentik", authentik_config)
        self.base_url = base_url

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from Authentik"""
        user_info = super().get_user_info(access_token)

        # Map Authentik user info to standard format
        return {
            "id": user_info.get("sub"),
            "username": user_info.get("preferred_username", user_info.get("nickname")),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "given_name": user_info.get("given_name"),
            "family_name": user_info.get("family_name"),
            "groups": user_info.get("groups", []),
            "roles": user_info.get("roles", []),
            "avatar": user_info.get("picture"),
            "verified": user_info.get("email_verified", False),
        }

    def map_groups_to_role(self, groups: list, roles: list = None) -> UserRole:
        """Map Authentik groups/roles to MVidarr user role"""
        # Default role mapping - can be configured
        admin_groups = ["mvidarr_admin", "admins", "administrators"]
        manager_groups = ["mvidarr_manager", "managers", "moderators"]
        user_groups = ["mvidarr_user", "users"]

        # Check all groups and roles
        all_memberships = groups + (roles or [])

        for membership in all_memberships:
            membership_lower = membership.lower()
            if any(admin_group in membership_lower for admin_group in admin_groups):
                return UserRole.ADMIN
            elif any(
                manager_group in membership_lower for manager_group in manager_groups
            ):
                return UserRole.MANAGER
            elif any(user_group in membership_lower for user_group in user_groups):
                return UserRole.USER

        # Default to readonly if no matching groups
        return UserRole.READONLY


class GoogleProvider(OAuthProvider):
    """Google OAuth provider"""

    def __init__(self, config: Dict[str, Any]):
        google_config = {
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "redirect_uri": config.get("redirect_uri"),
            "scope": "openid email profile",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
            "issuer": "https://accounts.google.com",
        }

        super().__init__("google", google_config)

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from Google"""
        user_info = super().get_user_info(access_token)

        return {
            "id": user_info.get("id"),
            "username": (
                user_info.get("email").split("@")[0] if user_info.get("email") else None
            ),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "given_name": user_info.get("given_name"),
            "family_name": user_info.get("family_name"),
            "avatar": user_info.get("picture"),
            "verified": user_info.get("verified_email", False),
        }


class GitHubProvider(OAuthProvider):
    """GitHub OAuth provider"""

    def __init__(self, config: Dict[str, Any]):
        github_config = {
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "redirect_uri": config.get("redirect_uri"),
            "scope": "user:email",
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "issuer": "https://github.com",
        }

        super().__init__("github", github_config)

    def exchange_code_for_token(self, code: str, state: str = None) -> Dict[str, Any]:
        """Exchange authorization code for access token (GitHub specific)"""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
        }

        headers = {"Accept": "application/json"}

        response = requests.post(
            self.token_url, data=data, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        return response.json()

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from GitHub"""
        headers = {"Authorization": f"token {access_token}"}

        # Get user info
        user_response = requests.get(
            self.userinfo_url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        user_response.raise_for_status()
        user_info = user_response.json()

        # Get user email (GitHub may not return email in user info)
        email_response = requests.get(
            "https://api.github.com/user/emails",
            headers=headers,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )
        emails = email_response.json() if email_response.status_code == 200 else []

        primary_email = None
        for email in emails:
            if email.get("primary"):
                primary_email = email.get("email")
                break

        return {
            "id": str(user_info.get("id")),
            "username": user_info.get("login"),
            "email": primary_email or user_info.get("email"),
            "name": user_info.get("name"),
            "avatar": user_info.get("avatar_url"),
            "verified": any(
                email.get("verified") for email in emails if email.get("primary")
            ),
        }


class OAuthService:
    """OAuth authentication service"""

    def __init__(self):
        self.providers = {}
        self._load_providers()

    def _load_providers(self):
        """Load OAuth providers from configuration"""
        try:
            from src.services.settings_service import SettingsService

            # Load Authentik configuration
            authentik_config = {
                "base_url": SettingsService.get("oauth_authentik_base_url"),
                "client_id": SettingsService.get("oauth_authentik_client_id"),
                "client_secret": SettingsService.get("oauth_authentik_client_secret"),
                "redirect_uri": SettingsService.get("oauth_authentik_redirect_uri"),
            }

            if all(authentik_config.values()):
                self.providers["authentik"] = AuthentikProvider(authentik_config)
                logger.info("Authentik OAuth provider configured")

            # Load Google configuration
            google_config = {
                "client_id": SettingsService.get("oauth_google_client_id"),
                "client_secret": SettingsService.get("oauth_google_client_secret"),
                "redirect_uri": SettingsService.get("oauth_google_redirect_uri"),
            }

            if all(google_config.values()):
                self.providers["google"] = GoogleProvider(google_config)
                logger.info("Google OAuth provider configured")

            # Load GitHub configuration
            github_config = {
                "client_id": SettingsService.get("oauth_github_client_id"),
                "client_secret": SettingsService.get("oauth_github_client_secret"),
                "redirect_uri": SettingsService.get("oauth_github_redirect_uri"),
            }

            if all(github_config.values()):
                self.providers["github"] = GitHubProvider(github_config)
                logger.info("GitHub OAuth provider configured")

        except Exception as e:
            logger.error(f"Error loading OAuth providers: {e}")

    def get_provider(self, provider_name: str) -> Optional[OAuthProvider]:
        """Get OAuth provider by name"""
        return self.providers.get(provider_name)

    def get_available_providers(self) -> Dict[str, str]:
        """Get list of available OAuth providers"""
        return {name: provider.name for name, provider in self.providers.items()}

    def initiate_oauth_flow(
        self, provider_name: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Initiate OAuth authentication flow

        Args:
            provider_name: Name of OAuth provider

        Returns:
            Tuple of (success, message/auth_url, state)
        """
        try:
            provider = self.get_provider(provider_name)
            if not provider:
                return False, f"OAuth provider '{provider_name}' not configured", None

            # Generate state for CSRF protection
            state = secrets.token_urlsafe(32)

            # Store state server-side (see _oauth_states above)
            _cleanup_expired_oauth_states()
            _oauth_states[state] = {
                "provider": provider_name,
                "expires_at": datetime.utcnow()
                + timedelta(minutes=_OAUTH_STATE_EXPIRY_MINUTES),
            }

            # Generate authorization URL
            auth_url = provider.get_authorization_url(state)

            logger.info(f"OAuth flow initiated for provider: {provider_name}")
            return True, auth_url, state

        except Exception as e:
            logger.error(f"Error initiating OAuth flow: {e}")
            return False, "Failed to initiate OAuth flow", None

    def handle_oauth_callback(
        self,
        provider_name: str,
        code: str,
        state: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[User], Optional[UserSession]]:
        """
        Handle OAuth callback and authenticate user

        Args:
            provider_name: Name of OAuth provider
            code: Authorization code from provider
            state: State parameter for CSRF protection
            ip_address: Client IP address for the new session (from the
                real FastAPI Request; this service has no Flask request
                context to read it from itself)
            user_agent: Client User-Agent header for the new session

        Returns:
            Tuple of (success, message, user, session)
        """
        try:
            # Verify state for CSRF protection
            _cleanup_expired_oauth_states()
            stored = _oauth_states.get(state)

            if not stored:
                return (
                    False,
                    "Invalid or expired state parameter - possible CSRF attack",
                    None,
                    None,
                )

            if stored["provider"] != provider_name:
                return False, "Provider mismatch", None, None

            # Get provider
            provider = self.get_provider(provider_name)
            if not provider:
                return (
                    False,
                    f"OAuth provider '{provider_name}' not configured",
                    None,
                    None,
                )

            # Exchange code for token
            token_response = provider.exchange_code_for_token(code, state)
            access_token = token_response.get("access_token")

            if not access_token:
                return False, "Failed to obtain access token", None, None

            # Get user information
            user_info = provider.get_user_info(access_token)

            # Find or create user
            user, session_obj = self._find_or_create_oauth_user(
                provider_name, user_info, ip_address=ip_address, user_agent=user_agent
            )

            if user and session_obj:
                # Clear used state
                _oauth_states.pop(state, None)

                logger.info(
                    f"OAuth authentication successful for user: {user.username}"
                )
                return True, "Authentication successful", user, session_obj
            else:
                return False, "Failed to create or find user", None, None

        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")
            return False, "OAuth authentication failed", None, None

    def _find_or_create_oauth_user(
        self,
        provider_name: str,
        user_info: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[Optional[User], Optional[UserSession]]:
        """
        Find existing user or create new user from OAuth info

        Args:
            provider_name: Name of OAuth provider
            user_info: User information from OAuth provider
            ip_address: Client IP address for the new session
            user_agent: Client User-Agent header for the new session

        Returns:
            Tuple of (user, session)
        """
        try:
            with get_db() as session:
                email = user_info.get("email")
                username = user_info.get("username")
                oauth_id = user_info.get("id")

                if not email and not username:
                    logger.error("OAuth user info missing email and username")
                    return None, None

                # Try to find existing user by email first
                user = None
                if email:
                    user = session.query(User).filter_by(email=email).first()

                # If not found by email, try by username
                if not user and username:
                    user = session.query(User).filter_by(username=username).first()

                # Create new user if not found
                if not user:
                    # Generate username if not provided
                    if not username:
                        username = (
                            email.split("@")[0] if email else f"oauth_user_{oauth_id}"
                        )

                    # Ensure username is unique
                    base_username = username
                    counter = 1
                    while session.query(User).filter_by(username=username).first():
                        username = f"{base_username}_{counter}"
                        counter += 1

                    # Determine user role based on provider
                    user_role = UserRole.USER
                    if provider_name == "authentik" and isinstance(
                        self.providers[provider_name], AuthentikProvider
                    ):
                        groups = user_info.get("groups", [])
                        roles = user_info.get("roles", [])
                        user_role = self.providers[provider_name].map_groups_to_role(
                            groups, roles
                        )

                    # Create user
                    user = User(
                        username=username,
                        email=email or f"{username}@oauth.local",
                        password=secrets.token_urlsafe(
                            32
                        ),  # Random password (OAuth users don't use it)
                        role=user_role,
                    )

                    # Mark email as verified if OAuth provider confirms it
                    if user_info.get("verified"):
                        user.is_email_verified = True

                    # Store OAuth provider info in preferences
                    user.preferences = {
                        "oauth_provider": provider_name,
                        "oauth_id": oauth_id,
                        "oauth_avatar": user_info.get("avatar"),
                        "oauth_name": user_info.get("name"),
                    }

                    session.add(user)
                    session.flush()  # Get user ID

                    logger.info(
                        f"Created new OAuth user: {username} from {provider_name}"
                    )

                else:
                    # Update existing user's OAuth info
                    if not user.preferences:
                        user.preferences = {}

                    user.preferences.update(
                        {
                            "oauth_provider": provider_name,
                            "oauth_id": oauth_id,
                            "oauth_avatar": user_info.get("avatar"),
                            "oauth_name": user_info.get("name"),
                        }
                    )

                    # Update role for Authentik users based on current groups
                    if provider_name == "authentik" and isinstance(
                        self.providers[provider_name], AuthentikProvider
                    ):
                        groups = user_info.get("groups", [])
                        roles = user_info.get("roles", [])
                        new_role = self.providers[provider_name].map_groups_to_role(
                            groups, roles
                        )
                        if new_role != user.role:
                            logger.info(
                                f"Updated user role for {user.username}: {user.role.value} -> {new_role.value}"
                            )
                            user.role = new_role

                # Update last login
                user.last_login = datetime.utcnow()
                user.last_login_ip = ip_address

                # Create session
                user_session = UserSession(
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.add(user_session)
                session.commit()

                return user, user_session

        except Exception as e:
            logger.error(f"Error finding/creating OAuth user: {e}")
            return None, None

    def is_oauth_enabled(self) -> bool:
        """Check if any OAuth providers are configured"""
        return len(self.providers) > 0

    def get_oauth_login_urls(self) -> Dict[str, str]:
        """Get OAuth login URLs for all configured providers"""
        urls = {}
        for provider_name in self.providers:
            success, auth_url, state = self.initiate_oauth_flow(provider_name)
            if success:
                urls[provider_name] = auth_url
        return urls


# Global OAuth service instance
oauth_service = OAuthService()
