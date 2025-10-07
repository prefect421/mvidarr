"""
Async Base Service for FastAPI Migration
Provides common async patterns and database access for all services
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.database.async_connection import async_db_manager, get_async_session
from src.utils.logger import get_logger

# Type variable for model types
ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class AsyncBaseService:
    """
    Base service class providing common async database operations
    All FastAPI services should inherit from this class
    """

    def __init__(self, logger_name: str = None):
        """Initialize base service with logger"""
        self.logger = get_logger(logger_name or f"mvidarr.{self.__class__.__name__}")

    @asynccontextmanager
    async def get_session(self):
        """Get an async database session with automatic cleanup"""
        async with async_db_manager.session_scope() as session:
            try:
                yield session
            except Exception as e:
                self.logger.error(
                    f"Database session error in {self.__class__.__name__}: {e}"
                )
                raise

    async def get_by_id(
        self, model: Type[ModelType], id: Any, session: AsyncSession = None
    ) -> Optional[ModelType]:
        """Get a single record by ID"""
        try:
            if session:
                result = await session.get(model, id)
                return result
            else:
                async with self.get_session() as session:
                    result = await session.get(model, id)
                    return result
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting {model.__name__} by ID {id}: {e}")
            raise

    async def get_all(
        self,
        model: Type[ModelType],
        limit: int = None,
        offset: int = None,
        session: AsyncSession = None,
    ) -> List[ModelType]:
        """Get all records with optional pagination"""
        try:
            query = select(model)

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            if session:
                result = await session.execute(query)
                return result.scalars().all()
            else:
                async with self.get_session() as session:
                    result = await session.execute(query)
                    return result.scalars().all()
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting all {model.__name__}: {e}")
            raise

    async def get_by_filter(self, model: Type[ModelType], **filters) -> List[ModelType]:
        """Get records by filter conditions"""
        try:
            query = select(model)

            for field, value in filters.items():
                if hasattr(model, field):
                    query = query.where(getattr(model, field) == value)

            async with self.get_session() as session:
                result = await session.execute(query)
                return result.scalars().all()
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error getting {model.__name__} by filter {filters}: {e}"
            )
            raise

    async def create(self, model: Type[ModelType], **data) -> ModelType:
        """Create a new record"""
        try:
            async with self.get_session() as session:
                instance = model(**data)
                session.add(instance)
                await session.flush()  # Get the ID without committing
                await session.refresh(instance)
                return instance
        except SQLAlchemyError as e:
            self.logger.error(f"Error creating {model.__name__}: {e}")
            raise

    async def update_by_id(
        self, model: Type[ModelType], id: Any, **data
    ) -> Optional[ModelType]:
        """Update a record by ID"""
        try:
            async with self.get_session() as session:
                instance = await session.get(model, id)
                if instance:
                    for field, value in data.items():
                        if hasattr(instance, field):
                            setattr(instance, field, value)
                    await session.flush()
                    await session.refresh(instance)
                    return instance
                return None
        except SQLAlchemyError as e:
            self.logger.error(f"Error updating {model.__name__} ID {id}: {e}")
            raise

    async def delete_by_id(self, model: Type[ModelType], id: Any) -> bool:
        """Delete a record by ID"""
        try:
            async with self.get_session() as session:
                instance = await session.get(model, id)
                if instance:
                    await session.delete(instance)
                    return True
                return False
        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting {model.__name__} ID {id}: {e}")
            raise

    async def count(self, model: Type[ModelType], **filters) -> int:
        """Count records with optional filters"""
        try:
            query = select(func.count(model.id))

            for field, value in filters.items():
                if hasattr(model, field):
                    query = query.where(getattr(model, field) == value)

            async with self.get_session() as session:
                result = await session.execute(query)
                return result.scalar() or 0
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting {model.__name__}: {e}")
            raise

    async def execute_query(self, query: str, params: Dict = None) -> List[Dict]:
        """Execute raw SQL query with parameters"""
        try:
            async with self.get_session() as session:
                result = await session.execute(text(query), params or {})

                # Convert result to list of dictionaries
                columns = result.keys() if hasattr(result, "keys") else []
                rows = []

                for row in result:
                    row_dict = {}
                    for i, column in enumerate(columns):
                        row_dict[column] = row[i] if i < len(row) else None
                    rows.append(row_dict)

                return rows
        except SQLAlchemyError as e:
            self.logger.error(f"Error executing query: {e}")
            raise

    async def bulk_create(
        self, model: Type[ModelType], data_list: List[Dict]
    ) -> List[ModelType]:
        """Create multiple records in bulk"""
        try:
            async with self.get_session() as session:
                instances = []
                for data in data_list:
                    instance = model(**data)
                    session.add(instance)
                    instances.append(instance)

                await session.flush()

                # Refresh all instances to get generated IDs
                for instance in instances:
                    await session.refresh(instance)

                return instances
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating {model.__name__}: {e}")
            raise

    async def bulk_update(
        self, model: Type[ModelType], updates: List[Dict[str, Any]]
    ) -> int:
        """
        Bulk update records
        updates should be list of dicts with 'id' and other fields to update
        """
        try:
            async with self.get_session() as session:
                updated_count = 0

                for update_data in updates:
                    record_id = update_data.pop("id", None)
                    if record_id:
                        query = (
                            update(model)
                            .where(model.id == record_id)
                            .values(**update_data)
                        )
                        result = await session.execute(query)
                        updated_count += result.rowcount

                return updated_count
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk updating {model.__name__}: {e}")
            raise

    async def exists(self, model: Type[ModelType], **filters) -> bool:
        """Check if records exist with given filters"""
        try:
            count = await self.count(model, **filters)
            return count > 0
        except SQLAlchemyError as e:
            self.logger.error(f"Error checking existence {model.__name__}: {e}")
            raise

    async def get_paginated(
        self, model: Type[ModelType], page: int = 1, per_page: int = 20, **filters
    ) -> Dict[str, Any]:
        """Get paginated results with metadata"""
        try:
            offset = (page - 1) * per_page

            # Get total count
            total_count = await self.count(model, **filters)

            # Get paginated results
            query = select(model)

            for field, value in filters.items():
                if hasattr(model, field):
                    query = query.where(getattr(model, field) == value)

            query = query.offset(offset).limit(per_page)

            async with self.get_session() as session:
                result = await session.execute(query)
                items = result.scalars().all()

            return {
                "items": items,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "pages": (total_count + per_page - 1) // per_page,
                "has_next": page * per_page < total_count,
                "has_prev": page > 1,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting paginated {model.__name__}: {e}")
            raise


class AsyncServiceError(Exception):
    """Custom exception for async service operations"""

    def __init__(self, message: str, service: str = None, operation: str = None):
        self.message = message
        self.service = service
        self.operation = operation
        super().__init__(self.message)


class AsyncValidationError(AsyncServiceError):
    """Exception for validation errors in async services"""

    pass


class AsyncNotFoundError(AsyncServiceError):
    """Exception for not found errors in async services"""

    pass


# Utility functions for common async patterns


async def run_in_background(coro, logger: logging.Logger = None):
    """
    Run a coroutine in the background without blocking
    Useful for fire-and-forget operations
    """

    def _log_exception(task):
        if task.exception():
            if logger:
                logger.error(f"Background task failed: {task.exception()}")
            else:
                print(f"Background task failed: {task.exception()}")

    task = asyncio.create_task(coro)
    task.add_done_callback(_log_exception)
    return task


async def retry_async(
    coro, max_retries: int = 3, delay: float = 1.0, exponential_backoff: bool = True
):
    """
    Retry an async operation with exponential backoff
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await coro
        except Exception as e:
            last_exception = e

            if attempt < max_retries:
                wait_time = delay * (2**attempt if exponential_backoff else 1)
                await asyncio.sleep(wait_time)
            else:
                break

    raise last_exception


async def gather_with_concurrency(coros, max_concurrent: int = 10):
    """
    Run multiple coroutines with limited concurrency
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_with_semaphore(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[_run_with_semaphore(coro) for coro in coros])


# Example usage and testing functions


async def test_async_base_service():
    """Test the async base service functionality"""
    logger = get_logger("async_base_service_test")

    try:
        # Test basic service creation
        service = AsyncBaseService("test_service")
        logger.info("✅ AsyncBaseService created successfully")

        # Test database session
        async with service.get_session() as session:
            result = await session.execute(text("SELECT 1 as test_value"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database session test passed")
            else:
                logger.error("❌ Database session test failed")
                return False

        logger.info("✅ All AsyncBaseService tests passed")
        return True

    except Exception as e:
        logger.error(f"❌ AsyncBaseService test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    """Run tests if executed directly"""
    import asyncio

    async def main():
        print("🧪 Testing AsyncBaseService")
        print("=" * 40)

        # Initialize async database first
        from src.database.async_connection import initialize_async_database

        await initialize_async_database()

        success = await test_async_base_service()

        print("=" * 40)
        if success:
            print("🎉 AsyncBaseService tests passed!")
        else:
            print("💥 AsyncBaseService tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
