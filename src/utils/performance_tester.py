"""
Performance testing utilities for MVidarr
"""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import requests
from src.utils.logger import get_logger

logger = get_logger("mvidarr.utils.performance_tester")


class PerformanceTester:
    """Performance testing and benchmarking utilities"""

    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []

    def time_request(
        self, url: str, method: str = "GET", data: dict = None, headers: dict = None
    ) -> Dict[str, Any]:
        """Time a single HTTP request"""
        start_time = time.time()

        try:
            if method.upper() == "GET":
                response = self.session.get(url, headers=headers)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            end_time = time.time()
            duration = (end_time - start_time) * 1000  # Convert to milliseconds

            return {
                "url": url,
                "method": method,
                "status_code": response.status_code,
                "duration_ms": duration,
                "response_size": len(response.content),
                "success": response.status_code < 400,
                "timestamp": start_time,
            }

        except Exception as e:
            end_time = time.time()
            duration = (end_time - start_time) * 1000

            return {
                "url": url,
                "method": method,
                "status_code": 0,
                "duration_ms": duration,
                "response_size": 0,
                "success": False,
                "error": str(e),
                "timestamp": start_time,
            }

    def benchmark_endpoint(
        self,
        endpoint: str,
        iterations: int = 10,
        method: str = "GET",
        data: dict = None,
    ) -> Dict[str, Any]:
        """Benchmark a single endpoint with multiple requests"""
        url = f"{self.base_url}{endpoint}"
        results = []

        logger.info(f"Benchmarking {endpoint} with {iterations} iterations")

        for i in range(iterations):
            result = self.time_request(url, method, data)
            results.append(result)

            if i % 5 == 0:
                logger.debug(f"Completed {i+1}/{iterations} requests")

        # Calculate statistics
        successful_requests = [r for r in results if r["success"]]
        durations = [r["duration_ms"] for r in successful_requests]

        if not durations:
            return {
                "endpoint": endpoint,
                "total_requests": iterations,
                "successful_requests": 0,
                "error_rate": 100.0,
                "avg_duration_ms": 0,
                "min_duration_ms": 0,
                "max_duration_ms": 0,
                "median_duration_ms": 0,
                "p95_duration_ms": 0,
                "p99_duration_ms": 0,
                "requests_per_second": 0,
                "results": results,
            }

        stats = {
            "endpoint": endpoint,
            "total_requests": iterations,
            "successful_requests": len(successful_requests),
            "error_rate": (iterations - len(successful_requests)) / iterations * 100,
            "avg_duration_ms": statistics.mean(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "median_duration_ms": statistics.median(durations),
            "p95_duration_ms": self._percentile(durations, 95),
            "p99_duration_ms": self._percentile(durations, 99),
            "requests_per_second": len(successful_requests) / sum(durations) * 1000,
            "results": results,
        }

        return stats

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile from data"""
        if not data:
            return 0

        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)

        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

    def benchmark_search_performance(self) -> Dict[str, Any]:
        """Benchmark search performance with various queries"""
        search_tests = [
            # Artist searches
            {
                "name": "artist_search_simple",
                "endpoint": "/api/artists/search/advanced?search=madonna",
                "method": "GET",
            },
            {
                "name": "artist_search_complex",
                "endpoint": "/api/artists/search/advanced?search=rock&monitored=true&sort=name&order=asc&page=1&per_page=50",
                "method": "GET",
            },
            {
                "name": "artist_list_paginated",
                "endpoint": "/api/artists/?page=1&per_page=100",
                "method": "GET",
            },
            # Video searches
            {
                "name": "video_search_simple",
                "endpoint": "/api/videos/search?q=love",
                "method": "GET",
            },
            {
                "name": "video_search_complex",
                "endpoint": "/api/videos/search?q=rock&artist=madonna&status=downloaded&page=1&per_page=50",
                "method": "GET",
            },
            {
                "name": "video_list_paginated",
                "endpoint": "/api/videos/?page=1&per_page=100",
                "method": "GET",
            },
        ]

        benchmark_results = {}

        for test in search_tests:
            logger.info(f"Running search benchmark: {test['name']}")
            result = self.benchmark_endpoint(
                test["endpoint"], iterations=20, method=test["method"]
            )
            benchmark_results[test["name"]] = result

        return benchmark_results

    def benchmark_concurrent_requests(
        self, endpoint: str, concurrent_users: int = 5, requests_per_user: int = 10
    ) -> Dict[str, Any]:
        """Benchmark with concurrent requests to simulate load"""
        url = f"{self.base_url}{endpoint}"

        logger.info(
            f"Benchmarking {endpoint} with {concurrent_users} concurrent users, "
            f"{requests_per_user} requests each"
        )

        start_time = time.time()
        results = []

        def user_requests():
            user_results = []
            for _ in range(requests_per_user):
                result = self.time_request(url)
                user_results.append(result)
            return user_results

        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(user_requests) for _ in range(concurrent_users)]

            for future in as_completed(futures):
                try:
                    user_results = future.result()
                    results.extend(user_results)
                except Exception as e:
                    logger.error(f"Concurrent request failed: {e}")

        end_time = time.time()
        total_duration = end_time - start_time

        # Calculate statistics
        successful_requests = [r for r in results if r["success"]]
        durations = [r["duration_ms"] for r in successful_requests]

        if not durations:
            return {
                "endpoint": endpoint,
                "concurrent_users": concurrent_users,
                "requests_per_user": requests_per_user,
                "total_requests": len(results),
                "successful_requests": 0,
                "error_rate": 100.0,
                "total_duration_s": total_duration,
                "throughput_rps": 0,
                "avg_duration_ms": 0,
                "results": results,
            }

        stats = {
            "endpoint": endpoint,
            "concurrent_users": concurrent_users,
            "requests_per_user": requests_per_user,
            "total_requests": len(results),
            "successful_requests": len(successful_requests),
            "error_rate": (len(results) - len(successful_requests))
            / len(results)
            * 100,
            "total_duration_s": total_duration,
            "throughput_rps": len(successful_requests) / total_duration,
            "avg_duration_ms": statistics.mean(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "median_duration_ms": statistics.median(durations),
            "p95_duration_ms": self._percentile(durations, 95),
            "p99_duration_ms": self._percentile(durations, 99),
            "results": results,
        }

        return stats

    def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive performance benchmarks"""
        logger.info("Starting comprehensive performance benchmark")

        benchmark_results = {
            "timestamp": time.time(),
            "search_benchmarks": {},
            "concurrent_benchmarks": {},
            "system_info": {"base_url": self.base_url, "total_duration": 0},
        }

        start_time = time.time()

        # Run search benchmarks
        benchmark_results["search_benchmarks"] = self.benchmark_search_performance()

        # Run concurrent benchmarks on key endpoints
        concurrent_tests = [
            "/api/artists/?page=1&per_page=50",
            "/api/videos/search?q=rock",
            "/api/artists/search/advanced?search=pop",
        ]

        for endpoint in concurrent_tests:
            test_name = endpoint.split("/")[-1].split("?")[0]
            if not test_name:
                test_name = endpoint.split("/")[-2]

            benchmark_results["concurrent_benchmarks"][test_name] = (
                self.benchmark_concurrent_requests(
                    endpoint, concurrent_users=3, requests_per_user=5
                )
            )

        end_time = time.time()
        benchmark_results["system_info"]["total_duration"] = end_time - start_time

        logger.info(
            f"Comprehensive benchmark completed in {end_time - start_time:.2f} seconds"
        )

        return benchmark_results

    def save_benchmark_results(self, results: Dict[str, Any], filename: str = None):
        """Save benchmark results to file"""
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"

        output_path = Path("data/logs") / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Benchmark results saved to {output_path}")
        return str(output_path)

    def compare_benchmarks(
        self, before_results: Dict[str, Any], after_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare two benchmark results to show improvements"""
        comparison = {
            "search_improvements": {},
            "concurrent_improvements": {},
            "summary": {
                "overall_improvement": 0,
                "fastest_improvement": 0,
                "slowest_improvement": 0,
                "improved_endpoints": 0,
                "degraded_endpoints": 0,
            },
        }

        # Compare search benchmarks
        for test_name in before_results.get("search_benchmarks", {}):
            if test_name in after_results.get("search_benchmarks", {}):
                before = before_results["search_benchmarks"][test_name]
                after = after_results["search_benchmarks"][test_name]

                improvement = (
                    (before["avg_duration_ms"] - after["avg_duration_ms"])
                    / before["avg_duration_ms"]
                    * 100
                )

                comparison["search_improvements"][test_name] = {
                    "before_avg_ms": before["avg_duration_ms"],
                    "after_avg_ms": after["avg_duration_ms"],
                    "improvement_percent": improvement,
                    "before_p95_ms": before["p95_duration_ms"],
                    "after_p95_ms": after["p95_duration_ms"],
                    "p95_improvement_percent": (
                        before["p95_duration_ms"] - after["p95_duration_ms"]
                    )
                    / before["p95_duration_ms"]
                    * 100,
                }

        # Compare concurrent benchmarks
        for test_name in before_results.get("concurrent_benchmarks", {}):
            if test_name in after_results.get("concurrent_benchmarks", {}):
                before = before_results["concurrent_benchmarks"][test_name]
                after = after_results["concurrent_benchmarks"][test_name]

                improvement = (
                    (before["avg_duration_ms"] - after["avg_duration_ms"])
                    / before["avg_duration_ms"]
                    * 100
                )

                comparison["concurrent_improvements"][test_name] = {
                    "before_avg_ms": before["avg_duration_ms"],
                    "after_avg_ms": after["avg_duration_ms"],
                    "improvement_percent": improvement,
                    "before_throughput_rps": before["throughput_rps"],
                    "after_throughput_rps": after["throughput_rps"],
                    "throughput_improvement_percent": (
                        after["throughput_rps"] - before["throughput_rps"]
                    )
                    / before["throughput_rps"]
                    * 100,
                }

        # Calculate summary statistics
        all_improvements = []
        all_improvements.extend(
            [
                imp["improvement_percent"]
                for imp in comparison["search_improvements"].values()
            ]
        )
        all_improvements.extend(
            [
                imp["improvement_percent"]
                for imp in comparison["concurrent_improvements"].values()
            ]
        )

        if all_improvements:
            comparison["summary"]["overall_improvement"] = statistics.mean(
                all_improvements
            )
            comparison["summary"]["fastest_improvement"] = max(all_improvements)
            comparison["summary"]["slowest_improvement"] = min(all_improvements)
            comparison["summary"]["improved_endpoints"] = len(
                [imp for imp in all_improvements if imp > 0]
            )
            comparison["summary"]["degraded_endpoints"] = len(
                [imp for imp in all_improvements if imp < 0]
            )

        return comparison


# Create global instance
performance_tester = PerformanceTester()
