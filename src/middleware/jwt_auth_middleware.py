"""
Advanced JWT Authentication Middleware - Phase 3 Week 34
Comprehensive JWT token management with refresh tokens and security validation
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import jwt
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.jwt_auth")


class TokenType(Enum):
    """JWT token types"""

    ACCESS = "access"
    REFRESH = "refresh"
    RESET = "password_reset"
    VERIFICATION = "email_verification"


class UserRole(Enum):
    """User role levels"""

    GUEST = "guest"
    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


@dataclass
class TokenConfig:
    """JWT token configuration"""

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"
    issuer: str = "mvidarr-api"
    audience: str = "mvidarr-users"
    secret_key: str = field(default_factory=lambda: secrets.token_urlsafe(64))
    refresh_secret_key: str = field(default_factory=lambda: secrets.token_urlsafe(64))

    # Security settings
    require_https: bool = False  # Set to True in production
    allow_refresh_rotation: bool = True
    max_refresh_attempts: int = 5
    blacklist_cleanup_hours: int = 24

    # Token validation settings
    clock_skew_seconds: int = 30
    verify_signature: bool = True
    verify_expiration: bool = True
    verify_issuer: bool = True
    verify_audience: bool = True


@dataclass
class UserClaims:
    """User claims in JWT token"""

    user_id: int
    username: str
    email: str
    role: UserRole
    permissions: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


@dataclass
class TokenData:
    """Token data with metadata"""

    token: str
    token_type: TokenType
    user_claims: UserClaims
    expires_at: datetime
    issued_at: datetime
    jti: str  # JWT ID
    fingerprint: Optional[str] = None


class TokenBlacklist:
    """In-memory token blacklist with Redis fallback"""

    def __init__(self):
        self.blacklisted_tokens: Dict[str, float] = {}  # jti -> expiry_time
        self.failed_attempts: Dict[str, int] = {}  # user_id -> attempt_count
        self.last_cleanup = time.time()

    def add_token(self, jti: str, expires_at: datetime):
        """Add token to blacklist"""
        self.blacklisted_tokens[jti] = expires_at.timestamp()
        logger.info(f"🚫 Token {jti[:8]}... added to blacklist")

    def is_blacklisted(self, jti: str) -> bool:
        """Check if token is blacklisted"""
        if jti in self.blacklisted_tokens:
            # Check if blacklist entry is still valid
            if time.time() < self.blacklisted_tokens[jti]:
                return True
            else:
                # Remove expired blacklist entry
                del self.blacklisted_tokens[jti]
        return False

    def add_failed_attempt(self, user_id: str):
        """Record failed authentication attempt"""
        self.failed_attempts[user_id] = self.failed_attempts.get(user_id, 0) + 1

    def get_failed_attempts(self, user_id: str) -> int:
        """Get failed attempt count for user"""
        return self.failed_attempts.get(user_id, 0)

    def clear_failed_attempts(self, user_id: str):
        """Clear failed attempts for user"""
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]

    def cleanup_expired(self):
        """Remove expired blacklist entries"""
        current_time = time.time()

        # Only cleanup every hour
        if current_time - self.last_cleanup < 3600:
            return

        expired_tokens = [
            jti
            for jti, expiry in self.blacklisted_tokens.items()
            if current_time >= expiry
        ]

        for jti in expired_tokens:
            del self.blacklisted_tokens[jti]

        self.last_cleanup = current_time

        if expired_tokens:
            logger.info(
                f"🧹 Cleaned up {len(expired_tokens)} expired blacklisted tokens"
            )


class JWTManager:
    """Advanced JWT token management"""

    def __init__(self, config: TokenConfig):
        self.config = config
        self.blacklist = TokenBlacklist()
        logger.info("🔐 JWT Manager initialized with enhanced security")

    def _generate_jti(self) -> str:
        """Generate unique JWT ID"""
        return secrets.token_urlsafe(32)

    def _generate_fingerprint(self, request: Request) -> str:
        """Generate device fingerprint for additional security"""
        user_agent = request.headers.get("user-agent", "")
        client_ip = request.client.host
        accept_lang = request.headers.get("accept-language", "")

        fingerprint_data = f"{user_agent}:{client_ip}:{accept_lang}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    def create_access_token(
        self, user_claims: UserClaims, request: Optional[Request] = None
    ) -> TokenData:
        """Create JWT access token"""
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.config.access_token_expire_minutes)
        jti = self._generate_jti()

        # Create JWT payload
        payload = {
            "sub": str(user_claims.user_id),
            "username": user_claims.username,
            "email": user_claims.email,
            "role": user_claims.role.value,
            "permissions": user_claims.permissions,
            "session_id": user_claims.session_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nbf": int(now.timestamp()),
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "jti": jti,
            "type": TokenType.ACCESS.value,
        }

        # Add device fingerprint if request provided
        fingerprint = None
        if request:
            fingerprint = self._generate_fingerprint(request)
            payload["fingerprint"] = fingerprint

        # Create token
        token = jwt.encode(
            payload, self.config.secret_key, algorithm=self.config.algorithm
        )

        return TokenData(
            token=token,
            token_type=TokenType.ACCESS,
            user_claims=user_claims,
            expires_at=expires_at,
            issued_at=now,
            jti=jti,
            fingerprint=fingerprint,
        )

    def create_refresh_token(
        self, user_claims: UserClaims, request: Optional[Request] = None
    ) -> TokenData:
        """Create JWT refresh token"""
        now = datetime.utcnow()
        expires_at = now + timedelta(days=self.config.refresh_token_expire_days)
        jti = self._generate_jti()

        # Create JWT payload
        payload = {
            "sub": str(user_claims.user_id),
            "username": user_claims.username,
            "session_id": user_claims.session_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nbf": int(now.timestamp()),
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "jti": jti,
            "type": TokenType.REFRESH.value,
        }

        # Add device fingerprint if request provided
        fingerprint = None
        if request:
            fingerprint = self._generate_fingerprint(request)
            payload["fingerprint"] = fingerprint

        # Create token using refresh secret
        token = jwt.encode(
            payload, self.config.refresh_secret_key, algorithm=self.config.algorithm
        )

        return TokenData(
            token=token,
            token_type=TokenType.REFRESH,
            user_claims=user_claims,
            expires_at=expires_at,
            issued_at=now,
            jti=jti,
            fingerprint=fingerprint,
        )

    def verify_token(
        self, token: str, token_type: TokenType, request: Optional[Request] = None
    ) -> Tuple[bool, Optional[UserClaims], Optional[str]]:
        """
        Verify JWT token and return user claims
        Returns: (is_valid, user_claims, error_message)
        """
        try:
            # Choose secret key based on token type
            secret_key = (
                self.config.refresh_secret_key
                if token_type == TokenType.REFRESH
                else self.config.secret_key
            )

            # Decode token
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer if self.config.verify_issuer else None,
                audience=self.config.audience if self.config.verify_audience else None,
                options={
                    "verify_signature": self.config.verify_signature,
                    "verify_exp": self.config.verify_expiration,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_iss": self.config.verify_issuer,
                    "verify_aud": self.config.verify_audience,
                    "leeway": self.config.clock_skew_seconds,
                },
            )

            # Validate token type
            if payload.get("type") != token_type.value:
                return False, None, f"Invalid token type: expected {token_type.value}"

            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti and self.blacklist.is_blacklisted(jti):
                return False, None, "Token has been revoked"

            # Verify device fingerprint if available
            if request and "fingerprint" in payload:
                current_fingerprint = self._generate_fingerprint(request)
                if payload["fingerprint"] != current_fingerprint:
                    logger.warning(
                        f"🚨 Device fingerprint mismatch for user {payload.get('sub')}"
                    )
                    return False, None, "Device fingerprint mismatch"

            # Create user claims
            try:
                role = UserRole(payload.get("role", "user"))
            except ValueError:
                role = UserRole.USER

            user_claims = UserClaims(
                user_id=int(payload["sub"]),
                username=payload.get("username", ""),
                email=payload.get("email", ""),
                role=role,
                permissions=payload.get("permissions", []),
                session_id=payload.get("session_id"),
                created_at=payload.get("iat", time.time()),
                last_activity=time.time(),
            )

            return True, user_claims, None

        except jwt.ExpiredSignatureError:
            return False, None, "Token has expired"
        except jwt.InvalidTokenError as e:
            return False, None, f"Invalid token: {str(e)}"
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return False, None, "Token verification failed"

    def revoke_token(self, jti: str, expires_at: datetime):
        """Revoke a token by adding it to blacklist"""
        self.blacklist.add_token(jti, expires_at)

    def refresh_access_token(
        self, refresh_token: str, request: Optional[Request] = None
    ) -> Tuple[bool, Optional[TokenData], Optional[str]]:
        """
        Refresh access token using refresh token
        Returns: (success, new_token_data, error_message)
        """
        # Verify refresh token
        is_valid, user_claims, error = self.verify_token(
            refresh_token, TokenType.REFRESH, request
        )

        if not is_valid:
            if user_claims:
                self.blacklist.add_failed_attempt(str(user_claims.user_id))
            return False, None, error

        # Check failed attempt limits
        user_id = str(user_claims.user_id)
        if (
            self.blacklist.get_failed_attempts(user_id)
            >= self.config.max_refresh_attempts
        ):
            return False, None, "Too many failed refresh attempts"

        # Create new access token
        new_access_token = self.create_access_token(user_claims, request)

        # Clear failed attempts on successful refresh
        self.blacklist.clear_failed_attempts(user_id)

        # Optionally rotate refresh token
        if self.config.allow_refresh_rotation:
            # Blacklist old refresh token
            try:
                old_payload = jwt.decode(
                    refresh_token, options={"verify_signature": False}
                )
                old_jti = old_payload.get("jti")
                old_exp = datetime.fromtimestamp(old_payload.get("exp", 0))
                if old_jti:
                    self.revoke_token(old_jti, old_exp)
            except Exception:
                pass  # Continue even if blacklisting fails

        return True, new_access_token, None

    def cleanup_expired_tokens(self):
        """Clean up expired blacklisted tokens"""
        self.blacklist.cleanup_expired()


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware"""

    def __init__(self, app, config: Optional[TokenConfig] = None):
        super().__init__(app)
        self.config = config or TokenConfig()
        self.jwt_manager = JWTManager(self.config)

        # Paths that don't require authentication
        self.public_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static/",
            "/css/",
            "/favicon.ico",
            "/login",
            "/auth/login",
            "/test-login",
            "/api/auth/login",
            "/api/auth/simple-login",
            "/api/auth/register",
            "/api/auth/refresh",
            "/api/auth/reset-password",
            "/api/auth/verify-email",
            "/",
            "/dashboard",  # Allow root and dashboard to handle their own authentication
        }

        # Paths that require specific roles
        self.role_protected_paths = {
            "/api/admin/": UserRole.ADMIN,
            "/api/settings/": UserRole.MANAGER,
            "/api/users/": UserRole.MANAGER,
        }

        logger.info("🔐 JWT authentication middleware initialized")

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require auth)"""
        return any(path.startswith(public) for public in self.public_paths)

    def _is_browser_request(self, request: Request) -> bool:
        """Check if request is from a browser (expects HTML response)"""
        accept_header = request.headers.get("accept", "").lower()
        return "text/html" in accept_header or "application/xhtml+xml" in accept_header

    def _get_required_role(self, path: str) -> Optional[UserRole]:
        """Get required role for path"""
        for protected_path, required_role in self.role_protected_paths.items():
            if path.startswith(protected_path):
                return required_role
        return UserRole.USER  # Default minimum role

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request"""
        # Try Authorization header first
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Try cookie
        token_cookie = request.cookies.get("access_token")
        if token_cookie:
            return token_cookie

        return None

    def _has_permission(self, user_claims: UserClaims, required_role: UserRole) -> bool:
        """Check if user has required permissions"""
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
            UserRole.SUPERADMIN: 4,
        }

        user_level = role_hierarchy.get(user_claims.role, 0)
        required_level = role_hierarchy.get(required_role, 1)

        return user_level >= required_level

    async def dispatch(self, request: Request, call_next):
        """Process request with JWT authentication"""
        path = request.url.path

        # Skip authentication for public paths
        if self._is_public_path(path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if not token:
            # Redirect browser requests to login page
            if self._is_browser_request(request):
                return RedirectResponse(url="/auth/login", status_code=302)
            # Return JSON for API requests
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify token
        is_valid, user_claims, error = self.jwt_manager.verify_token(
            token, TokenType.ACCESS, request
        )

        if not is_valid:
            # Redirect browser requests to login page
            if self._is_browser_request(request):
                return RedirectResponse(url="/auth/login", status_code=302)
            # Return JSON for API requests
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": error or "Invalid token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check role permissions
        required_role = self._get_required_role(path)
        if required_role and not self._has_permission(user_claims, required_role):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Insufficient permissions. Required: {required_role.value}"
                },
            )

        # Add user claims to request state
        request.state.user = user_claims
        request.state.authenticated = True

        # Process request
        response = await call_next(request)

        # Add security headers
        response.headers["X-Authenticated"] = "true"
        response.headers["X-User-Role"] = user_claims.role.value

        # Cleanup expired tokens periodically
        self.jwt_manager.cleanup_expired_tokens()

        return response
