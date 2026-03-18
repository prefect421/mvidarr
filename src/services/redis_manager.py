"""
Simplified Redis Manager - Phase 3 Week 33
Basic Redis operations for MVidarr caching system
"""

from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("mvidarr.redis_manager")


class RedisManager:
    """Simplified Redis manager for MVidarr performance caching"""

    def __init__(self):
        self.redis_client = None
        self._connected = False

    async def _ensure_connection(self):
        """Ensure Redis connection is available"""
        if not self._connected:
            try:
                import os

                import redis.asyncio as redis

                redis_url = os.environ.get(
                    "REDIS_URL",
                    os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
                )
                redis_password = os.environ.get("REDIS_PASSWORD")
                connect_kwargs = {
                    "decode_responses": True,
                    "socket_connect_timeout": 5,
                }
                # If password is set and not already in the URL, add it
                if redis_password and "@" not in redis_url:
                    connect_kwargs["password"] = redis_password
                self.redis_client = redis.Redis.from_url(
                    redis_url,
                    **connect_kwargs,
                )
                # Test connection
                await self.redis_client.ping()
                self._connected = True
                logger.info("✅ Redis connection established")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None
                self._connected = False

    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                return await self.redis_client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
        return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set value in Redis with optional TTL"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                if ttl:
                    await self.redis_client.setex(key, ttl, value)
                else:
                    await self.redis_client.set(key, value)
                return True
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
        return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                return bool(await self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
        return False

    async def lpush(self, key: str, value: str) -> bool:
        """Push value to left of list"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                await self.redis_client.lpush(key, value)
                return True
        except Exception as e:
            logger.error(f"Redis LPUSH error for key {key}: {e}")
        return False

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim list to specified range"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                await self.redis_client.ltrim(key, start, stop)
                return True
        except Exception as e:
            logger.error(f"Redis LTRIM error for key {key}: {e}")
        return False

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
        return False

    async def keys(self, pattern: str = "*") -> list:
        """Get keys matching pattern"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                return await self.redis_client.keys(pattern)
        except Exception as e:
            logger.error(f"Redis KEYS error for pattern {pattern}: {e}")
        return []

    async def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            await self._ensure_connection()
            if self.redis_client:
                await self.redis_client.ping()
                return True
        except Exception:
            pass
        return False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False
            logger.info("Redis connection closed")


# Global Redis manager instance
redis_manager = RedisManager()


async def get_redis_manager() -> RedisManager:
    """Get the global Redis manager instance"""
    return redis_manager
