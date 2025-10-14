"""
Comprehensive Load Testing Framework - Phase 3 Week 35
Advanced load testing, stress testing, and performance validation for MVidarr FastAPI
"""

import asyncio
import json
import statistics
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

from src.utils.logger import get_logger

logger = get_logger("mvidarr.testing.load")


class TestType(Enum):
    """Load test types"""

    SMOKE = "smoke"  # Light load validation
    LOAD = "load"  # Normal expected load
    STRESS = "stress"  # Beyond normal capacity
    SPIKE = "spike"  # Sudden load increases
    VOLUME = "volume"  # Large data volumes
    ENDURANCE = "endurance"  # Extended duration


class TestPhase(Enum):
    """Test execution phases"""

    RAMP_UP = "ramp_up"
    SUSTAIN = "sustain"
    RAMP_DOWN = "ramp_down"
    COOLDOWN = "cooldown"


@dataclass
class LoadTestConfig:
    """Load test configuration"""

    # Test parameters
    base_url: str = "http://localhost:5000"
    test_duration_minutes: int = 5
    max_concurrent_users: int = 100
    ramp_up_duration_minutes: int = 1
    ramp_down_duration_minutes: int = 1

    # Request patterns
    requests_per_second_target: int = 50
    request_timeout_seconds: int = 30
    think_time_seconds: float = 0.1

    # Test scenarios
    endpoint_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "/health": 0.1,
            "/api/videos": 0.3,
            "/api/artists": 0.2,
            "/api/playlists": 0.2,
            "/api/performance": 0.1,
            "/api/settings": 0.1,
        }
    )

    # Performance thresholds
    max_response_time_ms: int = 1000
    max_error_rate_percent: float = 1.0
    min_throughput_rps: int = 40
    max_cpu_percent: float = 80.0
    max_memory_percent: float = 85.0

    # Output configuration
    results_directory: str = "load_test_results"
    generate_report: bool = True
    real_time_monitoring: bool = True


@dataclass
class RequestResult:
    """Individual request result"""

    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    timestamp: datetime
    error: Optional[str] = None
    response_size_bytes: Optional[int] = None
    user_id: Optional[int] = None


@dataclass
class TestMetrics:
    """Test execution metrics"""

    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time_ms: float = 0.0
    min_response_time_ms: float = float("inf")
    max_response_time_ms: float = 0.0

    # Throughput metrics
    requests_per_second: float = 0.0
    avg_response_time_ms: float = 0.0
    median_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0

    # Error metrics
    error_rate_percent: float = 0.0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    status_code_distribution: Dict[int, int] = field(default_factory=dict)

    # System metrics
    avg_cpu_percent: float = 0.0
    max_cpu_percent: float = 0.0
    avg_memory_percent: float = 0.0
    max_memory_percent: float = 0.0

    # Test metadata
    test_start_time: Optional[datetime] = None
    test_end_time: Optional[datetime] = None
    test_duration_seconds: float = 0.0
    concurrent_users: int = 0


class SystemMonitor:
    """Real-time system resource monitoring during load tests"""

    def __init__(self):
        self.monitoring = False
        self.metrics = []
        self.monitor_thread = None

    def start_monitoring(self, interval_seconds: float = 1.0):
        """Start system monitoring"""
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(interval_seconds,), daemon=True
        )
        self.monitor_thread.start()
        logger.info("🖥️ System monitoring started")

    def stop_monitoring(self):
        """Stop system monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("🖥️ System monitoring stopped")

    def _monitor_loop(self, interval: float):
        """System monitoring loop"""
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage("/")

                metric = {
                    "timestamp": datetime.utcnow(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_gb": memory.used / (1024**3),
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_usage_percent": (disk.used / disk.total) * 100,
                    "disk_free_gb": disk.free / (1024**3),
                }

                self.metrics.append(metric)

                time.sleep(interval)

            except Exception as e:
                logger.error(f"System monitoring error: {e}")

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics from monitoring"""
        if not self.metrics:
            return {}

        cpu_values = [m["cpu_percent"] for m in self.metrics]
        memory_values = [m["memory_percent"] for m in self.metrics]

        return {
            "avg_cpu_percent": statistics.mean(cpu_values),
            "max_cpu_percent": max(cpu_values),
            "avg_memory_percent": statistics.mean(memory_values),
            "max_memory_percent": max(memory_values),
            "sample_count": len(self.metrics),
            "monitoring_duration_seconds": (
                (
                    self.metrics[-1]["timestamp"] - self.metrics[0]["timestamp"]
                ).total_seconds()
                if len(self.metrics) > 1
                else 0
            ),
        }


class VirtualUser:
    """Virtual user for load testing"""

    def __init__(
        self, user_id: int, config: LoadTestConfig, session: aiohttp.ClientSession
    ):
        self.user_id = user_id
        self.config = config
        self.session = session
        self.results: List[RequestResult] = []
        self.active = True

    async def run_scenario(self, duration_seconds: float) -> List[RequestResult]:
        """Run user scenario for specified duration"""
        start_time = time.time()

        while (time.time() - start_time) < duration_seconds and self.active:
            # Select endpoint based on weights
            endpoint = self._select_endpoint()

            # Make request
            result = await self._make_request(endpoint)
            self.results.append(result)

            # Think time between requests
            if self.config.think_time_seconds > 0:
                await asyncio.sleep(self.config.think_time_seconds)

        return self.results

    def _select_endpoint(self) -> str:
        """Select endpoint based on configured weights"""
        import random

        endpoints = list(self.config.endpoint_weights.keys())
        weights = list(self.config.endpoint_weights.values())

        return random.choices(endpoints, weights=weights)[0]

    async def _make_request(self, endpoint: str) -> RequestResult:
        """Make HTTP request and record result"""
        start_time = time.time()
        timestamp = datetime.utcnow()

        try:
            url = f"{self.config.base_url}{endpoint}"

            async with self.session.get(
                url,
                timeout=aiohttp.ClientTimeout(
                    total=self.config.request_timeout_seconds
                ),
                headers={
                    "Accept": "application/json",
                    "User-Agent": f"LoadTest-User-{self.user_id}",
                },
            ) as response:
                await response.text()  # Read response body

                response_time_ms = (time.time() - start_time) * 1000

                return RequestResult(
                    endpoint=endpoint,
                    method="GET",
                    status_code=response.status,
                    response_time_ms=response_time_ms,
                    timestamp=timestamp,
                    response_size_bytes=(
                        len(await response.read())
                        if hasattr(response, "read")
                        else None
                    ),
                    user_id=self.user_id,
                )

        except asyncio.TimeoutError:
            response_time_ms = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=endpoint,
                method="GET",
                status_code=408,
                response_time_ms=response_time_ms,
                timestamp=timestamp,
                error="Request timeout",
                user_id=self.user_id,
            )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            return RequestResult(
                endpoint=endpoint,
                method="GET",
                status_code=0,
                response_time_ms=response_time_ms,
                timestamp=timestamp,
                error=str(e),
                user_id=self.user_id,
            )

    def stop(self):
        """Stop the virtual user"""
        self.active = False


class LoadTestExecutor:
    """Main load test execution engine"""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.system_monitor = SystemMonitor()
        self.users: List[VirtualUser] = []
        self.results: List[RequestResult] = []

        # Ensure results directory exists
        Path(config.results_directory).mkdir(parents=True, exist_ok=True)

    async def execute_load_test(
        self, test_type: TestType = TestType.LOAD
    ) -> TestMetrics:
        """Execute comprehensive load test"""
        logger.info(f"🚀 Starting {test_type.value} load test")

        # Start system monitoring
        self.system_monitor.start_monitoring()

        test_start = datetime.utcnow()

        try:
            # Create HTTP session
            connector = aiohttp.TCPConnector(
                limit=self.config.max_concurrent_users * 2,
                limit_per_host=self.config.max_concurrent_users,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )

            async with aiohttp.ClientSession(connector=connector) as session:
                # Execute test phases
                await self._execute_ramp_up_phase(session)
                await self._execute_sustain_phase(session)
                await self._execute_ramp_down_phase(session)

        except Exception as e:
            logger.error(f"Load test execution error: {e}")
        finally:
            # Stop monitoring
            self.system_monitor.stop_monitoring()

            # Stop all users
            for user in self.users:
                user.stop()

        test_end = datetime.utcnow()

        # Collect results
        self._collect_results()

        # Calculate metrics
        metrics = self._calculate_metrics(test_start, test_end)

        # Generate report
        if self.config.generate_report:
            await self._generate_test_report(metrics, test_type)

        logger.info(f"✅ {test_type.value} load test completed")
        return metrics

    async def _execute_ramp_up_phase(self, session: aiohttp.ClientSession):
        """Execute ramp-up phase"""
        logger.info("📈 Executing ramp-up phase")

        ramp_duration = self.config.ramp_up_duration_minutes * 60
        user_spawn_interval = ramp_duration / self.config.max_concurrent_users

        tasks = []

        for user_id in range(self.config.max_concurrent_users):
            # Create and start virtual user
            user = VirtualUser(user_id, self.config, session)
            self.users.append(user)

            # Start user scenario
            scenario_duration = ramp_duration + (self.config.test_duration_minutes * 60)
            task = asyncio.create_task(user.run_scenario(scenario_duration))
            tasks.append(task)

            # Stagger user creation
            if user_spawn_interval > 0:
                await asyncio.sleep(user_spawn_interval)

        # Wait for ramp-up to complete
        await asyncio.sleep(ramp_duration)

    async def _execute_sustain_phase(self, session: aiohttp.ClientSession):
        """Execute sustained load phase"""
        logger.info("⚡ Executing sustained load phase")

        sustain_duration = self.config.test_duration_minutes * 60
        await asyncio.sleep(sustain_duration)

    async def _execute_ramp_down_phase(self, session: aiohttp.ClientSession):
        """Execute ramp-down phase"""
        logger.info("📉 Executing ramp-down phase")

        ramp_down_duration = self.config.ramp_down_duration_minutes * 60
        users_per_interval = len(self.users) / max(ramp_down_duration, 1)

        # Gradually stop users
        for i, user in enumerate(self.users):
            if i % max(int(users_per_interval), 1) == 0:
                await asyncio.sleep(1)
            user.stop()

    def _collect_results(self):
        """Collect results from all virtual users"""
        self.results = []
        for user in self.users:
            self.results.extend(user.results)

        logger.info(f"📊 Collected {len(self.results)} request results")

    def _calculate_metrics(
        self, start_time: datetime, end_time: datetime
    ) -> TestMetrics:
        """Calculate comprehensive test metrics"""
        metrics = TestMetrics()

        if not self.results:
            return metrics

        # Basic counts
        metrics.total_requests = len(self.results)
        metrics.successful_requests = sum(
            1 for r in self.results if 200 <= r.status_code < 400
        )
        metrics.failed_requests = metrics.total_requests - metrics.successful_requests
        metrics.concurrent_users = len(self.users)

        # Response times
        response_times = [r.response_time_ms for r in self.results]
        metrics.total_response_time_ms = sum(response_times)
        metrics.min_response_time_ms = min(response_times)
        metrics.max_response_time_ms = max(response_times)
        metrics.avg_response_time_ms = statistics.mean(response_times)
        metrics.median_response_time_ms = statistics.median(response_times)

        # Percentiles
        response_times_sorted = sorted(response_times)
        metrics.p95_response_time_ms = response_times_sorted[
            int(len(response_times_sorted) * 0.95)
        ]
        metrics.p99_response_time_ms = response_times_sorted[
            int(len(response_times_sorted) * 0.99)
        ]

        # Error rates
        metrics.error_rate_percent = (
            metrics.failed_requests / metrics.total_requests
        ) * 100

        # Status code distribution
        for result in self.results:
            metrics.status_code_distribution[result.status_code] = (
                metrics.status_code_distribution.get(result.status_code, 0) + 1
            )

        # Errors by type
        for result in self.results:
            if result.error:
                metrics.errors_by_type[result.error] = (
                    metrics.errors_by_type.get(result.error, 0) + 1
                )

        # Throughput
        test_duration = (end_time - start_time).total_seconds()
        metrics.requests_per_second = (
            metrics.total_requests / test_duration if test_duration > 0 else 0
        )

        # System metrics
        system_stats = self.system_monitor.get_summary_stats()
        metrics.avg_cpu_percent = system_stats.get("avg_cpu_percent", 0)
        metrics.max_cpu_percent = system_stats.get("max_cpu_percent", 0)
        metrics.avg_memory_percent = system_stats.get("avg_memory_percent", 0)
        metrics.max_memory_percent = system_stats.get("max_memory_percent", 0)

        # Test metadata
        metrics.test_start_time = start_time
        metrics.test_end_time = end_time
        metrics.test_duration_seconds = test_duration

        return metrics

    async def _generate_test_report(self, metrics: TestMetrics, test_type: TestType):
        """Generate comprehensive test report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = (
            Path(self.config.results_directory)
            / f"{test_type.value}_report_{timestamp}.json"
        )

        # Performance assessment
        performance_grade = self._assess_performance(metrics)

        report = {
            "test_metadata": {
                "test_type": test_type.value,
                "test_start": (
                    metrics.test_start_time.isoformat()
                    if metrics.test_start_time
                    else None
                ),
                "test_end": (
                    metrics.test_end_time.isoformat() if metrics.test_end_time else None
                ),
                "duration_seconds": metrics.test_duration_seconds,
                "concurrent_users": metrics.concurrent_users,
                "target_rps": self.config.requests_per_second_target,
            },
            "request_metrics": {
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "error_rate_percent": round(metrics.error_rate_percent, 2),
                "requests_per_second": round(metrics.requests_per_second, 2),
            },
            "response_time_metrics": {
                "avg_response_time_ms": round(metrics.avg_response_time_ms, 2),
                "median_response_time_ms": round(metrics.median_response_time_ms, 2),
                "p95_response_time_ms": round(metrics.p95_response_time_ms, 2),
                "p99_response_time_ms": round(metrics.p99_response_time_ms, 2),
                "min_response_time_ms": round(metrics.min_response_time_ms, 2),
                "max_response_time_ms": round(metrics.max_response_time_ms, 2),
            },
            "system_metrics": {
                "avg_cpu_percent": round(metrics.avg_cpu_percent, 2),
                "max_cpu_percent": round(metrics.max_cpu_percent, 2),
                "avg_memory_percent": round(metrics.avg_memory_percent, 2),
                "max_memory_percent": round(metrics.max_memory_percent, 2),
            },
            "error_analysis": {
                "status_code_distribution": metrics.status_code_distribution,
                "errors_by_type": metrics.errors_by_type,
            },
            "performance_assessment": performance_grade,
            "test_configuration": {
                "base_url": self.config.base_url,
                "max_concurrent_users": self.config.max_concurrent_users,
                "test_duration_minutes": self.config.test_duration_minutes,
                "endpoint_weights": self.config.endpoint_weights,
            },
        }

        # Write report
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"📋 Test report generated: {report_file}")

        # Log summary
        logger.info(f"📊 Load Test Summary:")
        logger.info(f"   Total Requests: {metrics.total_requests}")
        logger.info(f"   Success Rate: {100 - metrics.error_rate_percent:.1f}%")
        logger.info(f"   Avg Response Time: {metrics.avg_response_time_ms:.1f}ms")
        logger.info(f"   Throughput: {metrics.requests_per_second:.1f} RPS")
        logger.info(f"   Performance Grade: {performance_grade['overall_grade']}")

    def _assess_performance(self, metrics: TestMetrics) -> Dict[str, Any]:
        """Assess overall performance against thresholds"""
        assessment = {
            "overall_grade": "UNKNOWN",
            "criteria_scores": {},
            "issues": [],
            "recommendations": [],
        }

        score = 0
        max_score = 0

        # Response time assessment (25 points)
        max_score += 25
        if metrics.avg_response_time_ms <= self.config.max_response_time_ms * 0.5:
            score += 25
            assessment["criteria_scores"]["response_time"] = "EXCELLENT"
        elif metrics.avg_response_time_ms <= self.config.max_response_time_ms:
            score += 20
            assessment["criteria_scores"]["response_time"] = "GOOD"
        elif metrics.avg_response_time_ms <= self.config.max_response_time_ms * 1.5:
            score += 15
            assessment["criteria_scores"]["response_time"] = "ACCEPTABLE"
            assessment["issues"].append(
                f"Average response time {metrics.avg_response_time_ms:.1f}ms exceeds target"
            )
        else:
            score += 5
            assessment["criteria_scores"]["response_time"] = "POOR"
            assessment["issues"].append(
                f"Average response time {metrics.avg_response_time_ms:.1f}ms significantly exceeds target"
            )
            assessment["recommendations"].append(
                "Investigate slow endpoints and optimize database queries"
            )

        # Error rate assessment (25 points)
        max_score += 25
        if metrics.error_rate_percent <= self.config.max_error_rate_percent * 0.2:
            score += 25
            assessment["criteria_scores"]["error_rate"] = "EXCELLENT"
        elif metrics.error_rate_percent <= self.config.max_error_rate_percent:
            score += 20
            assessment["criteria_scores"]["error_rate"] = "GOOD"
        elif metrics.error_rate_percent <= self.config.max_error_rate_percent * 2:
            score += 10
            assessment["criteria_scores"]["error_rate"] = "ACCEPTABLE"
            assessment["issues"].append(
                f"Error rate {metrics.error_rate_percent:.1f}% exceeds target"
            )
        else:
            score += 0
            assessment["criteria_scores"]["error_rate"] = "POOR"
            assessment["issues"].append(
                f"Error rate {metrics.error_rate_percent:.1f}% significantly exceeds target"
            )
            assessment["recommendations"].append(
                "Investigate error causes and implement proper error handling"
            )

        # Throughput assessment (25 points)
        max_score += 25
        if metrics.requests_per_second >= self.config.min_throughput_rps * 1.2:
            score += 25
            assessment["criteria_scores"]["throughput"] = "EXCELLENT"
        elif metrics.requests_per_second >= self.config.min_throughput_rps:
            score += 20
            assessment["criteria_scores"]["throughput"] = "GOOD"
        elif metrics.requests_per_second >= self.config.min_throughput_rps * 0.8:
            score += 15
            assessment["criteria_scores"]["throughput"] = "ACCEPTABLE"
            assessment["issues"].append(
                f"Throughput {metrics.requests_per_second:.1f} RPS below target"
            )
        else:
            score += 5
            assessment["criteria_scores"]["throughput"] = "POOR"
            assessment["issues"].append(
                f"Throughput {metrics.requests_per_second:.1f} RPS significantly below target"
            )
            assessment["recommendations"].append(
                "Consider horizontal scaling or performance optimizations"
            )

        # System resource assessment (25 points)
        max_score += 25
        cpu_ok = metrics.max_cpu_percent <= self.config.max_cpu_percent
        memory_ok = metrics.max_memory_percent <= self.config.max_memory_percent

        if cpu_ok and memory_ok:
            if (
                metrics.max_cpu_percent <= self.config.max_cpu_percent * 0.7
                and metrics.max_memory_percent <= self.config.max_memory_percent * 0.7
            ):
                score += 25
                assessment["criteria_scores"]["system_resources"] = "EXCELLENT"
            else:
                score += 20
                assessment["criteria_scores"]["system_resources"] = "GOOD"
        elif cpu_ok or memory_ok:
            score += 15
            assessment["criteria_scores"]["system_resources"] = "ACCEPTABLE"
            if not cpu_ok:
                assessment["issues"].append(
                    f"CPU usage {metrics.max_cpu_percent:.1f}% exceeds threshold"
                )
            if not memory_ok:
                assessment["issues"].append(
                    f"Memory usage {metrics.max_memory_percent:.1f}% exceeds threshold"
                )
        else:
            score += 5
            assessment["criteria_scores"]["system_resources"] = "POOR"
            assessment["issues"].append(
                f"Both CPU ({metrics.max_cpu_percent:.1f}%) and memory ({metrics.max_memory_percent:.1f}%) exceed thresholds"
            )
            assessment["recommendations"].append(
                "System resources constrained - consider scaling up or optimizing resource usage"
            )

        # Calculate overall grade
        percentage = (score / max_score) * 100

        if percentage >= 90:
            assessment["overall_grade"] = "A"
        elif percentage >= 80:
            assessment["overall_grade"] = "B"
        elif percentage >= 70:
            assessment["overall_grade"] = "C"
        elif percentage >= 60:
            assessment["overall_grade"] = "D"
        else:
            assessment["overall_grade"] = "F"

        assessment["score_percentage"] = round(percentage, 1)

        return assessment


# Convenience functions for different test types
async def run_smoke_test(base_url: str = "http://localhost:5000") -> TestMetrics:
    """Run smoke test with light load"""
    config = LoadTestConfig(
        base_url=base_url,
        test_duration_minutes=1,
        max_concurrent_users=5,
        requests_per_second_target=10,
        ramp_up_duration_minutes=0.5,
        ramp_down_duration_minutes=0.5,
    )

    executor = LoadTestExecutor(config)
    return await executor.execute_load_test(TestType.SMOKE)


async def run_load_test(base_url: str = "http://localhost:5000") -> TestMetrics:
    """Run standard load test"""
    config = LoadTestConfig(
        base_url=base_url,
        test_duration_minutes=5,
        max_concurrent_users=50,
        requests_per_second_target=40,
    )

    executor = LoadTestExecutor(config)
    return await executor.execute_load_test(TestType.LOAD)


async def run_stress_test(base_url: str = "http://localhost:5000") -> TestMetrics:
    """Run stress test with high load"""
    config = LoadTestConfig(
        base_url=base_url,
        test_duration_minutes=10,
        max_concurrent_users=200,
        requests_per_second_target=100,
        max_response_time_ms=2000,
        max_error_rate_percent=5.0,
    )

    executor = LoadTestExecutor(config)
    return await executor.execute_load_test(TestType.STRESS)


# CLI interface for running tests
if __name__ == "__main__":
    import sys

    async def main():
        test_type = sys.argv[1] if len(sys.argv) > 1 else "load"
        base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:5000"

        if test_type == "smoke":
            await run_smoke_test(base_url)
        elif test_type == "stress":
            await run_stress_test(base_url)
        else:
            await run_load_test(base_url)

    asyncio.run(main())
