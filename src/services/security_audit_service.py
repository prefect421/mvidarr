"""
Security Audit Service - Phase 3 Week 34
Comprehensive security event logging and monitoring
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.database.async_connection import get_async_db_manager
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.security.audit")


class SecurityEventType(Enum):
    """Security event types"""

    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILED = "auth_failed"
    AUTH_LOGOUT = "auth_logout"
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_LOCKED = "account_locked"

    # Authorization events
    ACCESS_DENIED = "access_denied"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_API_ACCESS = "unauthorized_api_access"

    # Security violations
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    COMMAND_INJECTION_ATTEMPT = "command_injection_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    MALICIOUS_REQUEST = "malicious_request"

    # System security events
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SECURITY_POLICY_VIOLATION = "security_policy_violation"
    DATA_BREACH_ATTEMPT = "data_breach_attempt"
    CONFIGURATION_CHANGED = "configuration_changed"

    # File and data events
    SENSITIVE_FILE_ACCESS = "sensitive_file_access"
    DATA_EXPORT = "data_export"
    BULK_OPERATION = "bulk_operation"
    FILE_UPLOAD_VIOLATION = "file_upload_violation"


class SeverityLevel(Enum):
    """Security event severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """Security event data structure"""

    event_type: SecurityEventType
    severity: SeverityLevel
    timestamp: datetime
    source_ip: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    endpoint: Optional[str] = None
    user_agent: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0  # 0-100 risk score
    event_id: Optional[str] = None
    session_id: Optional[str] = None
    fingerprint: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            # Generate unique event ID
            event_data = f"{self.timestamp}{self.event_type.value}{self.source_ip}{self.user_id or 'anonymous'}"
            self.event_id = hashlib.sha256(event_data.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "source_ip": self.source_ip,
            "user_id": self.user_id,
            "username": self.username,
            "endpoint": self.endpoint,
            "user_agent": self.user_agent,
            "details": self.details,
            "risk_score": self.risk_score,
            "session_id": self.session_id,
            "fingerprint": self.fingerprint,
        }


class SecurityAuditConfig:
    """Security audit configuration"""

    def __init__(self):
        # Logging configuration
        self.enable_database_logging = True
        self.enable_file_logging = True
        self.enable_cache_logging = True

        # File logging settings
        self.log_directory = Path("logs/security")
        self.log_file_prefix = "security_audit"
        self.max_log_file_size = 100 * 1024 * 1024  # 100MB
        self.max_log_files = 10

        # Database retention
        self.database_retention_days = 90
        self.critical_event_retention_days = 365

        # Cache settings
        self.cache_events_ttl = 3600  # 1 hour
        self.real_time_alerts_ttl = 300  # 5 minutes

        # Risk scoring
        self.risk_score_thresholds = {
            SeverityLevel.LOW: 25,
            SeverityLevel.MEDIUM: 50,
            SeverityLevel.HIGH: 75,
            SeverityLevel.CRITICAL: 90,
        }

        # Alert configuration
        self.enable_real_time_alerts = True
        self.alert_threshold_score = 70
        self.suspicious_activity_patterns = [
            "multiple_failed_logins",
            "rapid_requests",
            "unusual_endpoints",
            "privilege_escalation_attempts",
            "suspicious_user_agent",
        ]


class RiskScorer:
    """Calculate risk scores for security events"""

    def __init__(self, config: SecurityAuditConfig):
        self.config = config

        # Base risk scores by event type
        self.base_scores = {
            SecurityEventType.AUTH_FAILED: 20,
            SecurityEventType.ACCESS_DENIED: 30,
            SecurityEventType.SQL_INJECTION_ATTEMPT: 90,
            SecurityEventType.XSS_ATTEMPT: 85,
            SecurityEventType.COMMAND_INJECTION_ATTEMPT: 95,
            SecurityEventType.PATH_TRAVERSAL_ATTEMPT: 80,
            SecurityEventType.RATE_LIMIT_EXCEEDED: 40,
            SecurityEventType.MALICIOUS_REQUEST: 75,
            SecurityEventType.DATA_BREACH_ATTEMPT: 100,
            SecurityEventType.PRIVILEGE_ESCALATION: 85,
        }

    def calculate_risk_score(
        self, event: SecurityEvent, context: Dict[str, Any] = None
    ) -> int:
        """Calculate risk score for security event"""
        context = context or {}

        # Start with base score
        base_score = self.base_scores.get(event.event_type, 25)

        # Adjust based on context factors
        score_multiplier = 1.0

        # Frequency factor
        if context.get("recent_similar_events", 0) > 5:
            score_multiplier += 0.3

        # Source IP reputation
        if context.get("known_malicious_ip", False):
            score_multiplier += 0.5

        # User context
        if event.user_id:
            if context.get("user_privilege_level", 0) >= 3:  # Admin/Manager
                score_multiplier += 0.2
        else:
            # Anonymous requests are riskier
            score_multiplier += 0.1

        # Time-based factors
        hour = event.timestamp.hour
        if hour < 6 or hour > 22:  # Off-hours activity
            score_multiplier += 0.1

        # Calculate final score
        final_score = min(100, int(base_score * score_multiplier))

        return final_score


class SecurityAuditService:
    """Comprehensive security audit and monitoring service"""

    def __init__(self, config: Optional[SecurityAuditConfig] = None):
        self.config = config or SecurityAuditConfig()
        self.risk_scorer = RiskScorer(self.config)
        self.cache_manager = MediaCacheManager()

        # Ensure log directory exists
        if self.config.enable_file_logging:
            self.config.log_directory.mkdir(parents=True, exist_ok=True)

        logger.info("🛡️ Security audit service initialized")

    async def log_security_event(
        self,
        event_type: SecurityEventType,
        source_ip: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> SecurityEvent:
        """Log a security event"""

        # Determine severity based on event type
        severity = self._determine_severity(event_type)

        # Create security event
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            timestamp=datetime.utcnow(),
            source_ip=source_ip,
            user_id=user_id,
            username=username,
            endpoint=endpoint,
            user_agent=user_agent,
            details=details or {},
            session_id=session_id,
            fingerprint=fingerprint,
        )

        # Get context for risk scoring
        context = await self._get_event_context(event)

        # Calculate risk score
        event.risk_score = self.risk_scorer.calculate_risk_score(event, context)

        try:
            # Log to multiple destinations
            await self._log_to_cache(event)

            if self.config.enable_database_logging:
                await self._log_to_database(event)

            if self.config.enable_file_logging:
                await self._log_to_file(event)

            # Check for real-time alerts
            if (
                self.config.enable_real_time_alerts
                and event.risk_score >= self.config.alert_threshold_score
            ):
                await self._trigger_security_alert(event)

            logger.info(
                f"🔍 Security event logged: {event.event_type.value} (risk: {event.risk_score})"
            )

        except Exception as e:
            logger.error(f"Failed to log security event: {e}")

        return event

    def _determine_severity(self, event_type: SecurityEventType) -> SeverityLevel:
        """Determine severity level for event type"""
        critical_events = {
            SecurityEventType.SQL_INJECTION_ATTEMPT,
            SecurityEventType.COMMAND_INJECTION_ATTEMPT,
            SecurityEventType.DATA_BREACH_ATTEMPT,
        }

        high_events = {
            SecurityEventType.XSS_ATTEMPT,
            SecurityEventType.PATH_TRAVERSAL_ATTEMPT,
            SecurityEventType.PRIVILEGE_ESCALATION,
            SecurityEventType.UNAUTHORIZED_API_ACCESS,
        }

        medium_events = {
            SecurityEventType.ACCESS_DENIED,
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            SecurityEventType.MALICIOUS_REQUEST,
            SecurityEventType.SUSPICIOUS_ACTIVITY,
        }

        if event_type in critical_events:
            return SeverityLevel.CRITICAL
        elif event_type in high_events:
            return SeverityLevel.HIGH
        elif event_type in medium_events:
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.LOW

    async def _get_event_context(self, event: SecurityEvent) -> Dict[str, Any]:
        """Get context information for risk scoring"""
        context = {}

        try:
            # Count recent similar events from same IP
            recent_key = f"recent_events:{event.source_ip}:{event.event_type.value}"
            recent_count = await self.cache_manager.get(recent_key) or "0"
            context["recent_similar_events"] = int(recent_count)

            # Update recent event count
            await self.cache_manager.set(
                recent_key, str(int(recent_count) + 1), ttl=3600  # 1 hour window
            )

            # Check if IP is in known malicious list (placeholder)
            malicious_key = f"malicious_ip:{event.source_ip}"
            is_malicious = await self.cache_manager.get(malicious_key)
            context["known_malicious_ip"] = bool(is_malicious)

            # Get user privilege level if user_id available
            if event.user_id:
                user_key = f"user_privilege:{event.user_id}"
                privilege_level = await self.cache_manager.get(user_key) or "1"
                context["user_privilege_level"] = int(privilege_level)

        except Exception as e:
            logger.error(f"Error getting event context: {e}")

        return context

    async def _log_to_cache(self, event: SecurityEvent):
        """Log event to cache for real-time access"""
        try:
            # Store individual event
            event_key = f"security_event:{event.event_id}"
            await self.cache_manager.set(
                event_key, json.dumps(event.to_dict()), ttl=self.config.cache_events_ttl
            )

            # Add to recent events list by IP
            recent_key = f"recent_security_events:{event.source_ip}"
            await self.cache_manager.set(
                recent_key,
                json.dumps(
                    {
                        "timestamp": event.timestamp.isoformat(),
                        "event_type": event.event_type.value,
                        "risk_score": event.risk_score,
                        "event_id": event.event_id,
                    }
                ),
                ttl=3600,
            )

        except Exception as e:
            logger.error(f"Error logging to cache: {e}")

    async def _log_to_database(self, event: SecurityEvent):
        """Log event to database for long-term storage"""
        try:
            db_manager = await get_async_db_manager()

            # Insert security event
            query = """
                INSERT INTO security_audit_log (
                    event_id, event_type, severity, timestamp, source_ip,
                    user_id, username, endpoint, user_agent, details,
                    risk_score, session_id, fingerprint
                ) VALUES (
                    :event_id, :event_type, :severity, :timestamp, :source_ip,
                    :user_id, :username, :endpoint, :user_agent, :details,
                    :risk_score, :session_id, :fingerprint
                )
            """

            params = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "timestamp": event.timestamp,
                "source_ip": event.source_ip,
                "user_id": event.user_id,
                "username": event.username,
                "endpoint": event.endpoint,
                "user_agent": event.user_agent[:500] if event.user_agent else None,
                "details": json.dumps(event.details),
                "risk_score": event.risk_score,
                "session_id": event.session_id,
                "fingerprint": event.fingerprint,
            }

            await db_manager.execute_update(query, params)

        except Exception as e:
            logger.error(f"Error logging to database: {e}")

    async def _log_to_file(self, event: SecurityEvent):
        """Log event to file for persistent storage"""
        try:
            log_file = (
                self.config.log_directory
                / f"{self.config.log_file_prefix}_{datetime.now().strftime('%Y%m%d')}.json"
            )

            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(event.to_dict(), f, ensure_ascii=False, separators=(",", ":"))
                f.write("\n")

        except Exception as e:
            logger.error(f"Error logging to file: {e}")

    async def _trigger_security_alert(self, event: SecurityEvent):
        """Trigger real-time security alert"""
        try:
            alert_data = {
                "alert_id": f"alert_{event.event_id}",
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "risk_score": event.risk_score,
                "source_ip": event.source_ip,
                "user_id": event.user_id,
                "username": event.username,
                "endpoint": event.endpoint,
                "details": event.details,
            }

            # Store alert for real-time access
            alert_key = f"security_alert:{event.event_id}"
            await self.cache_manager.set(
                alert_key, json.dumps(alert_data), ttl=self.config.real_time_alerts_ttl
            )

            # Log critical alert
            logger.critical(
                f"🚨 SECURITY ALERT: {event.event_type.value} from {event.source_ip} (risk: {event.risk_score})"
            )

        except Exception as e:
            logger.error(f"Error triggering security alert: {e}")

    async def get_security_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[SecurityEventType]] = None,
        severity_levels: Optional[List[SeverityLevel]] = None,
        source_ip: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve security events with filtering"""
        try:
            db_manager = await get_async_db_manager()

            # Build query with filters
            conditions = []
            params = {}

            if start_time:
                conditions.append("timestamp >= :start_time")
                params["start_time"] = start_time

            if end_time:
                conditions.append("timestamp <= :end_time")
                params["end_time"] = end_time

            if event_types:
                event_type_list = [et.value for et in event_types]
                conditions.append(
                    f"event_type IN ({','.join(['?' for _ in event_type_list])})"
                )
                params.update(
                    {f"event_type_{i}": et for i, et in enumerate(event_type_list)}
                )

            if severity_levels:
                severity_list = [sl.value for sl in severity_levels]
                conditions.append(
                    f"severity IN ({','.join(['?' for _ in severity_list])})"
                )
                params.update(
                    {f"severity_{i}": sl for i, sl in enumerate(severity_list)}
                )

            if source_ip:
                conditions.append("source_ip = :source_ip")
                params["source_ip"] = source_ip

            if user_id:
                conditions.append("user_id = :user_id")
                params["user_id"] = user_id

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT * FROM security_audit_log
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT :limit
            """

            params["limit"] = limit

            events = await db_manager.execute_query(query, params)

            return events

        except Exception as e:
            logger.error(f"Error retrieving security events: {e}")
            return []

    async def get_security_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get security statistics for specified time period"""
        try:
            db_manager = await get_async_db_manager()
            start_time = datetime.utcnow() - timedelta(hours=hours)

            # Get event counts by type
            type_query = """
                SELECT event_type, COUNT(*) as count
                FROM security_audit_log
                WHERE timestamp >= :start_time
                GROUP BY event_type
                ORDER BY count DESC
            """

            type_stats = await db_manager.execute_query(
                type_query, {"start_time": start_time}
            )

            # Get severity distribution
            severity_query = """
                SELECT severity, COUNT(*) as count
                FROM security_audit_log
                WHERE timestamp >= :start_time
                GROUP BY severity
            """

            severity_stats = await db_manager.execute_query(
                severity_query, {"start_time": start_time}
            )

            # Get top source IPs
            ip_query = """
                SELECT source_ip, COUNT(*) as count
                FROM security_audit_log
                WHERE timestamp >= :start_time
                GROUP BY source_ip
                ORDER BY count DESC
                LIMIT 10
            """

            ip_stats = await db_manager.execute_query(
                ip_query, {"start_time": start_time}
            )

            # Get high-risk events
            risk_query = """
                SELECT COUNT(*) as high_risk_count
                FROM security_audit_log
                WHERE timestamp >= :start_time AND risk_score >= 70
            """

            risk_stats = await db_manager.execute_query(
                risk_query, {"start_time": start_time}
            )

            return {
                "period_hours": hours,
                "event_types": type_stats,
                "severity_distribution": severity_stats,
                "top_source_ips": ip_stats,
                "high_risk_events": (
                    risk_stats[0]["high_risk_count"] if risk_stats else 0
                ),
                "generated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting security statistics: {e}")
            return {}


# Global security audit service instance
security_audit_service = SecurityAuditService()


async def log_security_event(
    event_type: SecurityEventType, source_ip: str, **kwargs
) -> SecurityEvent:
    """Convenience function to log security events"""
    return await security_audit_service.log_security_event(
        event_type, source_ip, **kwargs
    )


async def get_security_audit_service() -> SecurityAuditService:
    """Get the global security audit service"""
    return security_audit_service
