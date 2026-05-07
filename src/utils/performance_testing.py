"""
Production Performance Testing and Validation
Real-world performance testing tools for Phase 3 validation
"""

import json
import statistics
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.utils.logger import get_logger

logger = get_logger("mvidarr.performance.testing")


class ProductionPerformanceTester:
    """Test performance against running MVidarr instance"""

    def __init__(self, base_url: str = "http://localhost:5001"):
        self.base_url = base_url.rstrip("/")
        self.test_results = {}

    def test_endpoint_performance(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        iterations: int = 10,
    ) -> Dict[str, Any]:
        """Test performance of a specific endpoint"""

        url = f"{self.base_url}{endpoint}"
        times = []
        errors = []

        logger.info(f"Testing {method} {endpoint} ({iterations} iterations)")

        for i in range(iterations):
            try:
                start_time = time.time()

                if method.upper() == "GET":
                    response = requests.get(url, params=params, timeout=30)
                elif method.upper() == "POST":
                    response = requests.post(url, json=data, timeout=30)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                end_time = time.time()
                response_time = end_time - start_time

                if response.status_code == 200:
                    times.append(response_time)
                else:
                    errors.append(
                        {
                            "iteration": i,
                            "status_code": response.status_code,
                            "response_time": response_time,
                            "error": response.text[:200],
                        }
                    )

            except requests.RequestException as e:
                errors.append({"iteration": i, "error": str(e), "response_time": None})

        if not times:
            return {
                "endpoint": endpoint,
                "status": "FAILED",
                "error": f"All {iterations} requests failed",
                "errors": errors,
            }

        return {
            "endpoint": endpoint,
            "method": method,
            "iterations": len(times),
            "errors": len(errors),
            "avg_time": statistics.mean(times),
            "min_time": min(times),
            "max_time": max(times),
            "median_time": statistics.median(times),
            "p95_time": self._percentile(times, 95),
            "success_rate": len(times) / iterations * 100,
            "status": "SUCCESS" if len(errors) == 0 else "PARTIAL",
            "error_details": errors if errors else None,
        }

    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(percentile / 100 * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]

    def test_video_list_scenarios(self) -> Dict[str, Any]:
        """Test the optimized video list endpoint scenarios"""

        scenarios = {
            "default_list": {
                "endpoint": "/api/videos/",
                "params": {"sort": "title", "order": "asc"},
                "expected": "FAST - No JOIN optimization",
            },
            "sort_by_date": {
                "endpoint": "/api/videos/",
                "params": {"sort": "created_at", "order": "desc"},
                "expected": "FAST - No JOIN optimization",
            },
            "sort_by_artist": {
                "endpoint": "/api/videos/",
                "params": {"sort": "artist_name", "order": "asc"},
                "expected": "SLOWER - Requires JOIN (expected)",
            },
            "paginated": {
                "endpoint": "/api/videos/",
                "params": {"sort": "title", "limit": 25, "offset": 50},
                "expected": "FAST - Optimized count query",
            },
            "status_filter": {
                "endpoint": "/api/videos/search",
                "params": {"status": "DOWNLOADED", "sort": "title", "order": "asc"},
                "expected": "MODERATE - Uses performance optimizer",
            },
        }

        results = {}

        for scenario_name, config in scenarios.items():
            logger.info(f"Testing scenario: {scenario_name}")
            result = self.test_endpoint_performance(
                config["endpoint"], params=config["params"], iterations=15
            )
            result["expected_performance"] = config["expected"]
            results[scenario_name] = result

        return results

    def test_monitoring_endpoints(self) -> Dict[str, Any]:
        """Test the performance monitoring endpoints"""

        monitoring_endpoints = {
            "performance_summary": "/api/performance/summary",
            "performance_stats": "/api/performance/stats",
            "performance_slow": "/api/performance/slow?threshold=500",
            "performance_health": "/api/performance/health",
        }

        results = {}

        for name, endpoint in monitoring_endpoints.items():
            result = self.test_endpoint_performance(endpoint, iterations=5)
            results[name] = result

        return results

    def validate_optimization_impact(
        self, video_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze optimization effectiveness from real test results"""

        optimized_scenarios = ["default_list", "sort_by_date", "paginated"]
        unoptimized_scenarios = ["sort_by_artist"]

        optimized_times = []
        unoptimized_times = []

        analysis = {
            "optimized_performance": {},
            "unoptimized_performance": {},
            "performance_gap": {},
            "optimization_effective": False,
            "issues_found": [],
        }

        # Collect optimized scenario performance
        for scenario in optimized_scenarios:
            if scenario in video_results and video_results[scenario].get("avg_time"):
                optimized_times.append(video_results[scenario]["avg_time"])
                analysis["optimized_performance"][scenario] = {
                    "avg_time": video_results[scenario]["avg_time"],
                    "success_rate": video_results[scenario].get("success_rate", 0),
                }

        # Collect unoptimized scenario performance
        for scenario in unoptimized_scenarios:
            if scenario in video_results and video_results[scenario].get("avg_time"):
                unoptimized_times.append(video_results[scenario]["avg_time"])
                analysis["unoptimized_performance"][scenario] = {
                    "avg_time": video_results[scenario]["avg_time"],
                    "success_rate": video_results[scenario].get("success_rate", 0),
                }

        # Calculate performance gap
        if optimized_times and unoptimized_times:
            optimized_avg = statistics.mean(optimized_times)
            unoptimized_avg = statistics.mean(unoptimized_times)
            gap_percent = ((unoptimized_avg - optimized_avg) / unoptimized_avg) * 100

            analysis["performance_gap"] = {
                "optimized_avg": optimized_avg,
                "unoptimized_avg": unoptimized_avg,
                "improvement_percent": gap_percent,
                "meets_expectations": gap_percent > 20,  # Expected 30-50% improvement
            }

            analysis["optimization_effective"] = gap_percent > 10

        # Check for issues
        for scenario, result in video_results.items():
            if result.get("success_rate", 0) < 100:
                analysis["issues_found"].append(
                    f"{scenario}: {result.get('errors', 0)} errors"
                )

            if result.get("avg_time", 0) > 1.0:  # Slow responses
                analysis["issues_found"].append(
                    f"{scenario}: Slow response ({result['avg_time']:.3f}s)"
                )

        return analysis

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance test report"""

        logger.info("Starting comprehensive performance testing...")

        # Test video list scenarios (our main optimization target)
        video_results = self.test_video_list_scenarios()

        # Test monitoring endpoints
        monitoring_results = self.test_monitoring_endpoints()

        # Analyze optimization effectiveness
        optimization_analysis = self.validate_optimization_impact(video_results)

        # Generate overall assessment
        report = {
            "test_timestamp": datetime.now().isoformat(),
            "test_target": self.base_url,
            "test_results": {
                "video_endpoints": video_results,
                "monitoring_endpoints": monitoring_results,
            },
            "optimization_analysis": optimization_analysis,
            "overall_status": self._assess_overall_status(
                video_results, optimization_analysis
            ),
            "recommendations": self._generate_recommendations(
                video_results, optimization_analysis
            ),
        }

        return report

    def _assess_overall_status(
        self, video_results: Dict, optimization_analysis: Dict
    ) -> str:
        """Assess overall performance status"""

        # Check if optimization is effective
        if optimization_analysis.get("optimization_effective", False):
            if optimization_analysis.get("performance_gap", {}).get(
                "meets_expectations", False
            ):
                return "EXCELLENT - Optimization exceeds expectations"
            else:
                return "GOOD - Optimization shows measurable improvement"

        # Check for critical issues
        error_count = sum(
            1 for result in video_results.values() if result.get("errors", 0) > 0
        )
        if error_count > 0:
            return "ISSUES - Errors detected in testing"

        # Check response times
        slow_count = sum(
            1 for result in video_results.values() if result.get("avg_time", 0) > 1.0
        )
        if slow_count > 0:
            return "SLOW - Response times need optimization"

        return "UNKNOWN - Unable to determine optimization effectiveness"

    def _generate_recommendations(
        self, video_results: Dict, optimization_analysis: Dict
    ) -> List[str]:
        """Generate actionable recommendations"""

        recommendations = []

        # Optimization-specific recommendations
        if optimization_analysis.get("optimization_effective", False):
            gap = optimization_analysis.get("performance_gap", {}).get(
                "improvement_percent", 0
            )
            recommendations.append(
                f"✅ Phase 2 optimization successful: {gap:.1f}% improvement achieved"
            )
        else:
            recommendations.append(
                "⚠️ Phase 2 optimization impact unclear - investigate further"
            )

        # Error-specific recommendations
        for scenario, result in video_results.items():
            if result.get("errors", 0) > 0:
                recommendations.append(
                    f"🔧 Fix errors in {scenario} endpoint ({result['errors']} errors)"
                )

            if result.get("avg_time", 0) > 1.0:
                recommendations.append(
                    f"⚡ Optimize {scenario} performance ({result['avg_time']:.3f}s avg)"
                )

        # Monitoring recommendations
        recommendations.append(
            "📊 Continue monitoring performance with: curl http://localhost:5001/api/performance/summary"
        )

        # Next steps
        if optimization_analysis.get("optimization_effective", False):
            recommendations.append("🎯 Focus on remaining medium-priority bottlenecks")
        else:
            recommendations.append(
                "🔍 Investigate why optimization didn't show expected impact"
            )

        return recommendations


def main():
    """Run production performance validation"""

    print("🚀 PRODUCTION PERFORMANCE TESTING - PHASE 3")
    print("=" * 60)

    # Test against local development server
    tester = ProductionPerformanceTester()

    try:
        report = tester.generate_performance_report()

        # Save detailed report
        with open("production_performance_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)

        # Print summary
        print("\n📊 PERFORMANCE TEST RESULTS")
        print("=" * 40)
        print(f"Overall Status: {report['overall_status']}")

        print("\n💡 RECOMMENDATIONS:")
        for rec in report["recommendations"]:
            print(f"  {rec}")

        print(f"\n💾 Detailed report saved: production_performance_report.json")

        return report

    except requests.ConnectionError:
        print("❌ Cannot connect to MVidarr server")
        print("💡 Start the server with: python src/app_with_simple_auth.py")
        print("💡 Or run validation against different URL")
        return None

    except Exception as e:
        print(f"❌ Performance testing failed: {e}")
        return None


if __name__ == "__main__":
    main()
