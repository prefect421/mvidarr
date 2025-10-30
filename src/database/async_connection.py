"""
Async Database Connection Manager - Phase 3 Week 33
High-performance async database operations with advanced connection pooling for FastAPI
"""

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import QueuePool

from src.utils.logger import get_logger

logger = get_logger("mvidarr.database.async_connection")


class AsyncDatabaseManager:
    """High-performance async database connection manager with advanced monitoring"""

    def __init__(self):
        self.engine: AsyncEngine = None
        self.async_session_factory: async_sessionmaker = None
        self._initialized = False
        self.connection_stats = {
            "queries_executed": 0,
            "total_query_time": 0.0,
            "slow_queries": 0,
            "connection_errors": 0,
            "pool_checkouts": 0,
        }

    async def initialize(self, database_url: str):
        """Initialize async database engine and session factory"""
        if self._initialized:
            logger.debug("Async database already initialized")
            return

        try:
            # Convert MySQL URL to async format
            if database_url.startswith("mysql+pymysql://"):
                async_database_url = database_url.replace(
                    "mysql+pymysql://", "mysql+aiomysql://"
                )
            elif database_url.startswith("mysql://"):
                async_database_url = database_url.replace(
                    "mysql://", "mysql+aiomysql://"
                )
            else:
                async_database_url = database_url

            logger.info(f"Initializing async database connection")

            # Create async engine with production-optimized settings
            self.engine = create_async_engine(
                async_database_url,
                # Enhanced connection pool settings for high performance
                poolclass=QueuePool,
                pool_size=25,  # Increased for FastAPI concurrency
                max_overflow=35,  # Higher burst capacity
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=7200,  # Recycle connections after 2 hours
                pool_timeout=20,  # Reduced timeout for faster failover
                # Performance optimizations
                echo=False,  # Disable for production performance
                future=True,  # Use SQLAlchemy 2.0 style
                # Additional async optimizations
                connect_args={
                    "server_side_cursors": True,  # Reduce memory usage for large result sets
                    "autocommit": False,  # Explicit transaction control
                    "charset": "utf8mb4",
                },
            )

            # Create async session factory
            self.async_session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,  # Important for async operations
                autoflush=False,  # Manual control over flushing
                autocommit=False,  # Explicit transaction management
            )

            # Test the connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            self._initialized = True
            logger.info("✅ Async database initialized successfully")
            logger.info(f"Connection pool size: {self.engine.pool.size()}")

        except Exception as e:
            logger.error(f"Failed to initialize async database: {e}")
            raise

    async def get_session(self) -> AsyncSession:
        """Get an async database session"""
        if not self._initialized:
            raise RuntimeError(
                "Async database not initialized. Call initialize() first."
            )

        return self.async_session_factory()

    @asynccontextmanager
    async def session_scope(self):
        """
        Async context manager for database sessions with automatic cleanup
        Usage:
            async with db_manager.session_scope() as session:
                # Use session here
                result = await session.execute(select(User))
        """
        session = await self.get_session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    async def execute_query(
        self, query: str, params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Execute raw SQL query and return results with performance tracking"""
        start_time = time.time()

        try:
            if not self._initialized:
                await initialize_async_database()

            async with self.engine.begin() as conn:
                result = await conn.execute(text(query), params or {})
                rows = await result.fetchall()

                # Convert to list of dictionaries
                if rows:
                    columns = result.keys()
                    data = [dict(zip(columns, row)) for row in rows]
                else:
                    data = []

            # Track performance
            query_time = time.time() - start_time
            self.connection_stats["queries_executed"] += 1
            self.connection_stats["total_query_time"] += query_time

            if query_time > 0.1:  # Log slow queries (>100ms)
                self.connection_stats["slow_queries"] += 1
                logger.warning(
                    f"🐌 Slow query: {query[:100]}... took {query_time:.3f}s"
                )

            return data

        except Exception as e:
            self.connection_stats["connection_errors"] += 1
            logger.error(f"Query execution failed: {e}")
            raise

    async def execute_scalar(self, query: str, params: Optional[Dict] = None) -> Any:
        """Execute query and return single scalar value"""
        try:
            if not self._initialized:
                await initialize_async_database()

            async with self.engine.begin() as conn:
                result = await conn.execute(text(query), params or {})
                return await result.scalar()
        except Exception as e:
            self.connection_stats["connection_errors"] += 1
            logger.error(f"Scalar query failed: {e}")
            raise

    async def bulk_insert(self, table_name: str, records: List[Dict[str, Any]]) -> int:
        """Perform optimized bulk insert with transaction management"""
        if not records:
            return 0

        start_time = time.time()

        try:
            if not self._initialized:
                await initialize_async_database()

            # Build bulk insert query
            columns = list(records[0].keys())
            placeholders = ", ".join([f":{col}" for col in columns])
            query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

            async with self.engine.begin() as conn:
                result = await conn.execute(text(query), records)
                inserted_count = result.rowcount

            bulk_time = time.time() - start_time
            logger.info(
                f"📦 Bulk inserted {inserted_count} records into {table_name} in {bulk_time:.3f}s"
            )

            return inserted_count

        except Exception as e:
            self.connection_stats["connection_errors"] += 1
            logger.error(f"Bulk insert failed: {e}")
            raise

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get detailed connection pool statistics"""
        if not self.engine:
            return {}

        try:
            pool = self.engine.pool
            stats = {
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "checked_in": pool.checkedin(),
                "invalid": pool.invalid(),
                "total_connections": pool.size() + pool.overflow(),
                "utilization": pool.checkedout() / max(pool.size(), 1),
                **self.connection_stats,
            }

            # Add average query time
            if stats["queries_executed"] > 0:
                stats["avg_query_time"] = (
                    stats["total_query_time"] / stats["queries_executed"]
                )
            else:
                stats["avg_query_time"] = 0.0

            return stats

        except Exception as e:
            logger.error(f"Failed to get pool stats: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive database health check with performance metrics"""
        try:
            start_time = time.time()

            if not self._initialized:
                await initialize_async_database()

            # Test basic connectivity
            async with self.engine.begin() as conn:
                result = await conn.execute(
                    text("SELECT 1 as health_check, NOW() as current_time")
                )
                test_result = await result.fetchone()

            response_time = time.time() - start_time

            # Get pool statistics
            pool_stats = await self.get_pool_stats()

            # Determine health status
            is_healthy = (
                response_time < 1.0
                and pool_stats.get("utilization", 0) < 0.8
                and self.connection_stats.get("connection_errors", 0)
                / max(self.connection_stats.get("queries_executed", 1), 1)
                < 0.01
            )

            return {
                "status": "healthy" if is_healthy else "degraded",
                "response_time": f"{response_time:.3f}s",
                "database_time": str(test_result.current_time) if test_result else None,
                "pool_stats": pool_stats,
                "connection_errors": self.connection_stats.get("connection_errors", 0),
                "total_queries": self.connection_stats.get("queries_executed", 0),
                "slow_queries": self.connection_stats.get("slow_queries", 0),
            }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "connection_errors": self.connection_stats.get("connection_errors", 0),
            }

    async def close(self):
        """Close the database engine and all connections"""
        if self.engine:
            await self.engine.dispose()
            self._initialized = False
            logger.info("✅ Async database connections closed cleanly")

            # Log final statistics
            stats = self.connection_stats
            if stats["queries_executed"] > 0:
                avg_time = stats["total_query_time"] / stats["queries_executed"]
                logger.info(
                    f"📊 Final DB stats: {stats['queries_executed']} queries, {avg_time:.3f}s avg, {stats['slow_queries']} slow"
                )


# Global async database manager instance
async_db_manager = AsyncDatabaseManager()


async def get_async_database_url():
    """Get the async database URL from environment/config"""
    # Import here to avoid circular imports
    try:
        from src.config.config import Config

        config = Config()

        # Build the async database URL using the same pattern as sync
        sync_url = (
            f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
            f"?charset=utf8mb4"
        )

        # Convert to async URL
        if sync_url.startswith("mysql+pymysql://"):
            return sync_url.replace("mysql+pymysql://", "mysql+aiomysql://")
        elif sync_url.startswith("mysql://"):
            return sync_url.replace("mysql://", "mysql+aiomysql://")
        else:
            return sync_url
    except Exception as e:
        logger.error(f"Error getting database URL from config: {e}")
        # Fallback to environment variables
        import os
        from urllib.parse import quote_plus

        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        username = os.getenv("DB_USER", "mvidarr")
        password = os.getenv("DB_PASSWORD", "change_me_to_your_password")
        database = os.getenv("DB_NAME", "mvidarr")

        # URL encode the password to handle special characters
        encoded_password = quote_plus(password)

        return f"mysql+aiomysql://{username}:{encoded_password}@{host}:{port}/{database}?charset=utf8mb4"


async def initialize_async_database():
    """Initialize the global async database manager"""
    database_url = await get_async_database_url()
    await async_db_manager.initialize(database_url)


# FastAPI dependency for getting async database sessions
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting async database sessions
    Usage in FastAPI routes:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    if not async_db_manager._initialized:
        await initialize_async_database()

    async with async_db_manager.session_scope() as session:
        yield session


# Utility function for manual session management
async def get_async_session() -> AsyncSession:
    """Get an async session for manual management (remember to close!)"""
    if not async_db_manager._initialized:
        await initialize_async_database()

    return await async_db_manager.get_session()


# Health check function
async def check_async_database_health():
    """Check if async database connection is healthy with detailed metrics"""
    try:
        if not async_db_manager._initialized:
            await initialize_async_database()

        return await async_db_manager.health_check()

    except Exception as e:
        logger.error(f"Async database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database": "async_connection_failed",
        }


# Query optimization utilities
class AsyncQueryOptimizer:
    """Utilities for optimizing async database queries"""

    @staticmethod
    async def analyze_query_performance(
        query: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Analyze query performance using EXPLAIN"""
        try:
            explain_query = f"EXPLAIN {query}"
            explain_result = await async_db_manager.execute_query(explain_query, params)

            return {
                "explain_plan": explain_result,
                "estimated_rows": sum(row.get("rows", 0) for row in explain_result),
                "uses_index": any(
                    "Using index" in str(row.get("Extra", "")) for row in explain_result
                ),
                "has_filesort": any(
                    "Using filesort" in str(row.get("Extra", ""))
                    for row in explain_result
                ),
                "query": query[:200] + "..." if len(query) > 200 else query,
            }

        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            return {"error": str(e)}

    @staticmethod
    async def suggest_optimizations(table_name: str) -> List[str]:
        """Suggest query optimizations for a table"""
        suggestions = []

        try:
            # Check for missing indexes
            index_query = """
                SELECT DISTINCT 
                    COLUMN_NAME,
                    CARDINALITY,
                    INDEX_NAME
                FROM INFORMATION_SCHEMA.STATISTICS 
                WHERE TABLE_NAME = :table_name 
                AND TABLE_SCHEMA = DATABASE()
                ORDER BY CARDINALITY DESC
            """

            indexes = await async_db_manager.execute_query(
                index_query, {"table_name": table_name}
            )

            if len(indexes) < 3:
                suggestions.append(f"Consider adding more indexes to {table_name}")

            # Check table stats
            stats_query = f"SHOW TABLE STATUS LIKE '{table_name}'"
            table_stats = await async_db_manager.execute_query(stats_query)

            if table_stats:
                stats = table_stats[0]
                if stats.get("Rows", 0) > 100000:
                    suggestions.append(
                        f"Large table {table_name} ({stats['Rows']} rows) - consider partitioning"
                    )

                if stats.get("Data_free", 0) > 1024 * 1024:  # 1MB
                    suggestions.append(
                        f"Table {table_name} has fragmentation - consider OPTIMIZE TABLE"
                    )

                # Check for full table scans
                if stats.get("Rows", 0) > 10000 and len(indexes) < 2:
                    suggestions.append(
                        f"Table {table_name} may have full table scan issues - add indexes on commonly queried columns"
                    )

        except Exception as e:
            logger.error(f"Optimization analysis failed for {table_name}: {e}")
            suggestions.append(f"Error analyzing {table_name}: {str(e)}")

        return suggestions


# Cached query decorator for frequent database calls
def cache_database_query(ttl: int = 300, key_prefix: str = "db_query"):
    """Decorator to cache database query results with Redis"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                # Generate cache key from function name and arguments
                import hashlib

                from src.services.media_cache_manager import MediaCacheManager

                key_parts = [key_prefix, func.__name__]

                # Add non-self arguments to cache key
                for arg in args[1:]:  # Skip 'self' argument
                    if isinstance(arg, (str, int, float, bool)):
                        key_parts.append(str(arg))

                for k, v in kwargs.items():
                    if isinstance(v, (str, int, float, bool)):
                        key_parts.append(f"{k}:{v}")

                cache_key_string = "|".join(key_parts)
                cache_key_hash = hashlib.md5(cache_key_string.encode(), usedforsecurity=False).hexdigest()
                final_key = f"{key_prefix}:{cache_key_hash}"

                # Try to get from cache
                cache_manager = MediaCacheManager()
                cached = await cache_manager.get(final_key)
                if cached:
                    import json

                    logger.debug(f"🎯 Database query cache HIT: {func.__name__}")
                    return json.loads(cached)

                # Execute function and cache result
                logger.debug(f"💾 Database query cache MISS: {func.__name__}")
                result = await func(*args, **kwargs)

                # Cache the result
                await cache_manager.set(
                    final_key, json.dumps(result, default=str), ttl=ttl
                )

                return result

            except Exception as e:
                logger.warning(f"Database query caching error for {func.__name__}: {e}")
                # Fallback to direct execution
                return await func(*args, **kwargs)

        return wrapper

    return decorator


# Utility function to get the global async database manager
async def get_async_db_manager() -> AsyncDatabaseManager:
    """Get the global async database manager with initialization check"""
    if not async_db_manager._initialized:
        await initialize_async_database()
    return async_db_manager
