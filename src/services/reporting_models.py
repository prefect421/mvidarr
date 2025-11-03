"""
Real-Time Reporting System - Data Models
Enums, dataclasses, and type definitions for the reporting system
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReportType(Enum):
    """Types of reports available"""

    SYSTEM_HEALTH = "system_health"
    USER_ENGAGEMENT = "user_engagement"
    CONTENT_PERFORMANCE = "content_performance"
    TRENDING_ANALYSIS = "trending_analysis"
    COMPREHENSIVE_OVERVIEW = "comprehensive_overview"
    CUSTOM_DASHBOARD = "custom_dashboard"


class ReportFormat(Enum):
    """Report output formats"""

    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"
    DASHBOARD = "dashboard"


class ReportSchedule(Enum):
    """Report scheduling options"""

    REAL_TIME = "real_time"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


@dataclass
class ReportConfiguration:
    """Report configuration settings"""

    report_id: str
    report_type: ReportType
    format: ReportFormat
    schedule: ReportSchedule
    title: str
    description: str
    enabled: bool = True

    # Data filters
    time_window_hours: int = 24
    content_types: List[str] = field(default_factory=list)
    user_segments: List[str] = field(default_factory=list)

    # Output settings
    include_charts: bool = True
    include_insights: bool = True
    include_recommendations: bool = True

    # Delivery settings
    recipients: List[str] = field(default_factory=list)
    webhook_urls: List[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)
    last_generated: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "format": self.format.value,
            "schedule": self.schedule.value,
            "title": self.title,
            "description": self.description,
            "enabled": self.enabled,
            "time_window_hours": self.time_window_hours,
            "content_types": self.content_types,
            "user_segments": self.user_segments,
            "include_charts": self.include_charts,
            "include_insights": self.include_insights,
            "include_recommendations": self.include_recommendations,
            "recipients": self.recipients,
            "webhook_urls": self.webhook_urls,
            "created_at": self.created_at,
            "last_generated": self.last_generated,
        }


@dataclass
class GeneratedReport:
    """Generated report data"""

    report_id: str
    config: ReportConfiguration
    data: Dict[str, Any]
    charts: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    generation_time: float = field(default_factory=time.time)
    processing_time_seconds: float = 0.0
    data_freshness: float = 0.0  # How fresh the underlying data is

    file_path: Optional[str] = None
    dashboard_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "config": self.config.to_dict(),
            "data": self.data,
            "charts": self.charts,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "generation_time": self.generation_time,
            "processing_time_seconds": self.processing_time_seconds,
            "data_freshness": self.data_freshness,
            "file_path": self.file_path,
            "dashboard_url": self.dashboard_url,
        }


@dataclass
class RealtimeMetrics:
    """Real-time system metrics"""

    timestamp: float
    system_metrics: Dict[str, Any]
    user_metrics: Dict[str, Any]
    content_metrics: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    alerts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "system_metrics": self.system_metrics,
            "user_metrics": self.user_metrics,
            "content_metrics": self.content_metrics,
            "performance_metrics": self.performance_metrics,
            "alerts": self.alerts,
        }
