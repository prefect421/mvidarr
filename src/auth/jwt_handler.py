"""
JWT Token Handler for FastAPI Authentication
Manages JWT token generation, validation, and refresh functionality
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext

from src.services.async_base_service import AsyncBaseService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.auth.jwt_handler")


class JWTHandler(AsyncBaseService):
    """JWT token handler for authentication"""

    def __init__(self):
        super().__init__("mvidarr.jwt_handler")

        # JWT Configuration
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 120  # 2 hours
        self.refresh_token_expire_days = 7  # 7 days

        # Password hashing
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # Lazy initialization to avoid database calls at import time
        self._secret_key = None
        self._refresh_secret_key = None

    async def _get_secret_key(self) -> str:
        """Get or generate JWT secret key"""
        if self._secret_key:
            return self._secret_key

        try:
            # Try to get from settings
            key_query = "SELECT setting_value FROM settings WHERE setting_key = 'jwt_secret_key'"
            result = await self.execute_query(key_query)

            if result and result[0]["setting_value"]:
                self._secret_key = result[0]["setting_value"]
                self.logger.debug("JWT secret key loaded from database")
            else:
                # Generate new secret key
                self._secret_key = secrets.token_urlsafe(64)

                # Save to database
                insert_query = """
                    INSERT INTO settings (setting_key, setting_value) 
                    VALUES ('jwt_secret_key', %s)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                """
                await self.execute_query(insert_query, [self._secret_key])
                self.logger.info("Generated and saved new JWT secret key")

        except Exception as e:
            # Fallback to environment or generated key
            self.logger.warning(f"Failed to load/save JWT secret key: {e}")
            self._secret_key = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(64)

        return self._secret_key

    async def _get_refresh_secret_key(self) -> str:
        """Get or generate JWT refresh secret key"""
        if self._refresh_secret_key:
            return self._refresh_secret_key

        try:
            # Try to get from settings
            key_query = "SELECT setting_value FROM settings WHERE setting_key = 'jwt_refresh_secret_key'"
            result = await self.execute_query(key_query)

            if result and result[0]["setting_value"]:
                self._refresh_secret_key = result[0]["setting_value"]
                self.logger.debug("JWT refresh secret key loaded from database")
            else:
                # Generate new refresh secret key
                self._refresh_secret_key = secrets.token_urlsafe(64)

                # Save to database
                insert_query = """
                    INSERT INTO settings (setting_key, setting_value) 
                    VALUES ('jwt_refresh_secret_key', %s)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                """
                await self.execute_query(insert_query, [self._refresh_secret_key])
                self.logger.info("Generated and saved new JWT refresh secret key")

        except Exception as e:
            # Fallback to environment or generated key
            self.logger.warning(f"Failed to load/save JWT refresh secret key: {e}")
            self._refresh_secret_key = os.getenv(
                "JWT_REFRESH_SECRET_KEY"
            ) or secrets.token_urlsafe(64)

        return self._refresh_secret_key

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            return self.pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            self.logger.error(f"Password verification error: {e}")
            return False

    async def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token"""
        try:
            to_encode = data.copy()

            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(
                    minutes=self.access_token_expire_minutes
                )

            to_encode.update(
                {"exp": expire, "iat": datetime.utcnow(), "type": "access"}
            )

            secret_key = await self._get_secret_key()
            encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=self.algorithm)

            self.logger.debug(
                f"Created access token for user: {data.get('sub', 'unknown')}"
            )
            return encoded_jwt

        except Exception as e:
            self.logger.error(f"Error creating access token: {e}")
            raise

    async def create_refresh_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT refresh token"""
        try:
            to_encode = data.copy()

            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(
                    days=self.refresh_token_expire_days
                )

            to_encode.update(
                {"exp": expire, "iat": datetime.utcnow(), "type": "refresh"}
            )

            refresh_secret_key = await self._get_refresh_secret_key()
            encoded_jwt = jwt.encode(
                to_encode, refresh_secret_key, algorithm=self.algorithm
            )

            self.logger.debug(
                f"Created refresh token for user: {data.get('sub', 'unknown')}"
            )
            return encoded_jwt

        except Exception as e:
            self.logger.error(f"Error creating refresh token: {e}")
            raise

    async def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT access token"""
        try:
            secret_key = await self._get_secret_key()
            payload = jwt.decode(token, secret_key, algorithms=[self.algorithm])

            # Check token type
            if payload.get("type") != "access":
                self.logger.warning("Invalid token type for access token")
                return None

            # Check expiration
            exp_timestamp = payload.get("exp")
            if (
                exp_timestamp
                and datetime.utcfromtimestamp(exp_timestamp) < datetime.utcnow()
            ):
                self.logger.debug("Access token expired")
                return None

            return payload

        except PyJWTError as e:
            self.logger.debug(f"JWT verification failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error verifying access token: {e}")
            return None

    async def verify_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT refresh token"""
        try:
            refresh_secret_key = await self._get_refresh_secret_key()
            payload = jwt.decode(token, refresh_secret_key, algorithms=[self.algorithm])

            # Check token type
            if payload.get("type") != "refresh":
                self.logger.warning("Invalid token type for refresh token")
                return None

            # Check expiration
            exp_timestamp = payload.get("exp")
            if (
                exp_timestamp
                and datetime.utcfromtimestamp(exp_timestamp) < datetime.utcnow()
            ):
                self.logger.debug("Refresh token expired")
                return None

            return payload

        except PyJWTError as e:
            self.logger.debug(f"Refresh token verification failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error verifying refresh token: {e}")
            return None

    async def refresh_access_token(
        self, refresh_token: str
    ) -> Optional[Dict[str, str]]:
        """Create new access token from valid refresh token"""
        try:
            payload = await self.verify_refresh_token(refresh_token)
            if not payload:
                return None

            # Create new access token with same user data
            user_data = {
                "sub": payload.get("sub"),
                "username": payload.get("username"),
                "user_id": payload.get("user_id"),
            }

            new_access_token = await self.create_access_token(user_data)

            return {"access_token": new_access_token, "token_type": "bearer"}

        except Exception as e:
            self.logger.error(f"Error refreshing access token: {e}")
            return None

    async def create_token_pair(
        self, username: str, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create both access and refresh tokens for a user"""
        try:
            user_data = {
                "sub": username,
                "username": username,
            }

            if user_id:
                user_data["user_id"] = user_id

            access_token = await self.create_access_token(user_data)
            refresh_token = await self.create_refresh_token(user_data)

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,
                "refresh_expires_in": self.refresh_token_expire_days * 24 * 60 * 60,
            }

        except Exception as e:
            self.logger.error(f"Error creating token pair: {e}")
            raise

    async def revoke_token(self, token: str) -> bool:
        """Add token to revocation list (blacklist)"""
        try:
            # Decode token to get expiration time
            payload = await self.verify_access_token(token)
            if not payload:
                # Try refresh token
                payload = await self.verify_refresh_token(token)

            if not payload:
                return False

            exp_timestamp = payload.get("exp")
            if not exp_timestamp:
                return False

            # Add to blacklist table (you'll need to create this table)
            blacklist_query = """
                INSERT INTO token_blacklist (token_hash, expires_at, created_at)
                VALUES (SHA2(%s, 256), FROM_UNIXTIME(%s), NOW())
                ON DUPLICATE KEY UPDATE created_at = NOW()
            """

            await self.execute_query(blacklist_query, [token, exp_timestamp])
            self.logger.info("Token added to blacklist")
            return True

        except Exception as e:
            self.logger.error(f"Error revoking token: {e}")
            return False

    async def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        try:
            blacklist_query = """
                SELECT 1 FROM token_blacklist 
                WHERE token_hash = SHA2(%s, 256) 
                AND expires_at > NOW()
            """

            result = await self.execute_query(blacklist_query, [token])
            return len(result) > 0

        except Exception as e:
            self.logger.error(f"Error checking token blacklist: {e}")
            return False

    async def cleanup_expired_tokens(self):
        """Clean up expired blacklisted tokens"""
        try:
            cleanup_query = "DELETE FROM token_blacklist WHERE expires_at <= NOW()"
            result = await self.execute_query(cleanup_query)

            # Log number of cleaned up tokens
            # Note: The exact way to get affected rows may vary by async driver
            self.logger.info("Cleaned up expired blacklisted tokens")

        except Exception as e:
            self.logger.error(f"Error cleaning up expired tokens: {e}")

    def is_password_strong(self, password: str) -> tuple[bool, str]:
        """Check if password meets strength requirements"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, "Password is strong"

    async def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get information about a token without verifying its signature"""
        try:
            # Decode without verification to get payload info
            unverified_payload = jwt.decode(token, options={"verify_signature": False})

            return {
                "username": unverified_payload.get("username"),
                "user_id": unverified_payload.get("user_id"),
                "expires_at": datetime.utcfromtimestamp(
                    unverified_payload.get("exp", 0)
                ),
                "issued_at": datetime.utcfromtimestamp(
                    unverified_payload.get("iat", 0)
                ),
                "token_type": unverified_payload.get("type"),
            }

        except Exception as e:
            self.logger.error(f"Error getting token info: {e}")
            return None


# Global JWT handler instance
jwt_handler = JWTHandler()


# Test function for the JWT handler
async def test_jwt_handler():
    """Test JWT handler functionality"""
    try:
        from src.database.async_connection import initialize_async_database

        print("🔄 Initializing async database...")
        await initialize_async_database()

        print("🔄 Testing JWT handler...")

        # Test password hashing
        password = "test_password_123"
        hashed = jwt_handler.hash_password(password)
        print(f"✅ Password hashed: {hashed[:20]}...")

        # Test password verification
        verified = jwt_handler.verify_password(password, hashed)
        print(f"✅ Password verification: {verified}")

        if not verified:
            print("❌ Password verification failed")
            return False

        # Test token creation
        token_pair = await jwt_handler.create_token_pair("test_user", 1)
        print(f"✅ Token pair created: {list(token_pair.keys())}")

        # Test access token verification
        access_token = token_pair["access_token"]
        payload = await jwt_handler.verify_access_token(access_token)
        print(f"✅ Access token verified: {payload}")

        if not payload:
            print("❌ Access token verification failed")
            return False

        print("✅ JWT handler basic functionality working!")
        return True

    except Exception as e:
        print(f"❌ JWT handler test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


# Global instance
_jwt_handler = None


async def get_jwt_handler() -> JWTHandler:
    """Get global JWT handler instance"""
    global _jwt_handler

    if _jwt_handler is None:
        _jwt_handler = JWTHandler()
        await _jwt_handler.initialize()

    return _jwt_handler


if __name__ == "__main__":
    """Run tests if executed directly"""
    import asyncio
    import os
    import sys

    # Add project root to path
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    async def main():
        print("🧪 Testing JWT Handler")
        print("=" * 40)

        success = await test_jwt_handler()

        print("=" * 40)
        if success:
            print("🎉 JWT Handler tests passed!")
        else:
            print("💥 JWT Handler tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
