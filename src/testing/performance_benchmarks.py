"""
Performance Benchmarking Suite - Issue 129 Performance Optimization & Load Testing
Comprehensive benchmarking system to measure and validate performance improvements
"""

import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import psutil
from src.services.database_service import DatabaseService
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.testing.performance_benchmarks")


class BenchmarkType(Enum):
    """Types of performance benchmarks"""

    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    MEMORY_USAGE = "memory_usage"
    DATABASE_PERFORMANCE = "database_performance"
    CACHE_PERFORMANCE = "cache_performance"
    CONCURRENCY = "concurrency"
    RESOURCE_UTILIZATION = "resource_utilization"


@dataclass
class BenchmarkConfig:
    """Configuration for performance benchmarks"""

    name: str
    benchmark_type: BenchmarkType

    # Test parameters
    iterations: int = 100
    concurrent_runs: int = 10
    warm_up_iterations: int = 10

    # Timing
    timeout_seconds: int = 30

    # Target thresholds
    target_response_time_ms: Optional[float] = None
    target_throughput_rps: Optional[float] = None
    target_memory_mb: Optional[float] = None
    target_success_rate: float = 99.0

    # Test data
    test_endpoints: List[str] = None
    test_queries: List[str] = None
    test_payload_size_kb: int = 1

    # Comparison baseline
    baseline_results: Optional[Dict] = None


@dataclass
class BenchmarkResult:
    """Result of a single benchmark measurement"""

    timestamp: float
    duration_ms: float
    memory_used_mb: float
    cpu_percent: float
    success: bool
    error_message: Optional[str] = None
    custom_metrics: Dict[str, Any] = None


@dataclass
class BenchmarkSummary:
    """Summary of benchmark results"""

    config: BenchmarkConfig
    start_time: datetime
    end_time: datetime
    total_duration_seconds: float

    # Statistical measures
    total_iterations: int
    successful_iterations: int
    failed_iterations: int
    success_rate: float

    # Performance metrics
    min_duration_ms: float
    max_duration_ms: float
    avg_duration_ms: float
    median_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float

    # Resource usage
    peak_memory_mb: float
    avg_memory_mb: float
    peak_cpu_percent: float
    avg_cpu_percent: float

    # Throughput
    throughput_rps: float

    # Performance assessment
    performance_score: float
    meets_targets: bool
    improvement_percentage: Optional[float] = None
    bottlenecks: List[str] = None

    # Detailed results
    raw_results: List[BenchmarkResult] = None


class PerformanceBenchmarkRunner:
    """Main performance benchmarking runner"""

    def __init__(self):
        self.db_service = None
        self.redis_client = None

    async def initialize(self):
        """Initialize benchmark runner"""
        try:
            self.db_service = DatabaseService()
            self.redis_client = await get_redis_client()
            logger.info("Performance benchmark runner initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize some services: {e}")

    async def run_benchmark(self, config: BenchmarkConfig) -> BenchmarkSummary:
        """Run a single benchmark"""
        logger.info(f"Starting benchmark: {config.name}")

        start_time = datetime.utcnow()
        results = []

        # Warm-up phase
        if config.warm_up_iterations > 0:
            logger.info(f"Warming up with {config.warm_up_iterations} iterations")
            await self._run_warm_up(config)

        try:
            # Execute benchmark based on type
            if config.benchmark_type == BenchmarkType.RESPONSE_TIME:
                results = await self._benchmark_response_time(config)
            elif config.benchmark_type == BenchmarkType.THROUGHPUT:
                results = await self._benchmark_throughput(config)
            elif config.benchmark_type == BenchmarkType.MEMORY_USAGE:
                results = await self._benchmark_memory_usage(config)
            elif config.benchmark_type == BenchmarkType.DATABASE_PERFORMANCE:
                results = await self._benchmark_database_performance(config)
            elif config.benchmark_type == BenchmarkType.CACHE_PERFORMANCE:
                results = await self._benchmark_cache_performance(config)
            elif config.benchmark_type == BenchmarkType.CONCURRENCY:
                results = await self._benchmark_concurrency(config)
            elif config.benchmark_type == BenchmarkType.RESOURCE_UTILIZATION:
                results = await self._benchmark_resource_utilization(config)
            else:
                raise ValueError(f"Unknown benchmark type: {config.benchmark_type}")

        except Exception as e:
            logger.error(f"Benchmark execution failed: {e}")
            results = []

        end_time = datetime.utcnow()

        # Generate summary
        summary = self._generate_summary(config, start_time, end_time, results)

        logger.info(
            f"Benchmark completed: {config.name} - Score: {summary.performance_score:.2f}"
        )

        return summary

    async def _run_warm_up(self, config: BenchmarkConfig):
        """Run warm-up iterations"""
        warm_up_config = BenchmarkConfig(
            name=f"{config.name}_warmup",
            benchmark_type=config.benchmark_type,
            iterations=config.warm_up_iterations,
            concurrent_runs=min(config.concurrent_runs, 5),
        )

        # Run simplified benchmark for warm-up
        if config.benchmark_type == BenchmarkType.RESPONSE_TIME:
            await self._benchmark_response_time(warm_up_config)
        elif config.benchmark_type == BenchmarkType.DATABASE_PERFORMANCE:
            await self._benchmark_database_performance(warm_up_config)

    async def _benchmark_response_time(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark API response times"""
        results = []
        endpoints = config.test_endpoints or [
            "/api/videos",
            "/api/artists",
            "/api/playlists",
        ]

        semaphore = asyncio.Semaphore(config.concurrent_runs)

        tasks = []
        for i in range(config.iterations):
            endpoint = endpoints[i % len(endpoints)]
            task = self._measure_api_response_time(semaphore, endpoint)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, BenchmarkResult)]
        return valid_results

    async def _benchmark_throughput(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark API throughput"""
        results = []
        endpoints = config.test_endpoints or ["/api/videos"]

        # Run concurrent requests and measure throughput
        start_time = time.time()

        semaphore = asyncio.Semaphore(config.concurrent_runs)
        tasks = []

        for i in range(config.iterations):
            endpoint = endpoints[i % len(endpoints)]
            task = self._measure_api_response_time(semaphore, endpoint)
            tasks.append(task)

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        # Calculate throughput
        successful_requests = sum(
            1 for r in raw_results if isinstance(r, BenchmarkResult) and r.success
        )
        total_duration = end_time - start_time
        throughput = successful_requests / total_duration if total_duration > 0 else 0

        # Create single result representing throughput
        result = BenchmarkResult(
            timestamp=start_time,
            duration_ms=total_duration * 1000,
            memory_used_mb=psutil.Process().memory_info().rss / (1024 * 1024),
            cpu_percent=psutil.cpu_percent(),
            success=True,
            custom_metrics={
                "throughput_rps": throughput,
                "successful_requests": successful_requests,
            },
        )

        return [result]

    async def _benchmark_memory_usage(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark memory usage patterns"""
        results = []
        process = psutil.Process()

        # Baseline memory
        baseline_memory = process.memory_info().rss / (1024 * 1024)

        for i in range(config.iterations):
            start_time = time.time()
            start_memory = process.memory_info().rss / (1024 * 1024)

            # Perform some memory-intensive operations
            await self._simulate_memory_workload(config)

            end_time = time.time()
            end_memory = process.memory_info().rss / (1024 * 1024)

            result = BenchmarkResult(
                timestamp=start_time,
                duration_ms=(end_time - start_time) * 1000,
                memory_used_mb=end_memory - baseline_memory,
                cpu_percent=psutil.cpu_percent(),
                success=True,
                custom_metrics={
                    "memory_growth_mb": end_memory - start_memory,
                    "baseline_memory_mb": baseline_memory,
                },
            )

            results.append(result)

            # Small delay to allow garbage collection
            await asyncio.sleep(0.1)

        return results

    async def _benchmark_database_performance(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark database query performance"""
        results = []

        if not self.db_service:
            logger.warning("Database service not available for benchmarking")
            return results

        queries = config.test_queries or [
            "SELECT COUNT(*) FROM videos",
            "SELECT * FROM videos ORDER BY added_at DESC LIMIT 10",
            "SELECT * FROM artists LIMIT 50",
            "SELECT v.* FROM videos v JOIN artists a ON v.artist_id = a.id LIMIT 20",
        ]

        semaphore = asyncio.Semaphore(config.concurrent_runs)

        tasks = []
        for i in range(config.iterations):
            query = queries[i % len(queries)]
            task = self._measure_database_query(semaphore, query)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, BenchmarkResult)]
        return valid_results

    async def _benchmark_cache_performance(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark cache performance"""
        results = []

        if not self.redis_client:
            logger.warning("Redis client not available for cache benchmarking")
            return results

        semaphore = asyncio.Semaphore(config.concurrent_runs)

        tasks = []
        for i in range(config.iterations):
            task = self._measure_cache_operation(semaphore, f"test_key_{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, BenchmarkResult)]
        return valid_results

    async def _benchmark_concurrency(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark concurrency handling"""
        results = []
        endpoints = config.test_endpoints or ["/api/videos"]

        # Test different concurrency levels
        concurrency_levels = [1, 5, 10, 20, 50, 100]

        for level in concurrency_levels:
            if level > config.concurrent_runs:
                break

            logger.info(f"Testing concurrency level: {level}")

            start_time = time.time()
            semaphore = asyncio.Semaphore(level)

            tasks = []
            for i in range(min(config.iterations, level * 10)):
                endpoint = endpoints[i % len(endpoints)]
                task = self._measure_api_response_time(semaphore, endpoint)
                tasks.append(task)

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Calculate metrics for this concurrency level
            successful_requests = sum(
                1 for r in batch_results if isinstance(r, BenchmarkResult) and r.success
            )
            failed_requests = len(batch_results) - successful_requests
            throughput = (
                successful_requests / (end_time - start_time)
                if end_time > start_time
                else 0
            )

            result = BenchmarkResult(
                timestamp=start_time,
                duration_ms=(end_time - start_time) * 1000,
                memory_used_mb=psutil.Process().memory_info().rss / (1024 * 1024),
                cpu_percent=psutil.cpu_percent(),
                success=failed_requests == 0,
                custom_metrics={
                    "concurrency_level": level,
                    "throughput_rps": throughput,
                    "successful_requests": successful_requests,
                    "failed_requests": failed_requests,
                },
            )

            results.append(result)

        return results

    async def _benchmark_resource_utilization(
        self, config: BenchmarkConfig
    ) -> List[BenchmarkResult]:
        """Benchmark system resource utilization"""
        results = []

        # Monitor system resources during load
        monitoring_duration = 60  # seconds
        monitoring_interval = 1  # second

        start_time = time.time()

        # Start background load
        load_task = asyncio.create_task(self._generate_background_load(config))

        try:
            for i in range(monitoring_duration):
                measurement_start = time.time()

                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_info = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                network_io = psutil.net_io_counters()

                result = BenchmarkResult(
                    timestamp=measurement_start,
                    duration_ms=monitoring_interval * 1000,
                    memory_used_mb=memory_info.used / (1024 * 1024),
                    cpu_percent=cpu_percent,
                    success=True,
                    custom_metrics={
                        "memory_percent": memory_info.percent,
                        "disk_read_mb": (
                            disk_io.read_bytes / (1024 * 1024) if disk_io else 0
                        ),
                        "disk_write_mb": (
                            disk_io.write_bytes / (1024 * 1024) if disk_io else 0
                        ),
                        "network_sent_mb": (
                            network_io.bytes_sent / (1024 * 1024) if network_io else 0
                        ),
                        "network_recv_mb": (
                            network_io.bytes_recv / (1024 * 1024) if network_io else 0
                        ),
                    },
                )

                results.append(result)
                await asyncio.sleep(monitoring_interval)

        finally:
            load_task.cancel()
            try:
                await load_task
            except asyncio.CancelledError:
                pass

        return results

    async def _measure_api_response_time(
        self, semaphore: asyncio.Semaphore, endpoint: str
    ) -> BenchmarkResult:
        """Measure API response time"""
        async with semaphore:
            start_time = time.time()
            memory_before = psutil.Process().memory_info().rss / (1024 * 1024)

            try:
                # Use localhost for testing
                url = f"http://localhost:5000{endpoint}"

                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        await response.text()

                        end_time = time.time()
                        memory_after = psutil.Process().memory_info().rss / (
                            1024 * 1024
                        )

                        return BenchmarkResult(
                            timestamp=start_time,
                            duration_ms=(end_time - start_time) * 1000,
                            memory_used_mb=memory_after,
                            cpu_percent=psutil.cpu_percent(),
                            success=200 <= response.status < 400,
                            custom_metrics={"status_code": response.status},
                        )

            except Exception as e:
                end_time = time.time()
                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)

                return BenchmarkResult(
                    timestamp=start_time,
                    duration_ms=(end_time - start_time) * 1000,
                    memory_used_mb=memory_after,
                    cpu_percent=psutil.cpu_percent(),
                    success=False,
                    error_message=str(e),
                )

    async def _measure_database_query(
        self, semaphore: asyncio.Semaphore, query: str
    ) -> BenchmarkResult:
        """Measure database query performance"""
        async with semaphore:
            start_time = time.time()
            memory_before = psutil.Process().memory_info().rss / (1024 * 1024)

            try:
                # Execute query
                result = await self.db_service.execute_query(query)

                end_time = time.time()
                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)

                return BenchmarkResult(
                    timestamp=start_time,
                    duration_ms=(end_time - start_time) * 1000,
                    memory_used_mb=memory_after,
                    cpu_percent=psutil.cpu_percent(),
                    success=True,
                    custom_metrics={"rows_affected": len(result) if result else 0},
                )

            except Exception as e:
                end_time = time.time()
                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)

                return BenchmarkResult(
                    timestamp=start_time,
                    duration_ms=(end_time - start_time) * 1000,
                    memory_used_mb=memory_after,
                    cpu_percent=psutil.cpu_percent(),
                    success=False,
                    error_message=str(e),
                )

    async def _measure_cache_operation(
        self, semaphore: asyncio.Semaphore, key: str
    ) -> BenchmarkResult:
        """Measure cache operation performance"""
        async with semaphore:
            start_time = time.time()
            memory_before = psutil.Process().memory_info().rss / (1024 * 1024)

            try:
                # Set and get cache operation
                test_value = f"test_value_{int(time.time() * 1000)}"

                await self.redis_client.set(key, test_value, ex=60)
                retrieved_value = await self.redis_client.get(key)

                end_time = time.time()
                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)

                return BenchmarkResult(
                    timestamp=start_time,
                    duration_ms=(end_time - start_time) * 1000,
                    memory_used_mb=memory_after,
                    cpu_percent=psutil.cpu_percent(),
                    success=retrieved_value == test_value,
                    custom_metrics={"cache_hit": retrieved_value is not None},
                )

            except Exception as e:
                end_time = time.time()
                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)

                return BenchmarkResult(
                    timestamp=start_time,
                    duration_ms=(end_time - start_time) * 1000,
                    memory_used_mb=memory_after,
                    cpu_percent=psutil.cpu_percent(),
                    success=False,
                    error_message=str(e),
                )

    async def _simulate_memory_workload(self, config: BenchmarkConfig):
        """Simulate memory-intensive workload"""
        # Create and manipulate data structures
        data = []

        for i in range(config.test_payload_size_kb * 100):
            data.append(
                {"id": i, "data": "x" * 1024, "timestamp": time.time()}  # 1KB of data
            )

        # Process data
        processed = [item for item in data if item["id"] % 2 == 0]

        # Cleanup
        del data
        del processed

        # Small delay for processing
        await asyncio.sleep(0.01)

    async def _generate_background_load(self, config: BenchmarkConfig):
        """Generate background load for resource monitoring"""
        endpoints = config.test_endpoints or ["/api/videos"]

        try:
            while True:
                # Concurrent requests
                semaphore = asyncio.Semaphore(10)
                tasks = []

                for i in range(20):
                    endpoint = endpoints[i % len(endpoints)]
                    task = self._measure_api_response_time(semaphore, endpoint)
                    tasks.append(task)

                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass

    def _generate_summary(
        self,
        config: BenchmarkConfig,
        start_time: datetime,
        end_time: datetime,
        results: List[BenchmarkResult],
    ) -> BenchmarkSummary:
        """Generate benchmark summary"""

        if not results:
            return BenchmarkSummary(
                config=config,
                start_time=start_time,
                end_time=end_time,
                total_duration_seconds=0,
                total_iterations=0,
                successful_iterations=0,
                failed_iterations=0,
                success_rate=0,
                min_duration_ms=0,
                max_duration_ms=0,
                avg_duration_ms=0,
                median_duration_ms=0,
                p95_duration_ms=0,
                p99_duration_ms=0,
                peak_memory_mb=0,
                avg_memory_mb=0,
                peak_cpu_percent=0,
                avg_cpu_percent=0,
                throughput_rps=0,
                performance_score=0,
                meets_targets=False,
                raw_results=[],
            )

        # Basic statistics
        successful_results = [r for r in results if r.success]
        total_iterations = len(results)
        successful_iterations = len(successful_results)
        failed_iterations = total_iterations - successful_iterations
        success_rate = (successful_iterations / max(total_iterations, 1)) * 100

        # Duration statistics
        durations = [r.duration_ms for r in successful_results]
        if durations:
            min_duration = min(durations)
            max_duration = max(durations)
            avg_duration = statistics.mean(durations)
            median_duration = statistics.median(durations)

            sorted_durations = sorted(durations)
            p95_duration = (
                sorted_durations[int(len(sorted_durations) * 0.95)]
                if sorted_durations
                else 0
            )
            p99_duration = (
                sorted_durations[int(len(sorted_durations) * 0.99)]
                if sorted_durations
                else 0
            )
        else:
            min_duration = max_duration = avg_duration = median_duration = (
                p95_duration
            ) = p99_duration = 0

        # Memory statistics
        memory_values = [r.memory_used_mb for r in results]
        peak_memory = max(memory_values) if memory_values else 0
        avg_memory = statistics.mean(memory_values) if memory_values else 0

        # CPU statistics
        cpu_values = [r.cpu_percent for r in results]
        peak_cpu = max(cpu_values) if cpu_values else 0
        avg_cpu = statistics.mean(cpu_values) if cpu_values else 0

        # Throughput calculation
        total_duration = (end_time - start_time).total_seconds()
        throughput_rps = successful_iterations / max(total_duration, 1)

        # Performance scoring
        performance_score = self._calculate_performance_score(
            config, success_rate, avg_duration, throughput_rps
        )

        # Target assessment
        meets_targets = self._assess_targets(
            config, success_rate, avg_duration, throughput_rps, peak_memory
        )

        # Improvement calculation
        improvement_percentage = None
        if config.baseline_results:
            baseline_avg = config.baseline_results.get("avg_duration_ms", avg_duration)
            if baseline_avg > 0:
                improvement_percentage = (
                    (baseline_avg - avg_duration) / baseline_avg
                ) * 100

        # Bottleneck identification
        bottlenecks = self._identify_bottlenecks(
            config, results, success_rate, avg_duration, peak_cpu, peak_memory
        )

        return BenchmarkSummary(
            config=config,
            start_time=start_time,
            end_time=end_time,
            total_duration_seconds=total_duration,
            total_iterations=total_iterations,
            successful_iterations=successful_iterations,
            failed_iterations=failed_iterations,
            success_rate=success_rate,
            min_duration_ms=min_duration,
            max_duration_ms=max_duration,
            avg_duration_ms=avg_duration,
            median_duration_ms=median_duration,
            p95_duration_ms=p95_duration,
            p99_duration_ms=p99_duration,
            peak_memory_mb=peak_memory,
            avg_memory_mb=avg_memory,
            peak_cpu_percent=peak_cpu,
            avg_cpu_percent=avg_cpu,
            throughput_rps=throughput_rps,
            performance_score=performance_score,
            meets_targets=meets_targets,
            improvement_percentage=improvement_percentage,
            bottlenecks=bottlenecks,
            raw_results=results,
        )

    def _calculate_performance_score(
        self,
        config: BenchmarkConfig,
        success_rate: float,
        avg_duration: float,
        throughput: float,
    ) -> float:
        """Calculate performance score (0-100)"""
        score = 0

        # Success rate component (40%)
        score += (success_rate / 100) * 40

        # Response time component (40%)
        target_time = config.target_response_time_ms or 1000
        if avg_duration <= target_time:
            time_score = 40
        else:
            time_score = max(0, 40 * (1 - (avg_duration - target_time) / target_time))
        score += time_score

        # Throughput component (20%)
        target_throughput = config.target_throughput_rps or 10
        if throughput >= target_throughput:
            throughput_score = 20
        else:
            throughput_score = (throughput / target_throughput) * 20
        score += throughput_score

        return min(100, max(0, score))

    def _assess_targets(
        self,
        config: BenchmarkConfig,
        success_rate: float,
        avg_duration: float,
        throughput: float,
        peak_memory: float,
    ) -> bool:
        """Assess if benchmark meets all targets"""

        if success_rate < config.target_success_rate:
            return False

        if (
            config.target_response_time_ms
            and avg_duration > config.target_response_time_ms
        ):
            return False

        if config.target_throughput_rps and throughput < config.target_throughput_rps:
            return False

        if config.target_memory_mb and peak_memory > config.target_memory_mb:
            return False

        return True

    def _identify_bottlenecks(
        self,
        config: BenchmarkConfig,
        results: List[BenchmarkResult],
        success_rate: float,
        avg_duration: float,
        peak_cpu: float,
        peak_memory: float,
    ) -> List[str]:
        """Identify performance bottlenecks"""
        bottlenecks = []

        if success_rate < 95:
            bottlenecks.append("Low success rate indicates reliability issues")

        if avg_duration > 1000:
            bottlenecks.append("High response times indicate processing bottlenecks")

        if peak_cpu > 80:
            bottlenecks.append("High CPU usage indicates computational bottlenecks")

        if peak_memory > 1000:  # 1GB
            bottlenecks.append("High memory usage indicates memory bottlenecks")

        # Check for error patterns
        error_count = sum(1 for r in results if not r.success)
        if error_count > len(results) * 0.1:
            bottlenecks.append("High error rate indicates system instability")

        return bottlenecks


# Predefined benchmark configurations
class BenchmarkPresets:
    """Predefined benchmark configurations"""

    @staticmethod
    def api_response_time_benchmark(
        base_url: str = "http://localhost:5000",
    ) -> BenchmarkConfig:
        """API response time benchmark"""
        return BenchmarkConfig(
            name="API Response Time Benchmark",
            benchmark_type=BenchmarkType.RESPONSE_TIME,
            iterations=200,
            concurrent_runs=20,
            warm_up_iterations=20,
            target_response_time_ms=500,
            target_success_rate=99.0,
            test_endpoints=[
                "/api/videos",
                "/api/artists",
                "/api/playlists",
                "/api/settings",
            ],
        )

    @staticmethod
    def api_throughput_benchmark(
        base_url: str = "http://localhost:5000",
    ) -> BenchmarkConfig:
        """API throughput benchmark"""
        return BenchmarkConfig(
            name="API Throughput Benchmark",
            benchmark_type=BenchmarkType.THROUGHPUT,
            iterations=1000,
            concurrent_runs=50,
            warm_up_iterations=50,
            target_throughput_rps=100,
            target_success_rate=95.0,
            test_endpoints=["/api/videos", "/api/artists"],
        )

    @staticmethod
    def database_performance_benchmark() -> BenchmarkConfig:
        """Database performance benchmark"""
        return BenchmarkConfig(
            name="Database Performance Benchmark",
            benchmark_type=BenchmarkType.DATABASE_PERFORMANCE,
            iterations=100,
            concurrent_runs=10,
            warm_up_iterations=10,
            target_response_time_ms=100,
            target_success_rate=99.0,
            test_queries=[
                "SELECT COUNT(*) FROM videos",
                "SELECT * FROM videos ORDER BY added_at DESC LIMIT 10",
                "SELECT * FROM artists LIMIT 50",
                "SELECT v.title, a.name FROM videos v JOIN artists a ON v.artist_id = a.id LIMIT 20",
            ],
        )

    @staticmethod
    def cache_performance_benchmark() -> BenchmarkConfig:
        """Cache performance benchmark"""
        return BenchmarkConfig(
            name="Cache Performance Benchmark",
            benchmark_type=BenchmarkType.CACHE_PERFORMANCE,
            iterations=500,
            concurrent_runs=25,
            warm_up_iterations=25,
            target_response_time_ms=10,
            target_success_rate=99.5,
        )

    @staticmethod
    def concurrency_benchmark(
        base_url: str = "http://localhost:5000",
    ) -> BenchmarkConfig:
        """Concurrency handling benchmark"""
        return BenchmarkConfig(
            name="Concurrency Benchmark",
            benchmark_type=BenchmarkType.CONCURRENCY,
            iterations=500,
            concurrent_runs=100,
            warm_up_iterations=50,
            target_success_rate=95.0,
            test_endpoints=["/api/videos", "/api/artists"],
        )

    @staticmethod
    def memory_usage_benchmark() -> BenchmarkConfig:
        """Memory usage benchmark"""
        return BenchmarkConfig(
            name="Memory Usage Benchmark",
            benchmark_type=BenchmarkType.MEMORY_USAGE,
            iterations=50,
            concurrent_runs=5,
            warm_up_iterations=5,
            target_memory_mb=512,
            target_success_rate=100.0,
            test_payload_size_kb=100,
        )


# Utility functions
async def run_benchmark_suite(
    output_dir: str = "benchmark_results",
) -> Dict[str, BenchmarkSummary]:
    """Run complete benchmark suite"""
    os.makedirs(output_dir, exist_ok=True)

    runner = PerformanceBenchmarkRunner()
    await runner.initialize()

    results = {}

    # Define benchmark suite
    benchmarks = [
        BenchmarkPresets.api_response_time_benchmark(),
        BenchmarkPresets.api_throughput_benchmark(),
        BenchmarkPresets.database_performance_benchmark(),
        BenchmarkPresets.cache_performance_benchmark(),
        BenchmarkPresets.concurrency_benchmark(),
        BenchmarkPresets.memory_usage_benchmark(),
    ]

    for benchmark_config in benchmarks:
        try:
            logger.info(f"Running benchmark: {benchmark_config.name}")

            result = await runner.run_benchmark(benchmark_config)
            results[benchmark_config.name] = result

            # Save individual results
            result_filename = f"{output_dir}/{benchmark_config.name.lower().replace(' ', '_')}_results.json"
            with open(result_filename, "w") as f:
                json.dump(asdict(result), f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Benchmark {benchmark_config.name} failed: {e}")

    # Generate summary report
    summary_filename = f"{output_dir}/benchmark_summary.json"
    summary_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "benchmarks": {
            name: {
                "performance_score": result.performance_score,
                "success_rate": result.success_rate,
                "avg_duration_ms": result.avg_duration_ms,
                "throughput_rps": result.throughput_rps,
                "meets_targets": result.meets_targets,
                "bottlenecks": result.bottlenecks,
            }
            for name, result in results.items()
        },
    }

    with open(summary_filename, "w") as f:
        json.dump(summary_data, f, indent=2)

    logger.info(f"Benchmark suite completed. Results saved to {output_dir}")

    return results


async def run_single_benchmark(benchmark_config: BenchmarkConfig) -> BenchmarkSummary:
    """Run a single benchmark"""
    runner = PerformanceBenchmarkRunner()
    await runner.initialize()
    return await runner.run_benchmark(benchmark_config)
