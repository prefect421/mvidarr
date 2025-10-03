"""
Redis Connection and Management for Background Jobs
Phase 2: Media Processing Optimization - Redis Infrastructure
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis

from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.redis_manager")


class RedisManager:
    """Manages Redis connections and operations for background jobs"""

    def __init__(self, redis_url: Optional[str] = None, auto_connect: bool = False):
        self.redis_url = redis_url or os.environ.get(
            "REDIS_URL", os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        )
        self.redis_client = None
        self.connection_pool = None
        self._connected = False

        # Only auto-connect if explicitly requested
        if auto_connect:
            self._initialize_connection()

    def _initialize_connection(self):
        """Initialize Redis connection with connection pooling"""
        if self._connected:
            return True

        try:
            # Create connection pool for better performance
            self.connection_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
            )

            # Create Redis client with connection pool
            self.redis_client = redis.Redis(
                connection_pool=self.connection_pool,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Test connection
            self.redis_client.ping()
            self._connected = True
            logger.info("Redis connection established successfully")
            return True

        except redis.RedisError as e:
            logger.warning(f"Redis connection failed: {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"Unexpected error connecting to Redis: {e}")
            self._connected = False
            return False

    def ensure_connection(self):
        """Ensure Redis connection is available, attempt to connect if not"""
        if not self._connected:
            return self._initialize_connection()
        return True

    def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health"""
        try:
            # Test basic operations
            start_time = time.time()
            self.redis_client.ping()
            response_time = time.time() - start_time

            # Get Redis info
            info = self.redis_client.info()

            return {
                "status": "healthy",
                "response_time_ms": round(response_time * 1000, 2),
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
            }

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    # Job Progress Tracking
    def set_job_progress(
        self, job_id: str, progress: Dict[str, Any], expire_seconds: int = 3600
    ):
        """Set job progress information"""
        if not self.ensure_connection():
            logger.debug(f"Redis unavailable, skipping job progress for {job_id}")
            return False

        try:
            key = f"job_progress:{job_id}"
            progress_data = {
                **progress,
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.redis_client.setex(key, expire_seconds, json.dumps(progress_data))

            # Also publish to progress channel for real-time updates
            self.redis_client.publish(f"progress:{job_id}", json.dumps(progress_data))

            return True

        except Exception as e:
            logger.error(f"Error setting job progress for {job_id}: {e}")
            return False

    def get_job_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job progress information"""
        try:
            key = f"job_progress:{job_id}"
            progress_data = self.redis_client.get(key)

            if progress_data:
                return json.loads(progress_data)
            return None

        except Exception as e:
            logger.error(f"Error getting job progress for {job_id}: {e}")
            return None

    def delete_job_progress(self, job_id: str) -> bool:
        """Delete job progress information"""
        try:
            key = f"job_progress:{job_id}"
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Error deleting job progress for {job_id}: {e}")
            return False

    # Job Status Management
    def set_job_status(
        self,
        job_id: str,
        status: str,
        details: Dict[str, Any] = None,
        expire_seconds: int = 3600,
    ):
        """Set job status information"""
        try:
            key = f"job_status:{job_id}"
            status_data = {
                "job_id": job_id,
                "status": status,
                "details": details or {},
                "updated_at": datetime.utcnow().isoformat(),
            }

            self.redis_client.setex(key, expire_seconds, json.dumps(status_data))

            # Publish status update
            self.redis_client.publish(f"status:{job_id}", json.dumps(status_data))

            return True

        except Exception as e:
            logger.error(f"Error setting job status for {job_id}: {e}")
            return False

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status information"""
        try:
            key = f"job_status:{job_id}"
            status_data = self.redis_client.get(key)

            if status_data:
                return json.loads(status_data)
            return None

        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {e}")
            return None

    # Job Results Storage
    def store_job_result(
        self, job_id: str, result: Dict[str, Any], expire_seconds: int = 7200
    ):
        """Store job result"""
        try:
            key = f"job_result:{job_id}"
            result_data = {
                "job_id": job_id,
                "result": result,
                "completed_at": datetime.utcnow().isoformat(),
            }

            self.redis_client.setex(key, expire_seconds, json.dumps(result_data))

            return True

        except Exception as e:
            logger.error(f"Error storing job result for {job_id}: {e}")
            return False

    def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job result"""
        try:
            key = f"job_result:{job_id}"
            result_data = self.redis_client.get(key)

            if result_data:
                return json.loads(result_data)
            return None

        except Exception as e:
            logger.error(f"Error getting job result for {job_id}: {e}")
            return None

    # Caching Operations
    def cache_set(self, key: str, value: Any, expire_seconds: int = 3600):
        """Set cache value"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            return self.redis_client.setex(key, expire_seconds, value)
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False

    def cache_get(self, key: str, parse_json: bool = False) -> Optional[Any]:
        """Get cache value"""
        try:
            value = self.redis_client.get(key)

            if value and parse_json:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value

            return value

        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    def cache_delete(self, key: str) -> bool:
        """Delete cache key"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    # Pub/Sub Operations
    def publish_message(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish message to channel"""
        try:
            message_data = {**message, "timestamp": datetime.utcnow().isoformat()}

            self.redis_client.publish(channel, json.dumps(message_data))
            return True

        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}")
            return False

    def subscribe_to_channel(self, channel: str):
        """Subscribe to a channel (returns pubsub object)"""
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Error subscribing to channel {channel}: {e}")
            return None

    # Utility Operations
    def get_all_job_keys(self, pattern: str = "job_*:*") -> List[str]:
        """Get all job-related keys"""
        try:
            return self.redis_client.keys(pattern)
        except Exception as e:
            logger.error(f"Error getting job keys: {e}")
            return []

    def cleanup_expired_jobs(self):
        """Clean up expired job data"""
        try:
            # Get all job keys
            job_keys = self.get_all_job_keys()

            cleaned_count = 0
            for key in job_keys:
                # Check if key exists (may have expired)
                if not self.redis_client.exists(key):
                    cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} expired job keys")
            return cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning up expired jobs: {e}")
            return 0

    def get_redis_stats(self) -> Dict[str, Any]:
        """Get Redis usage statistics"""
        try:
            info = self.redis_client.info()

            return {
                "memory_usage": {
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "used_memory_peak": info.get("used_memory_peak", 0),
                },
                "connections": {
                    "connected_clients": info.get("connected_clients", 0),
                    "total_connections_received": info.get(
                        "total_connections_received", 0
                    ),
                },
                "commands": {
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "instantaneous_ops_per_sec": info.get(
                        "instantaneous_ops_per_sec", 0
                    ),
                },
                "keys": {
                    "total_keys": sum(
                        info.get(f"db{i}", {}).get("keys", 0) for i in range(16)
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            return {}

    def close_connection(self):
        """Close Redis connection"""
        try:
            if self.connection_pool:
                self.connection_pool.disconnect()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    # Async Methods for better integration
    async def set_json(
        self, key: str, value: Dict[str, Any], ttl: Optional[int] = None
    ):
        """Async version of JSON set operation"""
        if not self.ensure_connection():
            return False

        try:
            json_value = json.dumps(value)
            if ttl:
                return self.redis_client.setex(key, ttl, json_value)
            else:
                return self.redis_client.set(key, json_value)
        except Exception as e:
            logger.error(f"Error setting JSON key {key}: {e}")
            return False

    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Async version of JSON get operation"""
        if not self.ensure_connection():
            return None

        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting JSON key {key}: {e}")
            return None

    async def publish_json(self, channel: str, data: Dict[str, Any]):
        """Async version of JSON publish operation"""
        if not self.ensure_connection():
            return False

        try:
            json_data = json.dumps(data)
            self.redis_client.publish(channel, json_data)
            return True
        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}")
            return False


# Global Redis manager instance (without auto-connection)
redis_manager = RedisManager(auto_connect=False)


# Convenience functions
def set_job_progress(job_id: str, progress: Dict[str, Any], expire_seconds: int = 3600):
    """Set job progress (convenience function)"""
    return redis_manager.set_job_progress(job_id, progress, expire_seconds)


def get_job_progress(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job progress (convenience function)"""
    return redis_manager.get_job_progress(job_id)


def set_job_status(
    job_id: str, status: str, details: Dict[str, Any] = None, expire_seconds: int = 3600
):
    """Set job status (convenience function)"""
    return redis_manager.set_job_status(job_id, status, details, expire_seconds)


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status (convenience function)"""
    return redis_manager.get_job_status(job_id)


# Health check function
def check_redis_health() -> Dict[str, Any]:
    """Check Redis health (convenience function)"""
    return redis_manager.health_check()


if __name__ == "__main__":
    # For testing: python -m src.jobs.redis_manager
    print("Redis Manager Test")
    print("=" * 50)

    # Test connection and health
    health = check_redis_health()
    print(f"Redis Health: {health}")

    if health["status"] == "healthy":
        # Test basic operations
        print("\nTesting basic operations...")

        # Test job progress
        job_id = "test_job_123"
        progress = {"percent": 50, "message": "Processing..."}
        set_job_progress(job_id, progress)
        retrieved_progress = get_job_progress(job_id)
        print(f"Job Progress: {retrieved_progress}")

        # Test caching
        redis_manager.cache_set("test_key", {"test": "data"}, 60)
        cached_data = redis_manager.cache_get("test_key", parse_json=True)
        print(f"Cached Data: {cached_data}")

        # Get stats
        stats = redis_manager.get_redis_stats()
        print(f"\nRedis Stats: {stats}")

        print("\n✅ Redis Manager test completed successfully!")
    else:
        print("❌ Redis connection failed!")
