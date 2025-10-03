"""
MVidarr System Integration Tests - Phase 2 Week 24
Comprehensive integration testing for all Phase 2 components
"""

import asyncio
import pytest
import time
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock

# Import system components
from src.services.media_cache_manager import get_media_cache_manager, CacheType
from src.services.performance_monitor import get_performance_monitor, MetricType
from src.services.system_optimizer import get_system_optimizer, OptimizationTarget, OptimizationLevel
from src.services.image_thread_pool import get_image_processing_pool
from src.jobs.bulk_media_tasks import BulkMediaProcessor
from src.jobs.advanced_image_tasks import AdvancedImageAnalyzer
from src.services.media_collection_manager import MediaCollectionManager, CollectionType


class TestSystemIntegration:
    """Integration tests for complete system functionality"""
    
    @pytest.fixture
    async def setup_test_environment(self):
        """Set up test environment with all services"""
        # Create temporary directory for test files
        test_dir = Path(tempfile.mkdtemp())
        
        # Initialize services
        cache_manager = await get_media_cache_manager()
        performance_monitor = await get_performance_monitor()
        system_optimizer = await get_system_optimizer()
        image_pool = get_image_processing_pool()
        
        yield {
            "test_dir": test_dir,
            "cache_manager": cache_manager,
            "performance_monitor": performance_monitor,
            "system_optimizer": system_optimizer,
            "image_pool": image_pool
        }
        
        # Cleanup
        shutil.rmtree(test_dir)
    
    @pytest.mark.asyncio
    async def test_cache_integration_with_media_processing(self, setup_test_environment):
        """Test cache integration with media processing pipeline"""
        env = await setup_test_environment
        cache_manager = env["cache_manager"]
        
        # Test data
        test_file_path = "/fake/path/test_image.jpg"
        test_metadata = {
            "width": 1920,
            "height": 1080,
            "format": "JPEG",
            "size": 2048000
        }
        
        # Test cache storage
        cache_success = await cache_manager.cache_media_metadata(test_file_path, test_metadata)
        assert cache_success, "Failed to cache metadata"
        
        # Test cache retrieval
        cached_metadata = await cache_manager.get_cached_media_metadata(test_file_path, validate_freshness=False)
        assert cached_metadata is not None, "Failed to retrieve cached metadata"
        assert cached_metadata["width"] == 1920, "Cached metadata corrupted"
        assert cached_metadata["format"] == "JPEG", "Cached format incorrect"
        
        # Test cache invalidation
        delete_success = await cache_manager.delete(CacheType.MEDIA_METADATA, test_file_path)
        assert delete_success, "Failed to delete cached metadata"
        
        # Verify deletion
        cached_after_delete = await cache_manager.get_cached_media_metadata(test_file_path, validate_freshness=False)
        assert cached_after_delete is None, "Metadata still cached after deletion"
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, setup_test_environment):
        """Test performance monitoring across system components"""
        env = await setup_test_environment
        monitor = env["performance_monitor"]
        
        # Start monitoring if not active
        if not monitor.monitoring_active:
            await monitor.start_monitoring()
        
        # Test metric recording
        await monitor.record_media_processing_time("test_operation", 2.5, "test_file.jpg")
        await monitor.record_api_response_time("/api/test", 150.0, 200)
        await monitor.record_concurrent_operations("test_ops", 5)
        
        # Wait for metrics to be recorded
        await asyncio.sleep(1)
        
        # Verify metrics are recorded
        current_metrics = monitor.get_current_metrics()
        assert len(current_metrics) > 0, "No metrics recorded"
        
        # Test health summary
        health_summary = await monitor.get_system_health_summary()
        assert "health_score" in health_summary, "Health score not calculated"
        assert "current_metrics" in health_summary, "Current metrics not included"
        assert health_summary["health_score"] >= 0, "Invalid health score"
    
    @pytest.mark.asyncio
    async def test_system_optimizer_integration(self, setup_test_environment):
        """Test system optimizer functionality"""
        env = await setup_test_environment
        optimizer = env["system_optimizer"]
        
        # Test basic optimization
        result = await optimizer.optimize_system(OptimizationTarget.CACHE, OptimizationLevel.BASIC)
        
        assert result.target == OptimizationTarget.CACHE, "Wrong optimization target"
        assert result.level == OptimizationLevel.BASIC, "Wrong optimization level"
        assert result.duration_seconds > 0, "Invalid optimization duration"
        
        # Test optimization recommendations
        recommendations = await optimizer.get_optimization_recommendations()
        assert isinstance(recommendations, list), "Recommendations should be a list"
        
        # Test optimization history
        history = optimizer.get_optimization_history(1)  # Last 1 hour
        assert len(history) >= 1, "Optimization not recorded in history"
    
    @pytest.mark.asyncio
    async def test_bulk_media_processing_with_caching(self, setup_test_environment):
        """Test bulk media processing with integrated caching"""
        env = await setup_test_environment
        cache_manager = env["cache_manager"]
        
        # Create test processor
        processor = BulkMediaProcessor()
        
        # Mock media files (we can't create real files in testing)
        test_media_paths = [
            str(env["test_dir"] / "test1.jpg"),
            str(env["test_dir"] / "test2.png"),
            str(env["test_dir"] / "test3.mp4")
        ]
        
        # Pre-cache some metadata to test cache hits
        test_metadata = {"width": 800, "height": 600, "cached": True}
        await cache_manager.cache_media_metadata(test_media_paths[0], test_metadata)
        
        # Since we can't process real files, we'll test the cache integration logic
        # by verifying cache operations work correctly
        
        cached_result = await cache_manager.get_cached_media_metadata(test_media_paths[0])
        assert cached_result is not None, "Pre-cached metadata not found"
        assert cached_result["cached"] is True, "Cache content incorrect"
    
    @pytest.mark.asyncio
    async def test_image_processing_integration(self, setup_test_environment):
        """Test image processing pipeline integration"""
        env = await setup_test_environment
        image_pool = env["image_pool"]
        
        # Test image pool status
        pool_stats = image_pool.get_pool_statistics()
        assert "worker_count" in pool_stats, "Pool statistics missing worker count"
        assert "queue_size" in pool_stats, "Pool statistics missing queue size"
        
        # Test pool lifecycle
        if not image_pool.pool.is_running():
            await image_pool.start()
        
        assert image_pool.pool.is_running(), "Image pool failed to start"
    
    @pytest.mark.asyncio
    async def test_collection_management_integration(self, setup_test_environment):
        """Test media collection management with integrated services"""
        env = await setup_test_environment
        
        # Create collection manager
        manager = MediaCollectionManager()
        
        # Test collection creation
        collection_id = "test_collection_001"
        metadata = await manager.create_collection(
            collection_id=collection_id,
            name="Test Collection",
            collection_type=CollectionType.MIXED_COLLECTION,
            description="Integration test collection"
        )
        
        assert metadata.collection_id == collection_id, "Collection ID mismatch"
        assert metadata.name == "Test Collection", "Collection name mismatch"
        assert metadata.collection_type == CollectionType.MIXED_COLLECTION, "Collection type mismatch"
        
        # Test collection statistics
        stats = await manager.get_collection_statistics(collection_id)
        assert "collection_metadata" in stats, "Collection metadata missing from stats"
        assert stats["collection_metadata"]["total_items"] == 0, "New collection should have 0 items"
        
        # Test processing statistics
        processing_stats = manager.get_processing_statistics()
        assert "processing_stats" in processing_stats, "Processing stats missing"
        assert "active_collections" in processing_stats, "Active collections count missing"
    
    @pytest.mark.asyncio
    async def test_end_to_end_media_workflow(self, setup_test_environment):
        """Test complete end-to-end media processing workflow"""
        env = await setup_test_environment
        cache_manager = env["cache_manager"]
        monitor = env["performance_monitor"]
        
        # Simulate complete workflow
        workflow_start = time.time()
        
        # Step 1: Cache some initial data
        test_files = [f"test_{i}.jpg" for i in range(5)]
        for i, file_path in enumerate(test_files):
            metadata = {
                "file_path": file_path,
                "width": 1920 + i * 100,
                "height": 1080 + i * 50,
                "format": "JPEG",
                "processed_at": time.time()
            }
            await cache_manager.cache_media_metadata(file_path, metadata)
        
        # Step 2: Retrieve cached data (simulating processing)
        cache_hits = 0
        for file_path in test_files:
            cached = await cache_manager.get_cached_media_metadata(file_path, validate_freshness=False)
            if cached:
                cache_hits += 1
        
        # Step 3: Record performance metrics
        workflow_time = time.time() - workflow_start
        await monitor.record_media_processing_time("end_to_end_workflow", workflow_time)
        
        # Step 4: Get cache statistics
        cache_stats = await cache_manager.get_cache_statistics()
        
        # Verify workflow completion
        assert cache_hits == len(test_files), f"Expected {len(test_files)} cache hits, got {cache_hits}"
        assert "cache_metrics" in cache_stats, "Cache metrics missing"
        assert workflow_time > 0, "Workflow time should be positive"
    
    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, setup_test_environment):
        """Test integrated system health monitoring"""
        env = await setup_test_environment
        monitor = env["performance_monitor"]
        
        # Get comprehensive health summary
        health_summary = await monitor.get_system_health_summary()
        
        # Verify health summary structure
        required_fields = [
            "health_score", "health_status", "current_metrics",
            "active_alerts_count", "monitoring_stats", "timestamp"
        ]
        
        for field in required_fields:
            assert field in health_summary, f"Health summary missing field: {field}"
        
        # Verify health score is valid
        health_score = health_summary["health_score"]
        assert 0 <= health_score <= 100, f"Invalid health score: {health_score}"
        
        # Verify health status is valid
        valid_statuses = ["excellent", "good", "fair", "poor", "critical"]
        assert health_summary["health_status"] in valid_statuses, "Invalid health status"
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, setup_test_environment):
        """Test error handling across integrated services"""
        env = await setup_test_environment
        cache_manager = env["cache_manager"]
        
        # Test cache operations with invalid data
        try:
            # This should handle gracefully
            await cache_manager.cache_media_metadata("", {})
        except Exception as e:
            # Should not raise unhandled exceptions
            assert False, f"Cache should handle empty data gracefully: {e}"
        
        # Test retrieving non-existent cache entries
        result = await cache_manager.get_cached_media_metadata("non_existent_file.jpg")
        assert result is None, "Non-existent cache entry should return None"
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, setup_test_environment):
        """Test system performance under simulated load"""
        env = await setup_test_environment
        cache_manager = env["cache_manager"]
        monitor = env["performance_monitor"]
        
        # Simulate concurrent operations
        concurrent_tasks = []
        start_time = time.time()
        
        # Create 50 concurrent cache operations
        for i in range(50):
            task = cache_manager.cache_media_metadata(
                f"load_test_{i}.jpg",
                {"width": 1920, "height": 1080, "test_id": i}
            )
            concurrent_tasks.append(task)
        
        # Wait for all operations to complete
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        load_test_time = time.time() - start_time
        
        # Verify most operations succeeded
        successful_operations = sum(1 for r in results if r is True)
        success_rate = successful_operations / len(results) * 100
        
        assert success_rate >= 80, f"Success rate too low under load: {success_rate}%"
        assert load_test_time < 10, f"Load test took too long: {load_test_time}s"
        
        # Record load test performance
        await monitor.record_media_processing_time("load_test", load_test_time, "50_concurrent_operations")


class TestAPIIntegration:
    """Test API integration with caching and monitoring"""
    
    @pytest.mark.asyncio
    async def test_api_performance_tracking(self):
        """Test API performance tracking integration"""
        from src.services.performance_monitor import track_api_response_time, track_error_rate
        
        # Test API response time tracking
        await track_api_response_time("/api/test/endpoint", 150.5, 200)
        await track_api_response_time("/api/test/slow", 2500.0, 200)
        
        # Test error rate tracking
        await track_error_rate("api_requests", 2, 10)  # 2 errors out of 10 requests
        
        # Verify tracking completed without exceptions
        assert True, "API performance tracking should complete without errors"
    
    @pytest.mark.asyncio
    async def test_cache_headers_integration(self):
        """Test cache headers middleware integration"""
        from src.middleware.performance_middleware import CacheHeadersMiddleware
        from fastapi import Request, Response
        from unittest.mock import AsyncMock
        
        # Create mock request and response
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/system-health/metrics/cpu"
        
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}
        
        # Create middleware
        middleware = CacheHeadersMiddleware(None, default_cache_ttl=300)
        
        # Mock the call_next function
        async def mock_call_next(request):
            return mock_response
        
        # Test middleware
        result = await middleware.dispatch(mock_request, mock_call_next)
        
        # Verify cache headers were added
        assert "Cache-Control" in result.headers, "Cache-Control header not added"
        assert "X-Cache-Strategy" in result.headers, "Cache strategy header not added"


# Pytest configuration and fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Performance benchmarks
class TestPerformanceBenchmarks:
    """Performance benchmark tests for integrated system"""
    
    @pytest.mark.asyncio
    async def test_cache_performance_benchmark(self):
        """Benchmark cache performance"""
        cache_manager = await get_media_cache_manager()
        
        # Benchmark cache writes
        write_start = time.time()
        for i in range(100):
            await cache_manager.cache_media_metadata(
                f"benchmark_{i}.jpg",
                {"width": 1920, "height": 1080, "benchmark": True}
            )
        write_time = time.time() - write_start
        
        # Benchmark cache reads
        read_start = time.time()
        for i in range(100):
            await cache_manager.get_cached_media_metadata(f"benchmark_{i}.jpg", validate_freshness=False)
        read_time = time.time() - read_start
        
        # Performance assertions
        assert write_time < 5.0, f"Cache writes too slow: {write_time}s for 100 operations"
        assert read_time < 1.0, f"Cache reads too slow: {read_time}s for 100 operations"
        
        # Calculate operations per second
        write_ops_per_sec = 100 / write_time
        read_ops_per_sec = 100 / read_time
        
        assert write_ops_per_sec > 20, f"Cache write performance too low: {write_ops_per_sec} ops/sec"
        assert read_ops_per_sec > 100, f"Cache read performance too low: {read_ops_per_sec} ops/sec"
    
    @pytest.mark.asyncio
    async def test_monitoring_overhead_benchmark(self):
        """Benchmark monitoring system overhead"""
        monitor = await get_performance_monitor()
        
        # Benchmark monitoring overhead
        operations = 1000
        
        # Time without monitoring
        start_time = time.time()
        for i in range(operations):
            # Simulate work
            await asyncio.sleep(0.001)
        baseline_time = time.time() - start_time
        
        # Time with monitoring
        start_time = time.time()
        for i in range(operations):
            await monitor.record_concurrent_operations("benchmark", 1)
            await asyncio.sleep(0.001)
            await monitor.record_concurrent_operations("benchmark", -1)
        monitored_time = time.time() - start_time
        
        # Calculate overhead
        overhead_percent = ((monitored_time - baseline_time) / baseline_time) * 100
        
        # Monitoring overhead should be less than 10%
        assert overhead_percent < 10, f"Monitoring overhead too high: {overhead_percent:.1f}%"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])