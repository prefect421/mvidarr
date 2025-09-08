"""
Advanced Rate Limiting and DDoS Protection Middleware - Phase 3 Week 34
Intelligent rate limiting with adaptive thresholds and attack detection
"""

import asyncio
import time
import hashlib
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.rate_limiting")


class ThreatLevel(Enum):
    """Threat assessment levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration"""
    name: str
    requests_per_second: int = 10
    requests_per_minute: int = 100
    requests_per_hour: int = 1000
    burst_allowance: int = 20
    block_duration: int = 300  # 5 minutes
    endpoints: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])


@dataclass
class ClientMetrics:
    """Client request metrics and behavior tracking"""
    ip_address: str
    request_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    endpoint_counts: Dict[str, int] = field(default_factory=dict)
    method_counts: Dict[str, int] = field(default_factory=dict)
    user_agents: Set[str] = field(default_factory=set)
    error_count: int = 0
    suspicious_patterns: List[str] = field(default_factory=list)
    threat_level: ThreatLevel = ThreatLevel.LOW
    block_until: Optional[float] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class RateLimitingConfig:
    """Advanced rate limiting configuration"""
    
    def __init__(self):
        # Default rate limit rules
        self.default_rules = [
            RateLimitRule(
                name="api_general",
                requests_per_second=5,
                requests_per_minute=60,
                requests_per_hour=1000,
                endpoints=["/api/"],
                burst_allowance=10
            ),
            RateLimitRule(
                name="api_auth",
                requests_per_second=2,
                requests_per_minute=10,
                requests_per_hour=50,
                endpoints=["/api/auth/", "/api/admin/"],
                burst_allowance=3,
                block_duration=900  # 15 minutes
            ),
            RateLimitRule(
                name="api_sensitive",
                requests_per_second=1,
                requests_per_minute=5,
                requests_per_hour=20,
                endpoints=["/api/settings/", "/api/admin/users/"],
                burst_allowance=2,
                block_duration=1800  # 30 minutes
            ),
            RateLimitRule(
                name="static_files",
                requests_per_second=20,
                requests_per_minute=1200,
                requests_per_hour=10000,
                endpoints=["/static/", "/css/", "/docs/"],
                burst_allowance=50
            ),
        ]
        
        # DDoS detection thresholds
        self.ddos_detection = {
            "rapid_requests_threshold": 50,  # requests per second
            "concurrent_connections_threshold": 100,
            "error_rate_threshold": 0.5,  # 50% error rate
            "suspicious_patterns_threshold": 5,
            "unique_endpoint_threshold": 20,  # too many different endpoints
        }
        
        # Adaptive rate limiting
        self.adaptive_limits = {
            "enable_adaptive": True,
            "load_threshold_high": 0.8,  # CPU/memory usage
            "load_threshold_critical": 0.95,
            "reduction_factor_high": 0.5,
            "reduction_factor_critical": 0.2,
        }
        
        # Whitelist and blacklist
        self.ip_whitelist = {
            "127.0.0.1", "::1",  # localhost
            "192.168.1.0/24",    # local network
        }
        self.ip_blacklist = set()
        
        # Suspicious behavior patterns
        self.suspicious_patterns = [
            r"admin|wp-admin|phpmyadmin|xmlrpc",
            r"\.php$|\.asp$|\.jsp$",
            r"eval\(|base64_decode|shell_exec",
            r"union.*select|drop.*table|insert.*into",
            r"<script|javascript:|vbscript:",
        ]


class AdaptiveRateLimiter:
    """Intelligent rate limiter with adaptive thresholds"""
    
    def __init__(self, config: RateLimitingConfig):
        self.config = config
        self.client_metrics: Dict[str, ClientMetrics] = {}
        self.global_metrics = {
            "total_requests": 0,
            "blocked_requests": 0,
            "active_connections": 0,
            "threat_alerts": deque(maxlen=100),
        }
        self.rules = {rule.name: rule for rule in config.default_rules}
        self._cleanup_task = None
        logger.info("🛡️ Adaptive rate limiter initialized")
    
    def start_background_tasks(self):
        """Start background cleanup and monitoring tasks"""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Background task to clean up old client metrics"""
        while True:
            try:
                current_time = time.time()
                expired_clients = []
                
                for client_ip, metrics in self.client_metrics.items():
                    # Remove clients not seen in last hour
                    if current_time - metrics.last_seen > 3600:
                        expired_clients.append(client_ip)
                    else:
                        # Clean old request times (older than 1 hour)
                        while (metrics.request_times and 
                               current_time - metrics.request_times[0] > 3600):
                            metrics.request_times.popleft()
                
                # Remove expired clients
                for client_ip in expired_clients:
                    del self.client_metrics[client_ip]
                
                logger.debug(f"🧹 Cleaned up {len(expired_clients)} expired client metrics")
                
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
            
            await asyncio.sleep(300)  # Run every 5 minutes
    
    def _get_client_metrics(self, client_ip: str) -> ClientMetrics:
        """Get or create client metrics"""
        if client_ip not in self.client_metrics:
            self.client_metrics[client_ip] = ClientMetrics(ip_address=client_ip)
        return self.client_metrics[client_ip]
    
    def _is_whitelisted(self, client_ip: str) -> bool:
        """Check if client IP is whitelisted"""
        try:
            import ipaddress
            client = ipaddress.ip_address(client_ip)
            
            for whitelist_entry in self.config.ip_whitelist:
                if "/" in whitelist_entry:
                    network = ipaddress.ip_network(whitelist_entry, strict=False)
                    if client in network:
                        return True
                else:
                    if str(client) == whitelist_entry:
                        return True
        except Exception:
            pass
        
        return False
    
    def _is_blacklisted(self, client_ip: str) -> bool:
        """Check if client IP is blacklisted"""
        return client_ip in self.config.ip_blacklist
    
    def _get_applicable_rule(self, path: str, method: str) -> Optional[RateLimitRule]:
        """Get the most specific rate limit rule for the request"""
        applicable_rules = []
        
        for rule in self.rules.values():
            if method in rule.methods:
                for endpoint_pattern in rule.endpoints:
                    if path.startswith(endpoint_pattern):
                        applicable_rules.append((rule, len(endpoint_pattern)))
        
        # Return most specific rule (longest endpoint match)
        if applicable_rules:
            return max(applicable_rules, key=lambda x: x[1])[0]
        
        return None
    
    async def _assess_threat_level(self, request: Request, client_metrics: ClientMetrics) -> ThreatLevel:
        """Assess threat level based on client behavior"""
        current_time = time.time()
        threat_score = 0
        
        # Calculate request rate (requests per second in last minute)
        recent_requests = [t for t in client_metrics.request_times 
                          if current_time - t <= 60]
        if len(recent_requests) > 0:
            requests_per_second = len(recent_requests) / min(60, current_time - recent_requests[0])
            if requests_per_second > self.config.ddos_detection["rapid_requests_threshold"]:
                threat_score += 40
        
        # Check error rate
        if client_metrics.error_count > 10:
            total_requests = len(client_metrics.request_times)
            error_rate = client_metrics.error_count / max(total_requests, 1)
            if error_rate > self.config.ddos_detection["error_rate_threshold"]:
                threat_score += 30
        
        # Check endpoint diversity (possible scanning)
        if len(client_metrics.endpoint_counts) > self.config.ddos_detection["unique_endpoint_threshold"]:
            threat_score += 25
        
        # Check suspicious patterns
        if len(client_metrics.suspicious_patterns) >= self.config.ddos_detection["suspicious_patterns_threshold"]:
            threat_score += 35
        
        # Check user agent diversity (possible bot behavior)
        if len(client_metrics.user_agents) > 5:
            threat_score += 20
        
        # Determine threat level
        if threat_score >= 80:
            return ThreatLevel.CRITICAL
        elif threat_score >= 60:
            return ThreatLevel.HIGH
        elif threat_score >= 30:
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
    
    async def _check_suspicious_patterns(self, request: Request, client_metrics: ClientMetrics):
        """Check for suspicious request patterns"""
        import re
        
        path = request.url.path
        query_string = str(request.url.query)
        user_agent = request.headers.get("user-agent", "")
        
        # Check path and query for suspicious patterns
        for pattern in self.config.suspicious_patterns:
            if re.search(pattern, path + query_string, re.IGNORECASE):
                if pattern not in client_metrics.suspicious_patterns:
                    client_metrics.suspicious_patterns.append(pattern)
                    logger.warning(f"🚨 Suspicious pattern detected: {pattern} from {client_metrics.ip_address}")
        
        # Track user agent
        if user_agent:
            client_metrics.user_agents.add(user_agent[:100])  # Limit length
    
    async def check_rate_limit(self, request: Request) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Check if request should be rate limited
        Returns: (is_allowed, reason, retry_after_seconds)
        """
        client_ip = request.client.host
        path = request.url.path
        method = request.method
        current_time = time.time()
        
        # Increment global request counter
        self.global_metrics["total_requests"] += 1
        
        # Check whitelist
        if self._is_whitelisted(client_ip):
            return True, None, None
        
        # Check blacklist
        if self._is_blacklisted(client_ip):
            self.global_metrics["blocked_requests"] += 1
            return False, "IP address blacklisted", 3600
        
        # Get client metrics
        client_metrics = self._get_client_metrics(client_ip)
        client_metrics.last_seen = current_time
        
        # Check if client is currently blocked
        if client_metrics.block_until and current_time < client_metrics.block_until:
            self.global_metrics["blocked_requests"] += 1
            remaining_time = int(client_metrics.block_until - current_time)
            return False, f"Temporarily blocked due to rate limit violation", remaining_time
        
        # Clear block if expired
        if client_metrics.block_until and current_time >= client_metrics.block_until:
            client_metrics.block_until = None
            client_metrics.threat_level = ThreatLevel.LOW
        
        # Track request
        client_metrics.request_times.append(current_time)
        client_metrics.endpoint_counts[path] = client_metrics.endpoint_counts.get(path, 0) + 1
        client_metrics.method_counts[method] = client_metrics.method_counts.get(method, 0) + 1
        
        # Check for suspicious patterns
        await self._check_suspicious_patterns(request, client_metrics)
        
        # Assess threat level
        client_metrics.threat_level = await self._assess_threat_level(request, client_metrics)
        
        # Get applicable rate limit rule
        rule = self._get_applicable_rule(path, method)
        if not rule:
            return True, None, None
        
        # Apply adaptive rate limiting based on threat level
        rate_multiplier = {
            ThreatLevel.LOW: 1.0,
            ThreatLevel.MEDIUM: 0.7,
            ThreatLevel.HIGH: 0.4,
            ThreatLevel.CRITICAL: 0.1,
        }[client_metrics.threat_level]
        
        # Check rate limits
        recent_times = client_metrics.request_times
        
        # Requests per second check
        second_requests = [t for t in recent_times if current_time - t <= 1]
        max_per_second = int(rule.requests_per_second * rate_multiplier)
        if len(second_requests) > max_per_second:
            self._block_client(client_metrics, rule.block_duration)
            self.global_metrics["blocked_requests"] += 1
            return False, f"Rate limit exceeded: {len(second_requests)} requests per second", rule.block_duration
        
        # Requests per minute check
        minute_requests = [t for t in recent_times if current_time - t <= 60]
        max_per_minute = int(rule.requests_per_minute * rate_multiplier)
        if len(minute_requests) > max_per_minute:
            self._block_client(client_metrics, rule.block_duration)
            self.global_metrics["blocked_requests"] += 1
            return False, f"Rate limit exceeded: {len(minute_requests)} requests per minute", rule.block_duration
        
        # Requests per hour check
        hour_requests = [t for t in recent_times if current_time - t <= 3600]
        max_per_hour = int(rule.requests_per_hour * rate_multiplier)
        if len(hour_requests) > max_per_hour:
            self._block_client(client_metrics, rule.block_duration * 2)
            self.global_metrics["blocked_requests"] += 1
            return False, f"Rate limit exceeded: {len(hour_requests)} requests per hour", rule.block_duration * 2
        
        # Log threat escalation
        if client_metrics.threat_level != ThreatLevel.LOW:
            logger.warning(f"🚨 Elevated threat level {client_metrics.threat_level.value} for {client_ip}")
        
        return True, None, None
    
    def _block_client(self, client_metrics: ClientMetrics, duration: int):
        """Block client for specified duration"""
        client_metrics.block_until = time.time() + duration
        client_metrics.threat_level = ThreatLevel.HIGH
        
        # Add to threat alerts
        alert = {
            "timestamp": time.time(),
            "ip": client_metrics.ip_address,
            "action": "blocked",
            "duration": duration,
            "threat_level": client_metrics.threat_level.value,
            "reason": "rate_limit_violation"
        }
        self.global_metrics["threat_alerts"].append(alert)
        
        logger.warning(f"🚫 Blocked {client_metrics.ip_address} for {duration} seconds due to rate limit violation")
    
    async def record_error(self, client_ip: str):
        """Record error for client metrics"""
        client_metrics = self._get_client_metrics(client_ip)
        client_metrics.error_count += 1
    
    def get_statistics(self) -> Dict:
        """Get rate limiting statistics"""
        current_time = time.time()
        active_blocks = sum(1 for metrics in self.client_metrics.values() 
                           if metrics.block_until and current_time < metrics.block_until)
        
        threat_distribution = {level.value: 0 for level in ThreatLevel}
        for metrics in self.client_metrics.values():
            threat_distribution[metrics.threat_level.value] += 1
        
        return {
            "total_requests": self.global_metrics["total_requests"],
            "blocked_requests": self.global_metrics["blocked_requests"],
            "active_clients": len(self.client_metrics),
            "active_blocks": active_blocks,
            "threat_distribution": threat_distribution,
            "recent_alerts": list(self.global_metrics["threat_alerts"])[-10:],
            "block_rate": (self.global_metrics["blocked_requests"] / 
                          max(self.global_metrics["total_requests"], 1)) * 100
        }


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting and DDoS protection middleware"""
    
    def __init__(self, app, config: Optional[RateLimitingConfig] = None):
        super().__init__(app)
        self.config = config or RateLimitingConfig()
        self.rate_limiter = AdaptiveRateLimiter(self.config)
        self.rate_limiter.start_background_tasks()
        logger.info("🛡️ Rate limiting middleware initialized with adaptive DDoS protection")
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting and DDoS protection"""
        start_time = time.time()
        client_ip = request.client.host
        
        try:
            # Check rate limits
            is_allowed, reason, retry_after = await self.rate_limiter.check_rate_limit(request)
            
            if not is_allowed:
                # Create rate limit response
                headers = {"X-RateLimit-Limit": "exceeded"}
                if retry_after:
                    headers["Retry-After"] = str(retry_after)
                
                logger.info(f"🚫 Rate limited {client_ip}: {reason}")
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": reason,
                        "retry_after": retry_after,
                        "blocked": True
                    },
                    headers=headers
                )
            
            # Process request
            response = await call_next(request)
            
            # Record error if response indicates error
            if response.status_code >= 400:
                await self.rate_limiter.record_error(client_ip)
            
            # Add rate limiting headers
            response.headers["X-RateLimit-Remaining"] = "ok"
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + 3600))
            
            processing_time = time.time() - start_time
            logger.debug(f"🛡️ Rate limit check passed for {client_ip} in {processing_time:.3f}s")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Rate limiting middleware error: {e}")
            # Allow request to proceed on middleware error
            return await call_next(request)