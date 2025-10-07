"""
Redis Service Wrapper - Phase 3 Week 29 Integration
Provides a simple Redis client interface for Week 29 services
"""

import asyncio
import json
from typing import Any, Optional

from src.services.redis_manager import RedisManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.redis_service")

# Global Redis manager instance
_redis_manager = None


async def get_redis_client():
    """Get Redis client for caching and data storage"""
    global _redis_manager

    if _redis_manager is None:
        _redis_manager = RedisManager()

    return _redis_manager


async def init_redis_service():
    """Initialize Redis service"""
    try:
        client = await get_redis_client()
        logger.info("Redis service initialized successfully")
        return client
    except Exception as e:
        logger.warning(f"Redis service initialization failed: {e}")
        return None
