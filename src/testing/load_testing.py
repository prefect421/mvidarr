"""
Load Testing Framework - Issue 129 Performance Optimization & Load Testing
Comprehensive API performance testing and benchmarking framework
"""

import asyncio
import aiohttp
import time
import json
import statistics
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import csv
import logging
from concurrent.futures import ThreadPoolExecutor
import psutil
import memory_profiler

from src.utils.logger import get_logger

logger = get_logger("mvidarr.testing.load_testing")

class LoadTestType(Enum):
    """Types of load tests"""
    SMOKE = "smoke"           # Light testing to verify basic functionality
    LOAD = "load"             # Normal expected load
    STRESS = "stress"         # Beyond normal capacity
    SPIKE = "spike"           # Sudden load increases
    VOLUME = "volume"         # Large amounts of data
    ENDURANCE = "endurance"   # Extended duration testing

@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    name: str
    base_url: str
    test_type: LoadTestType
    
    # Load parameters
    concurrent_users: int = 10
    total_requests: int = 100
    duration_seconds: Optional[int] = None
    ramp_up_time: int = 10  # seconds to reach target concurrency
    
    # Request configuration
    endpoints: List[str] = None
    request_methods: Dict[str, str] = None  # endpoint -> method mapping
    request_headers: Dict[str, str] = None
    request_payloads: Dict[str, Any] = None  # endpoint -> payload mapping
    authentication: Optional[Dict[str, str]] = None
    
    # Performance thresholds
    max_response_time_ms: float = 1000.0
    min_success_rate: float = 95.0
    max_error_rate: float = 5.0
    target_throughput_rps: Optional[float] = None
    
    # Monitoring
    monitor_system_resources: bool = True
    monitor_database: bool = True
    monitor_cache: bool = True
    
    # Output
    generate_report: bool = True
    output_format: str = "json"  # json, csv, html
    save_results: bool = True

@dataclass
class RequestResult:
    """Result of a single request"""
    timestamp: float
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    success: bool
    error_message: Optional[str] = None
    response_size_bytes: int = 0
    user_id: int = 0

@dataclass
class SystemMetrics:
    """System resource metrics during testing"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_received_mb: float
    active_connections: int

@dataclass
class LoadTestResults:
    """Comprehensive load test results"""
    config: LoadTestConfig
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    
    # Request statistics
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    error_rate: float
    
    # Response time statistics
    min_response_time: float
    max_response_time: float
    avg_response_time: float
    median_response_time: float
    p95_response_time: float
    p99_response_time: float
    
    # Throughput statistics
    requests_per_second: float
    bytes_per_second: float
    
    # Error analysis
    error_types: Dict[str, int]
    status_code_distribution: Dict[int, int]
    
    # System metrics
    system_metrics: List[SystemMetrics]
    peak_cpu_usage: float
    peak_memory_usage: float
    
    # Performance assessment
    performance_grade: str
    bottlenecks_identified: List[str]
    recommendations: List[str]

class LoadTestRunner:
    """Main load testing runner"""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.system_metrics: List[SystemMetrics] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time: Optional[datetime] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        
    async def run_test(self) -> LoadTestResults:
        """Execute the load test"""
        logger.info(f"Starting load test: {self.config.name}")
        
        try:
            # Initialize test session
            await self._initialize_session()
            
            # Start system monitoring
            if self.config.monitor_system_resources:
                self.monitoring_task = asyncio.create_task(self._monitor_system())
            
            self.start_time = datetime.utcnow()
            
            # Execute test based on type
            if self.config.test_type == LoadTestType.SMOKE:
                await self._run_smoke_test()
            elif self.config.test_type == LoadTestType.LOAD:
                await self._run_load_test()
            elif self.config.test_type == LoadTestType.STRESS:
                await self._run_stress_test()
            elif self.config.test_type == LoadTestType.SPIKE:
                await self._run_spike_test()
            elif self.config.test_type == LoadTestType.ENDURANCE:
                await self._run_endurance_test()
            else:
                await self._run_load_test()  # Default to load test
            
            end_time = datetime.utcnow()
            
            # Stop monitoring
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
            
            # Generate results
            results = await self._generate_results(end_time)
            
            logger.info(f"Load test completed: {results.success_rate:.1f}% success rate")
            
            return results
            
        finally:
            await self._cleanup()
    
    async def _initialize_session(self):
        """Initialize HTTP session with proper configuration"""
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(
            limit=self.config.concurrent_users * 2,
            limit_per_host=self.config.concurrent_users,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30
        )
        
        headers = self.config.request_headers or {}
        if self.config.authentication:
            if 'bearer_token' in self.config.authentication:
                headers['Authorization'] = f"Bearer {self.config.authentication['bearer_token']}"
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers
        )
    
    async def _run_smoke_test(self):
        """Run smoke test - light load to verify functionality"""
        logger.info("Executing smoke test")
        
        endpoints = self.config.endpoints or ['/api/videos', '/api/artists', '/api/playlists']
        
        # Test each endpoint once
        tasks = []
        for i, endpoint in enumerate(endpoints):
            task = self._make_request(endpoint, i, 0)
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_load_test(self):
        """Run standard load test with concurrent users"""
        logger.info(f"Executing load test with {self.config.concurrent_users} concurrent users")
        
        endpoints = self.config.endpoints or ['/api/videos', '/api/artists', '/api/playlists']
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.config.concurrent_users)
        
        # Calculate requests per user
        requests_per_user = self.config.total_requests // self.config.concurrent_users
        
        tasks = []
        for user_id in range(self.config.concurrent_users):
            for request_id in range(requests_per_user):
                endpoint = endpoints[request_id % len(endpoints)]
                
                # Add ramp-up delay
                delay = (user_id / self.config.concurrent_users) * self.config.ramp_up_time
                
                task = self._make_delayed_request(semaphore, endpoint, request_id, user_id, delay)
                tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_stress_test(self):
        """Run stress test - beyond normal capacity"""
        logger.info(f"Executing stress test with {self.config.concurrent_users} concurrent users")
        
        # Gradually increase load
        max_users = self.config.concurrent_users
        steps = 5
        step_duration = self.config.duration_seconds // steps if self.config.duration_seconds else 60
        
        for step in range(steps):
            current_users = int(max_users * (step + 1) / steps)
            logger.info(f"Stress test step {step + 1}/{steps}: {current_users} users")
            
            # Run load for this step
            step_config = LoadTestConfig(
                name=f"{self.config.name}_step_{step}",
                base_url=self.config.base_url,
                test_type=LoadTestType.LOAD,
                concurrent_users=current_users,
                total_requests=current_users * 10,
                endpoints=self.config.endpoints
            )
            
            step_runner = LoadTestRunner(step_config)
            await step_runner._initialize_session()
            await step_runner._run_load_test()
            self.results.extend(step_runner.results)
            await step_runner._cleanup()
            
            # Brief pause between steps
            await asyncio.sleep(5)
    
    async def _run_spike_test(self):
        """Run spike test - sudden load increases"""
        logger.info("Executing spike test")
        
        # Normal load phase
        normal_load = self.config.concurrent_users // 4
        await self._run_phase("normal", normal_load, 30)
        
        # Spike phase
        spike_load = self.config.concurrent_users
        await self._run_phase("spike", spike_load, 60)
        
        # Recovery phase  
        await self._run_phase("recovery", normal_load, 30)
    
    async def _run_endurance_test(self):
        """Run endurance test - extended duration"""
        duration = self.config.duration_seconds or 3600  # 1 hour default
        logger.info(f"Executing endurance test for {duration} seconds")
        
        end_time = time.time() + duration
        request_interval = 1.0 / (self.config.concurrent_users * 2)  # Conservative rate
        
        tasks = []
        request_id = 0
        
        while time.time() < end_time:
            for user_id in range(self.config.concurrent_users):
                endpoint = (self.config.endpoints or ['/api/videos'])[0]
                task = self._make_request(endpoint, request_id, user_id)
                tasks.append(task)
                request_id += 1
                
                # Control rate
                await asyncio.sleep(request_interval)
                
                # Process completed tasks periodically
                if len(tasks) >= 100:
                    done_tasks = [t for t in tasks if t.done()]
                    for task in done_tasks:
                        tasks.remove(task)
        
        # Wait for remaining tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_phase(self, phase_name: str, users: int, duration: int):
        """Run a phase of testing"""
        logger.info(f"Running {phase_name} phase: {users} users for {duration}s")
        
        semaphore = asyncio.Semaphore(users)
        endpoints = self.config.endpoints or ['/api/videos']
        
        tasks = []
        end_time = time.time() + duration
        request_id = 0
        
        while time.time() < end_time:
            endpoint = endpoints[request_id % len(endpoints)]
            user_id = request_id % users
            
            task = self._make_delayed_request(semaphore, endpoint, request_id, user_id, 0)
            tasks.append(task)
            request_id += 1
            
            await asyncio.sleep(0.1)  # Control request rate
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _make_delayed_request(self, semaphore: asyncio.Semaphore, endpoint: str, request_id: int, user_id: int, delay: float):
        """Make a request with optional delay"""
        if delay > 0:
            await asyncio.sleep(delay)
        
        async with semaphore:
            return await self._make_request(endpoint, request_id, user_id)
    
    async def _make_request(self, endpoint: str, request_id: int, user_id: int) -> RequestResult:
        """Make a single HTTP request"""
        url = f"{self.config.base_url}{endpoint}"
        method = (self.config.request_methods or {}).get(endpoint, 'GET')
        payload = (self.config.request_payloads or {}).get(endpoint)
        
        start_time = time.time()
        
        try:
            request_kwargs = {'url': url, 'method': method}
            
            if payload and method in ['POST', 'PUT', 'PATCH']:
                request_kwargs['json'] = payload
            
            async with self.session.request(**request_kwargs) as response:
                response_text = await response.text()
                end_time = time.time()
                
                result = RequestResult(
                    timestamp=start_time,
                    endpoint=endpoint,
                    method=method,
                    status_code=response.status,
                    response_time_ms=(end_time - start_time) * 1000,
                    success=200 <= response.status < 400,
                    response_size_bytes=len(response_text.encode()),
                    user_id=user_id
                )
                
                self.results.append(result)
                return result
                
        except Exception as e:
            end_time = time.time()
            
            result = RequestResult(
                timestamp=start_time,
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time_ms=(end_time - start_time) * 1000,
                success=False,
                error_message=str(e),
                user_id=user_id
            )
            
            self.results.append(result)
            return result
    
    async def _monitor_system(self):
        """Monitor system resources during test"""
        process = psutil.Process()
        
        while True:
            try:
                # System metrics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                network_io = psutil.net_io_counters()
                
                # Process-specific metrics
                process_memory = process.memory_info()
                
                metrics = SystemMetrics(
                    timestamp=time.time(),
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    memory_used_mb=memory.used / (1024 * 1024),
                    disk_io_read_mb=disk_io.read_bytes / (1024 * 1024) if disk_io else 0,
                    disk_io_write_mb=disk_io.write_bytes / (1024 * 1024) if disk_io else 0,
                    network_sent_mb=network_io.bytes_sent / (1024 * 1024) if network_io else 0,
                    network_received_mb=network_io.bytes_recv / (1024 * 1024) if network_io else 0,
                    active_connections=len(psutil.net_connections())
                )
                
                self.system_metrics.append(metrics)
                
                await asyncio.sleep(5)  # Monitor every 5 seconds
                
            except Exception as e:
                logger.warning(f"System monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _generate_results(self, end_time: datetime) -> LoadTestResults:
        """Generate comprehensive test results"""
        duration = (end_time - self.start_time).total_seconds()
        
        # Basic statistics
        total_requests = len(self.results)
        successful_requests = sum(1 for r in self.results if r.success)
        failed_requests = total_requests - successful_requests
        
        success_rate = (successful_requests / max(total_requests, 1)) * 100
        error_rate = (failed_requests / max(total_requests, 1)) * 100
        
        # Response time statistics
        response_times = [r.response_time_ms for r in self.results if r.success]
        
        if response_times:
            min_time = min(response_times)
            max_time = max(response_times)
            avg_time = statistics.mean(response_times)
            median_time = statistics.median(response_times)
            
            # Percentiles
            sorted_times = sorted(response_times)
            p95_time = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
            p99_time = sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
        else:
            min_time = max_time = avg_time = median_time = p95_time = p99_time = 0
        
        # Throughput
        rps = total_requests / max(duration, 1)
        total_bytes = sum(r.response_size_bytes for r in self.results)
        bps = total_bytes / max(duration, 1)
        
        # Error analysis
        error_types = {}
        status_codes = {}
        
        for result in self.results:
            if result.error_message:
                error_type = type(Exception(result.error_message)).__name__
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1
        
        # System metrics analysis
        peak_cpu = max((m.cpu_percent for m in self.system_metrics), default=0)
        peak_memory = max((m.memory_percent for m in self.system_metrics), default=0)
        
        # Performance assessment
        grade, bottlenecks, recommendations = self._assess_performance(
            success_rate, avg_time, rps, peak_cpu, peak_memory
        )
        
        return LoadTestResults(
            config=self.config,
            start_time=self.start_time,
            end_time=end_time,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            success_rate=success_rate,
            error_rate=error_rate,
            min_response_time=min_time,
            max_response_time=max_time,
            avg_response_time=avg_time,
            median_response_time=median_time,
            p95_response_time=p95_time,
            p99_response_time=p99_time,
            requests_per_second=rps,
            bytes_per_second=bps,
            error_types=error_types,
            status_code_distribution=status_codes,
            system_metrics=self.system_metrics,
            peak_cpu_usage=peak_cpu,
            peak_memory_usage=peak_memory,
            performance_grade=grade,
            bottlenecks_identified=bottlenecks,
            recommendations=recommendations
        )
    
    def _assess_performance(self, success_rate: float, avg_response_time: float, rps: float, peak_cpu: float, peak_memory: float) -> tuple:
        """Assess overall performance and identify bottlenecks"""
        
        grade = "A"
        bottlenecks = []
        recommendations = []
        
        # Success rate assessment
        if success_rate < 90:
            grade = "F"
            bottlenecks.append("Low success rate")
            recommendations.append("Investigate error causes and improve error handling")
        elif success_rate < 95:
            grade = "D"
            bottlenecks.append("Moderate success rate")
        elif success_rate < 99:
            grade = "C"
        
        # Response time assessment
        if avg_response_time > 2000:
            grade = min(grade, "F", key=lambda x: ord(x))
            bottlenecks.append("Very slow response times")
            recommendations.append("Optimize database queries and add caching")
        elif avg_response_time > 1000:
            grade = min(grade, "D", key=lambda x: ord(x))
            bottlenecks.append("Slow response times")
            recommendations.append("Review and optimize slow endpoints")
        elif avg_response_time > 500:
            grade = min(grade, "C", key=lambda x: ord(x))
        
        # System resource assessment
        if peak_cpu > 90:
            bottlenecks.append("High CPU usage")
            recommendations.append("Consider scaling horizontally or optimizing CPU-intensive operations")
        elif peak_cpu > 70:
            bottlenecks.append("Moderate CPU usage")
        
        if peak_memory > 90:
            bottlenecks.append("High memory usage")
            recommendations.append("Review memory usage and implement garbage collection optimizations")
        elif peak_memory > 70:
            bottlenecks.append("Moderate memory usage")
        
        # Throughput assessment
        if rps < 10:
            bottlenecks.append("Low throughput")
            recommendations.append("Optimize request processing and consider async improvements")
        
        if not bottlenecks and success_rate > 99 and avg_response_time < 200:
            grade = "A+"
        
        return grade, bottlenecks, recommendations
    
    async def _cleanup(self):
        """Cleanup test resources"""
        if self.session:
            await self.session.close()

class LoadTestReportGenerator:
    """Generate comprehensive load test reports"""
    
    @staticmethod
    def generate_json_report(results: LoadTestResults, filename: str = None) -> str:
        """Generate JSON format report"""
        report_data = {
            'test_config': asdict(results.config),
            'summary': {
                'duration_seconds': results.duration_seconds,
                'total_requests': results.total_requests,
                'success_rate': results.success_rate,
                'avg_response_time_ms': results.avg_response_time,
                'requests_per_second': results.requests_per_second,
                'performance_grade': results.performance_grade
            },
            'response_times': {
                'min': results.min_response_time,
                'max': results.max_response_time,
                'avg': results.avg_response_time,
                'median': results.median_response_time,
                'p95': results.p95_response_time,
                'p99': results.p99_response_time
            },
            'errors': {
                'error_rate': results.error_rate,
                'error_types': results.error_types,
                'status_codes': results.status_code_distribution
            },
            'system_metrics': {
                'peak_cpu_usage': results.peak_cpu_usage,
                'peak_memory_usage': results.peak_memory_usage
            },
            'assessment': {
                'bottlenecks': results.bottlenecks_identified,
                'recommendations': results.recommendations
            }
        }
        
        json_str = json.dumps(report_data, indent=2, default=str)
        
        if filename:
            with open(filename, 'w') as f:
                f.write(json_str)
        
        return json_str
    
    @staticmethod
    def generate_csv_report(results: LoadTestResults, filename: str = None) -> str:
        """Generate CSV format report"""
        csv_data = []
        
        # Header
        csv_data.append([
            'timestamp', 'endpoint', 'method', 'status_code', 
            'response_time_ms', 'success', 'user_id', 'error_message'
        ])
        
        # Request data (sample if too large)
        request_data = results.config.__dict__.get('_raw_results', [])
        if hasattr(results, '_raw_results'):
            sample_size = min(1000, len(results._raw_results))
            for result in results._raw_results[:sample_size]:
                csv_data.append([
                    result.timestamp, result.endpoint, result.method,
                    result.status_code, result.response_time_ms,
                    result.success, result.user_id, result.error_message or ''
                ])
        
        if filename:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(csv_data)
        
        return '\n'.join([','.join(map(str, row)) for row in csv_data])

# Predefined test configurations
class LoadTestPresets:
    """Predefined load test configurations"""
    
    @staticmethod
    def api_smoke_test(base_url: str) -> LoadTestConfig:
        """Basic smoke test configuration"""
        return LoadTestConfig(
            name="API Smoke Test",
            base_url=base_url,
            test_type=LoadTestType.SMOKE,
            concurrent_users=1,
            total_requests=5,
            endpoints=['/api/videos', '/api/artists', '/api/playlists', '/api/settings', '/api/performance'],
            max_response_time_ms=5000,
            min_success_rate=100.0
        )
    
    @staticmethod
    def api_load_test(base_url: str) -> LoadTestConfig:
        """Standard load test configuration"""
        return LoadTestConfig(
            name="API Load Test",
            base_url=base_url,
            test_type=LoadTestType.LOAD,
            concurrent_users=50,
            total_requests=1000,
            ramp_up_time=30,
            endpoints=['/api/videos', '/api/artists', '/api/playlists'],
            max_response_time_ms=1000,
            min_success_rate=95.0
        )
    
    @staticmethod
    def api_stress_test(base_url: str) -> LoadTestConfig:
        """Stress test configuration"""
        return LoadTestConfig(
            name="API Stress Test",
            base_url=base_url,
            test_type=LoadTestType.STRESS,
            concurrent_users=200,
            total_requests=5000,
            duration_seconds=300,
            endpoints=['/api/videos', '/api/artists', '/api/playlists'],
            max_response_time_ms=2000,
            min_success_rate=90.0
        )
    
    @staticmethod
    def api_endurance_test(base_url: str) -> LoadTestConfig:
        """Endurance test configuration"""
        return LoadTestConfig(
            name="API Endurance Test",
            base_url=base_url,
            test_type=LoadTestType.ENDURANCE,
            concurrent_users=20,
            duration_seconds=3600,  # 1 hour
            endpoints=['/api/videos', '/api/artists'],
            max_response_time_ms=1000,
            min_success_rate=98.0
        )

# Test runner utilities
async def run_load_test(config: LoadTestConfig) -> LoadTestResults:
    """Run a single load test"""
    runner = LoadTestRunner(config)
    return await runner.run_test()

async def run_test_suite(base_url: str, output_dir: str = "load_test_results") -> Dict[str, LoadTestResults]:
    """Run complete load test suite"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    results = {}
    
    # Run smoke test first
    smoke_config = LoadTestPresets.api_smoke_test(base_url)
    logger.info("Running smoke test...")
    smoke_results = await run_load_test(smoke_config)
    results['smoke'] = smoke_results
    
    # Only continue if smoke test passes
    if smoke_results.success_rate >= 95:
        
        # Load test
        load_config = LoadTestPresets.api_load_test(base_url)
        logger.info("Running load test...")
        load_results = await run_load_test(load_config)
        results['load'] = load_results
        
        # Stress test (only if load test is successful)
        if load_results.success_rate >= 90:
            stress_config = LoadTestPresets.api_stress_test(base_url)
            logger.info("Running stress test...")
            stress_results = await run_load_test(stress_config)
            results['stress'] = stress_results
    
    # Generate reports
    for test_name, test_results in results.items():
        report_filename = f"{output_dir}/{test_name}_report.json"
        LoadTestReportGenerator.generate_json_report(test_results, report_filename)
        logger.info(f"Report generated: {report_filename}")
    
    return results