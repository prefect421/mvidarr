"""
Advanced Dashboard System - Phase 3 Week 27
Enhanced system performance analytics dashboard with advanced visualization and monitoring
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics

from src.services.analytics_service import get_analytics_service
from src.services.user_behavior_analytics import get_user_behavior_analytics
from src.services.content_analytics_engine import get_content_analytics_engine
from src.services.performance_monitor import get_performance_monitor
from src.services.visualization_service import VisualizationService, ChartConfig, ChartType, TimeRange
from src.services.media_cache_manager import get_media_cache_manager, CacheType
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.advanced_dashboard")


class DashboardType(Enum):
    """Types of dashboards available"""
    SYSTEM_OVERVIEW = "system_overview"
    PERFORMANCE_MONITORING = "performance_monitoring"
    USER_ANALYTICS = "user_analytics"
    CONTENT_INSIGHTS = "content_insights"
    REAL_TIME_OPERATIONS = "real_time_operations"
    EXECUTIVE_SUMMARY = "executive_summary"


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class DashboardWidget:
    """Individual dashboard widget configuration"""
    widget_id: str
    widget_type: str  # chart, metric, alert, table, etc.
    title: str
    data_source: str
    refresh_interval: int  # seconds
    position: Dict[str, int]  # x, y, width, height
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'widget_id': self.widget_id,
            'widget_type': self.widget_type,
            'title': self.title,
            'data_source': self.data_source,
            'refresh_interval': self.refresh_interval,
            'position': self.position,
            'config': self.config,
            'enabled': self.enabled
        }


@dataclass
class DashboardConfiguration:
    """Complete dashboard configuration"""
    dashboard_id: str
    dashboard_type: DashboardType
    title: str
    description: str
    widgets: List[DashboardWidget] = field(default_factory=list)
    layout: str = "grid"  # grid, flex, custom
    theme: str = "dark"  # dark, light
    auto_refresh: bool = True
    refresh_interval: int = 30  # seconds
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'dashboard_id': self.dashboard_id,
            'dashboard_type': self.dashboard_type.value,
            'title': self.title,
            'description': self.description,
            'widgets': [w.to_dict() for w in self.widgets],
            'layout': self.layout,
            'theme': self.theme,
            'auto_refresh': self.auto_refresh,
            'refresh_interval': self.refresh_interval,
            'created_at': self.created_at
        }


@dataclass
class SystemAlert:
    """System alert information"""
    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    source: str  # Which service/component
    timestamp: float
    acknowledged: bool = False
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_id': self.alert_id,
            'severity': self.severity.value,
            'title': self.title,
            'message': self.message,
            'source': self.source,
            'timestamp': self.timestamp,
            'acknowledged': self.acknowledged,
            'resolved': self.resolved,
            'metadata': self.metadata
        }


class AdvancedDashboardSystem:
    """Advanced dashboard system with comprehensive analytics visualization"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize advanced dashboard system"""
        self.config = config or {
            'enable_real_time_updates': True,
            'update_interval_seconds': 10,
            'max_alerts_history': 1000,
            'dashboard_cache_ttl': 300,  # 5 minutes
            'enable_predictive_analytics': True,
            'performance_thresholds': {
                'cpu_warning': 80,
                'cpu_critical': 95,
                'memory_warning': 85,
                'memory_critical': 95,
                'response_time_warning': 1000,  # ms
                'response_time_critical': 3000
            }
        }
        
        # Service initialization
        self.visualization_service = VisualizationService()
        
        # Dashboard management
        self.dashboards: Dict[str, DashboardConfiguration] = {}
        self.active_alerts: Dict[str, SystemAlert] = {}
        self.alerts_history = deque(maxlen=self.config['max_alerts_history'])
        
        # Real-time data streams
        self.metrics_streams: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.dashboard_subscribers: Dict[str, List[Any]] = defaultdict(list)
        
        # Processing state
        self.system_active = True
        self.last_update_time = time.time()
        
        # Performance tracking
        self.stats = {
            'dashboards_created': 0,
            'widgets_rendered': 0,
            'alerts_generated': 0,
            'real_time_updates': 0,
            'total_processing_time': 0.0
        }
        
        # Initialize default dashboards
        asyncio.create_task(self._initialize_default_dashboards())
        
        # Start background services
        if self.config['enable_real_time_updates']:
            self._start_background_services()
        
        logger.info("📊 Advanced dashboard system initialized")
    
    def _start_background_services(self):
        """Start background dashboard services"""
        asyncio.create_task(self._real_time_update_loop())
        asyncio.create_task(self._alert_monitoring_loop())
        asyncio.create_task(self._predictive_analytics_loop())
    
    async def _real_time_update_loop(self):
        """Background loop for real-time dashboard updates"""
        while self.system_active:
            try:
                await asyncio.sleep(self.config['update_interval_seconds'])
                await self._collect_dashboard_metrics()
                await self._update_dashboard_streams()
            except Exception as e:
                logger.error(f"Real-time dashboard update error: {e}")
    
    async def _alert_monitoring_loop(self):
        """Background loop for alert monitoring"""
        while self.system_active:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._check_system_alerts()
            except Exception as e:
                logger.error(f"Alert monitoring error: {e}")
    
    async def _predictive_analytics_loop(self):
        """Background loop for predictive analytics"""
        if not self.config['enable_predictive_analytics']:
            return
        
        while self.system_active:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._run_predictive_analytics()
            except Exception as e:
                logger.error(f"Predictive analytics error: {e}")
    
    async def _initialize_default_dashboards(self):
        """Initialize default dashboard configurations"""
        try:
            # System Overview Dashboard
            system_overview = await self._create_system_overview_dashboard()
            await self.create_dashboard(system_overview)
            
            # Performance Monitoring Dashboard
            performance_dashboard = await self._create_performance_dashboard()
            await self.create_dashboard(performance_dashboard)
            
            # User Analytics Dashboard
            user_analytics_dashboard = await self._create_user_analytics_dashboard()
            await self.create_dashboard(user_analytics_dashboard)
            
            # Content Insights Dashboard
            content_dashboard = await self._create_content_insights_dashboard()
            await self.create_dashboard(content_dashboard)
            
            logger.info("📊 Default dashboards initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize default dashboards: {e}")
    
    async def _create_system_overview_dashboard(self) -> DashboardConfiguration:
        """Create system overview dashboard configuration"""
        widgets = [
            DashboardWidget(
                widget_id="system_health_gauge",
                widget_type="gauge",
                title="System Health Score",
                data_source="system_health",
                refresh_interval=30,
                position={"x": 0, "y": 0, "width": 6, "height": 4},
                config={"min": 0, "max": 100, "thresholds": [75, 90]}
            ),
            DashboardWidget(
                widget_id="active_users_metric",
                widget_type="metric",
                title="Active Users (24h)",
                data_source="user_analytics",
                refresh_interval=60,
                position={"x": 6, "y": 0, "width": 6, "height": 2},
                config={"format": "number"}
            ),
            DashboardWidget(
                widget_id="response_time_chart",
                widget_type="line_chart",
                title="Response Time Trend",
                data_source="performance_metrics",
                refresh_interval=30,
                position={"x": 0, "y": 4, "width": 12, "height": 4},
                config={"metric": "response_time", "time_window": "1h"}
            ),
            DashboardWidget(
                widget_id="active_alerts",
                widget_type="alert_list",
                title="Active System Alerts",
                data_source="system_alerts",
                refresh_interval=15,
                position={"x": 6, "y": 2, "width": 6, "height": 2},
                config={"max_items": 5}
            )
        ]
        
        return DashboardConfiguration(
            dashboard_id="system_overview",
            dashboard_type=DashboardType.SYSTEM_OVERVIEW,
            title="System Overview",
            description="Comprehensive system health and performance overview",
            widgets=widgets,
            refresh_interval=30
        )
    
    async def _create_performance_dashboard(self) -> DashboardConfiguration:
        """Create performance monitoring dashboard"""
        widgets = [
            DashboardWidget(
                widget_id="cpu_usage_chart",
                widget_type="area_chart",
                title="CPU Usage",
                data_source="system_metrics",
                refresh_interval=15,
                position={"x": 0, "y": 0, "width": 6, "height": 4},
                config={"metric": "cpu_percent", "time_window": "2h"}
            ),
            DashboardWidget(
                widget_id="memory_usage_chart",
                widget_type="area_chart",
                title="Memory Usage",
                data_source="system_metrics",
                refresh_interval=15,
                position={"x": 6, "y": 0, "width": 6, "height": 4},
                config={"metric": "memory_percent", "time_window": "2h"}
            ),
            DashboardWidget(
                widget_id="disk_io_chart",
                widget_type="line_chart",
                title="Disk I/O",
                data_source="system_metrics",
                refresh_interval=30,
                position={"x": 0, "y": 4, "width": 6, "height": 4},
                config={"metric": "disk_io", "time_window": "1h"}
            ),
            DashboardWidget(
                widget_id="network_io_chart",
                widget_type="line_chart",
                title="Network I/O",
                data_source="system_metrics",
                refresh_interval=30,
                position={"x": 6, "y": 4, "width": 6, "height": 4},
                config={"metric": "network_io", "time_window": "1h"}
            ),
            DashboardWidget(
                widget_id="performance_summary",
                widget_type="metrics_grid",
                title="Performance Summary",
                data_source="performance_summary",
                refresh_interval=60,
                position={"x": 0, "y": 8, "width": 12, "height": 2},
                config={"metrics": ["avg_response_time", "requests_per_second", "error_rate"]}
            )
        ]
        
        return DashboardConfiguration(
            dashboard_id="performance_monitoring",
            dashboard_type=DashboardType.PERFORMANCE_MONITORING,
            title="Performance Monitoring",
            description="Detailed system performance metrics and monitoring",
            widgets=widgets,
            refresh_interval=15
        )
    
    async def _create_user_analytics_dashboard(self) -> DashboardConfiguration:
        """Create user analytics dashboard"""
        widgets = [
            DashboardWidget(
                widget_id="user_activity_chart",
                widget_type="line_chart",
                title="User Activity Timeline",
                data_source="user_behavior",
                refresh_interval=60,
                position={"x": 0, "y": 0, "width": 8, "height": 4},
                config={"metric": "active_users", "time_window": "24h"}
            ),
            DashboardWidget(
                widget_id="engagement_score",
                widget_type="gauge",
                title="Avg Engagement Score",
                data_source="user_engagement",
                refresh_interval=120,
                position={"x": 8, "y": 0, "width": 4, "height": 4},
                config={"min": 0, "max": 100}
            ),
            DashboardWidget(
                widget_id="popular_content_list",
                widget_type="table",
                title="Popular Content",
                data_source="popular_content",
                refresh_interval=300,
                position={"x": 0, "y": 4, "width": 6, "height": 4},
                config={"columns": ["title", "interactions", "unique_users"], "max_rows": 10}
            ),
            DashboardWidget(
                widget_id="user_segments_pie",
                widget_type="pie_chart",
                title="User Engagement Segments",
                data_source="user_segments",
                refresh_interval=300,
                position={"x": 6, "y": 4, "width": 6, "height": 4},
                config={"segments": ["high_engagement", "medium_engagement", "low_engagement"]}
            )
        ]
        
        return DashboardConfiguration(
            dashboard_id="user_analytics",
            dashboard_type=DashboardType.USER_ANALYTICS,
            title="User Analytics",
            description="User behavior and engagement analytics",
            widgets=widgets,
            refresh_interval=60
        )
    
    async def _create_content_insights_dashboard(self) -> DashboardConfiguration:
        """Create content insights dashboard"""
        widgets = [
            DashboardWidget(
                widget_id="trending_content_chart",
                widget_type="bar_chart",
                title="Trending Content",
                data_source="trending_content",
                refresh_interval=180,
                position={"x": 0, "y": 0, "width": 8, "height": 4},
                config={"metric": "trending_score", "limit": 10}
            ),
            DashboardWidget(
                widget_id="content_performance",
                widget_type="metrics_grid",
                title="Content Performance",
                data_source="content_metrics",
                refresh_interval=300,
                position={"x": 8, "y": 0, "width": 4, "height": 4},
                config={"metrics": ["total_views", "avg_quality_score", "trending_items"]}
            ),
            DashboardWidget(
                widget_id="quality_distribution",
                widget_type="histogram",
                title="Quality Score Distribution",
                data_source="content_quality",
                refresh_interval=600,
                position={"x": 0, "y": 4, "width": 6, "height": 4},
                config={"bins": 10, "range": [0, 100]}
            ),
            DashboardWidget(
                widget_id="content_velocity_chart",
                widget_type="scatter_plot",
                title="Content Velocity vs Quality",
                data_source="content_analysis",
                refresh_interval=300,
                position={"x": 6, "y": 4, "width": 6, "height": 4},
                config={"x_axis": "quality_score", "y_axis": "trending_velocity"}
            )
        ]
        
        return DashboardConfiguration(
            dashboard_id="content_insights",
            dashboard_type=DashboardType.CONTENT_INSIGHTS,
            title="Content Insights",
            description="Content performance and trending analysis",
            widgets=widgets,
            refresh_interval=120
        )
    
    async def create_dashboard(self, config: DashboardConfiguration) -> str:
        """Create a new dashboard configuration"""
        try:
            self.dashboards[config.dashboard_id] = config
            
            # Cache dashboard configuration
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.DASHBOARD_CONFIG,
                f"dashboard_{config.dashboard_id}",
                config.to_dict(),
                ttl=self.config['dashboard_cache_ttl']
            )
            
            self.stats['dashboards_created'] += 1
            logger.info(f"📊 Created dashboard: {config.title}")
            
            return config.dashboard_id
            
        except Exception as e:
            logger.error(f"Failed to create dashboard: {e}")
            return ""
    
    async def _collect_dashboard_metrics(self):
        """Collect metrics for dashboard updates"""
        try:
            start_time = time.time()
            
            # Collect from all analytics services
            analytics_service = await get_analytics_service()
            user_analytics = await get_user_behavior_analytics()
            content_analytics = await get_content_analytics_engine()
            performance_monitor = await get_performance_monitor()
            
            # Get current metrics
            current_time = time.time()
            
            # System metrics
            system_health = await performance_monitor.get_system_health_summary()
            self.metrics_streams['system_health'].append({
                'timestamp': current_time,
                'value': system_health.get('health_score', 0)
            })
            
            current_metrics = performance_monitor.get_current_metrics()
            if 'cpu_usage' in current_metrics:
                self.metrics_streams['cpu_usage'].append({
                    'timestamp': current_time,
                    'value': current_metrics['cpu_usage']['value']
                })
            
            if 'memory_usage' in current_metrics:
                self.metrics_streams['memory_usage'].append({
                    'timestamp': current_time,
                    'value': current_metrics['memory_usage']['value']
                })
            
            # User metrics
            user_summary = await user_analytics.get_analytics_summary()
            self.metrics_streams['active_users'].append({
                'timestamp': current_time,
                'value': user_summary.get('active_users', {}).get('last_24_hours', 0)
            })
            
            # Content metrics
            trending_content = await content_analytics.get_trending_content(limit=10)
            self.metrics_streams['trending_count'].append({
                'timestamp': current_time,
                'value': len(trending_content)
            })
            
            # Update processing stats
            processing_time = time.time() - start_time
            self.stats['real_time_updates'] += 1
            self.stats['total_processing_time'] += processing_time
            self.last_update_time = current_time
            
        except Exception as e:
            logger.error(f"Dashboard metrics collection failed: {e}")
    
    async def _update_dashboard_streams(self):
        """Update real-time dashboard data streams"""
        try:
            # Notify all subscribers with updated data
            for dashboard_id, subscribers in self.dashboard_subscribers.items():
                if subscribers:
                    dashboard_data = await self.get_dashboard_data(dashboard_id)
                    # In a real implementation, this would send data to WebSocket connections
                    logger.debug(f"Updated {len(subscribers)} subscribers for dashboard {dashboard_id}")
            
        except Exception as e:
            logger.error(f"Dashboard streams update failed: {e}")
    
    async def _check_system_alerts(self):
        """Check for system alerts and generate notifications"""
        try:
            performance_monitor = await get_performance_monitor()
            active_alerts = performance_monitor.get_active_alerts()
            
            # Convert performance alerts to system alerts
            for alert_data in active_alerts:
                alert_id = f"perf_{alert_data['alert_id']}"
                
                if alert_id not in self.active_alerts:
                    # Determine severity
                    severity = AlertSeverity.WARNING
                    if 'critical' in alert_data['alert_level']:
                        severity = AlertSeverity.CRITICAL
                    elif 'emergency' in alert_data['alert_level']:
                        severity = AlertSeverity.EMERGENCY
                    
                    # Create system alert
                    system_alert = SystemAlert(
                        alert_id=alert_id,
                        severity=severity,
                        title=f"Performance Alert: {alert_data['metric_type']}",
                        message=alert_data['message'],
                        source="performance_monitor",
                        timestamp=alert_data['timestamp'],
                        metadata=alert_data
                    )
                    
                    self.active_alerts[alert_id] = system_alert
                    self.alerts_history.append(system_alert)
                    self.stats['alerts_generated'] += 1
                    
                    logger.warning(f"🚨 System alert generated: {system_alert.title}")
            
            # Check for custom threshold alerts
            await self._check_custom_thresholds()
            
        except Exception as e:
            logger.error(f"System alerts check failed: {e}")
    
    async def _check_custom_thresholds(self):
        """Check custom threshold alerts"""
        try:
            thresholds = self.config['performance_thresholds']
            
            # Check recent metrics against thresholds
            for metric_name, metric_data in self.metrics_streams.items():
                if not metric_data:
                    continue
                
                latest_value = metric_data[-1]['value']
                alert_generated = False
                
                # CPU thresholds
                if metric_name == 'cpu_usage':
                    if latest_value >= thresholds['cpu_critical']:
                        await self._generate_threshold_alert(
                            "cpu_critical", AlertSeverity.CRITICAL,
                            f"CPU usage critical: {latest_value:.1f}%", latest_value
                        )
                        alert_generated = True
                    elif latest_value >= thresholds['cpu_warning']:
                        await self._generate_threshold_alert(
                            "cpu_warning", AlertSeverity.WARNING,
                            f"CPU usage high: {latest_value:.1f}%", latest_value
                        )
                        alert_generated = True
                
                # Memory thresholds
                elif metric_name == 'memory_usage':
                    if latest_value >= thresholds['memory_critical']:
                        await self._generate_threshold_alert(
                            "memory_critical", AlertSeverity.CRITICAL,
                            f"Memory usage critical: {latest_value:.1f}%", latest_value
                        )
                        alert_generated = True
                    elif latest_value >= thresholds['memory_warning']:
                        await self._generate_threshold_alert(
                            "memory_warning", AlertSeverity.WARNING,
                            f"Memory usage high: {latest_value:.1f}%", latest_value
                        )
                        alert_generated = True
                
                # Resolve alerts if values return to normal
                if not alert_generated:
                    await self._resolve_threshold_alerts(metric_name)
            
        except Exception as e:
            logger.error(f"Custom threshold check failed: {e}")
    
    async def _generate_threshold_alert(self, alert_type: str, severity: AlertSeverity, message: str, value: float):
        """Generate a threshold-based alert"""
        alert_id = f"threshold_{alert_type}"
        
        if alert_id not in self.active_alerts:
            alert = SystemAlert(
                alert_id=alert_id,
                severity=severity,
                title=f"Threshold Alert: {alert_type.replace('_', ' ').title()}",
                message=message,
                source="dashboard_system",
                timestamp=time.time(),
                metadata={"threshold_type": alert_type, "current_value": value}
            )
            
            self.active_alerts[alert_id] = alert
            self.alerts_history.append(alert)
            self.stats['alerts_generated'] += 1
    
    async def _resolve_threshold_alerts(self, metric_name: str):
        """Resolve threshold alerts for a metric"""
        alerts_to_resolve = []
        
        for alert_id, alert in self.active_alerts.items():
            if alert.source == "dashboard_system" and metric_name in alert_id:
                alerts_to_resolve.append(alert_id)
        
        for alert_id in alerts_to_resolve:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            del self.active_alerts[alert_id]
            logger.info(f"✅ Resolved threshold alert: {alert.title}")
    
    async def _run_predictive_analytics(self):
        """Run predictive analytics on dashboard metrics"""
        try:
            if not self.config['enable_predictive_analytics']:
                return
            
            # Simple trend analysis for key metrics
            for metric_name, metric_data in self.metrics_streams.items():
                if len(metric_data) < 10:  # Need minimum data points
                    continue
                
                # Calculate trend
                recent_values = [point['value'] for point in list(metric_data)[-10:]]
                trend = self._calculate_trend(recent_values)
                
                # Generate predictive alerts
                if metric_name == 'cpu_usage' and trend > 5:  # Rising trend
                    current_value = recent_values[-1]
                    predicted_value = current_value + (trend * 3)  # 3 data points ahead
                    
                    if predicted_value > 90:
                        await self._generate_predictive_alert(
                            "cpu_trend", "CPU usage trending upward",
                            f"Current: {current_value:.1f}%, Predicted: {predicted_value:.1f}%"
                        )
                
                elif metric_name == 'memory_usage' and trend > 3:
                    current_value = recent_values[-1]
                    predicted_value = current_value + (trend * 3)
                    
                    if predicted_value > 90:
                        await self._generate_predictive_alert(
                            "memory_trend", "Memory usage trending upward",
                            f"Current: {current_value:.1f}%, Predicted: {predicted_value:.1f}%"
                        )
            
        except Exception as e:
            logger.error(f"Predictive analytics failed: {e}")
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate linear trend from values"""
        try:
            if len(values) < 2:
                return 0.0
            
            n = len(values)
            x = list(range(n))
            
            # Simple linear regression slope
            x_mean = sum(x) / n
            y_mean = sum(values) / n
            
            numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            if denominator == 0:
                return 0.0
            
            return numerator / denominator
            
        except Exception:
            return 0.0
    
    async def _generate_predictive_alert(self, alert_type: str, title: str, message: str):
        """Generate a predictive alert"""
        alert_id = f"predictive_{alert_type}"
        
        if alert_id not in self.active_alerts:
            alert = SystemAlert(
                alert_id=alert_id,
                severity=AlertSeverity.INFO,
                title=f"Predictive Alert: {title}",
                message=message,
                source="predictive_analytics",
                timestamp=time.time(),
                metadata={"alert_type": "predictive", "prediction_type": alert_type}
            )
            
            self.active_alerts[alert_id] = alert
            self.alerts_history.append(alert)
            logger.info(f"🔮 Predictive alert: {title}")
    
    async def get_dashboard_data(self, dashboard_id: str) -> Dict[str, Any]:
        """Get complete dashboard data including all widget data"""
        try:
            dashboard = self.dashboards.get(dashboard_id)
            if not dashboard:
                return {'error': 'Dashboard not found'}
            
            dashboard_data = {
                'dashboard_id': dashboard_id,
                'config': dashboard.to_dict(),
                'last_updated': self.last_update_time,
                'widgets_data': {},
                'alerts': [alert.to_dict() for alert in self.active_alerts.values()],
                'system_status': {
                    'healthy_widgets': 0,
                    'total_widgets': len(dashboard.widgets)
                }
            }
            
            # Collect data for each widget
            healthy_widgets = 0
            for widget in dashboard.widgets:
                try:
                    widget_data = await self._get_widget_data(widget)
                    dashboard_data['widgets_data'][widget.widget_id] = widget_data
                    if widget_data and 'error' not in widget_data:
                        healthy_widgets += 1
                except Exception as e:
                    dashboard_data['widgets_data'][widget.widget_id] = {'error': str(e)}
            
            dashboard_data['system_status']['healthy_widgets'] = healthy_widgets
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {'error': str(e)}
    
    async def _get_widget_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get data for a specific widget"""
        try:
            widget_data = {
                'widget_id': widget.widget_id,
                'last_updated': time.time(),
                'data': None,
                'chart_config': None
            }
            
            # Get data based on widget data source
            if widget.data_source == 'system_health':
                performance_monitor = await get_performance_monitor()
                health_summary = await performance_monitor.get_system_health_summary()
                widget_data['data'] = health_summary.get('health_score', 0)
                
            elif widget.data_source == 'user_analytics':
                user_analytics = await get_user_behavior_analytics()
                summary = await user_analytics.get_analytics_summary()
                widget_data['data'] = summary.get('active_users', {}).get('last_24_hours', 0)
                
            elif widget.data_source == 'performance_metrics':
                # Get time series data for charts
                metric_name = widget.config.get('metric', 'response_time')
                time_window = widget.config.get('time_window', '1h')
                
                if metric_name in self.metrics_streams:
                    # Filter data based on time window
                    current_time = time.time()
                    window_seconds = {'1h': 3600, '2h': 7200, '24h': 86400}.get(time_window, 3600)
                    cutoff_time = current_time - window_seconds
                    
                    filtered_data = [
                        point for point in self.metrics_streams[metric_name]
                        if point['timestamp'] >= cutoff_time
                    ]
                    
                    widget_data['data'] = filtered_data
                    
                    # Generate chart configuration
                    if widget.widget_type in ['line_chart', 'area_chart']:
                        chart_config = ChartConfig(
                            chart_type=ChartType.LINE if widget.widget_type == 'line_chart' else ChartType.AREA,
                            title=widget.title,
                            metric_name=metric_name,
                            time_range=TimeRange.LAST_HOUR
                        )
                        
                        # Convert data format for chart
                        chart_data = []
                        for point in filtered_data:
                            chart_data.append({
                                'timestamp': datetime.fromtimestamp(point['timestamp']),
                                'value': point['value']
                            })
                        
                        chart = self.visualization_service.create_line_chart(chart_config, chart_data)
                        widget_data['chart_config'] = chart.chart_definition
                
            elif widget.data_source == 'system_alerts':
                # Get active alerts
                alerts_data = []
                max_items = widget.config.get('max_items', 10)
                
                for alert in list(self.active_alerts.values())[:max_items]:
                    alerts_data.append(alert.to_dict())
                
                widget_data['data'] = alerts_data
                
            elif widget.data_source == 'trending_content':
                content_analytics = await get_content_analytics_engine()
                trending_content = await content_analytics.get_trending_content(limit=10)
                widget_data['data'] = [item.to_dict() for item in trending_content]
                
            elif widget.data_source == 'popular_content':
                user_analytics = await get_user_behavior_analytics()
                popular_content = await user_analytics.get_popular_content(hours=24)
                widget_data['data'] = popular_content
            
            return widget_data
            
        except Exception as e:
            logger.error(f"Failed to get widget data for {widget.widget_id}: {e}")
            return {'error': str(e)}
    
    async def get_dashboard_list(self) -> List[Dict[str, Any]]:
        """Get list of all available dashboards"""
        dashboard_list = []
        
        for dashboard_id, config in self.dashboards.items():
            dashboard_info = {
                'dashboard_id': dashboard_id,
                'title': config.title,
                'description': config.description,
                'type': config.dashboard_type.value,
                'widget_count': len(config.widgets),
                'theme': config.theme,
                'auto_refresh': config.auto_refresh,
                'refresh_interval': config.refresh_interval,
                'created_at': config.created_at
            }
            dashboard_list.append(dashboard_info)
        
        return dashboard_list
    
    async def get_real_time_stream_data(self, metric_names: List[str], minutes: int = 60) -> Dict[str, List[Dict[str, Any]]]:
        """Get real-time stream data for specified metrics"""
        try:
            cutoff_time = time.time() - (minutes * 60)
            stream_data = {}
            
            for metric_name in metric_names:
                if metric_name in self.metrics_streams:
                    filtered_data = [
                        point for point in self.metrics_streams[metric_name]
                        if point['timestamp'] >= cutoff_time
                    ]
                    stream_data[metric_name] = filtered_data
                else:
                    stream_data[metric_name] = []
            
            return stream_data
            
        except Exception as e:
            logger.error(f"Failed to get real-time stream data: {e}")
            return {}
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a system alert"""
        try:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].acknowledged = True
                logger.info(f"📋 Alert acknowledged: {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve a system alert"""
        try:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                del self.active_alerts[alert_id]
                logger.info(f"✅ Alert resolved: {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False
    
    async def get_system_summary(self) -> Dict[str, Any]:
        """Get comprehensive system summary for executive dashboard"""
        try:
            # Collect summary data from all services
            performance_monitor = await get_performance_monitor()
            user_analytics = await get_user_behavior_analytics()
            content_analytics = await get_content_analytics_engine()
            
            system_health = await performance_monitor.get_system_health_summary()
            user_summary = await user_analytics.get_analytics_summary()
            trending_content = await content_analytics.get_trending_content(limit=5)
            
            summary = {
                'timestamp': time.time(),
                'system_health': {
                    'overall_score': system_health.get('health_score', 0),
                    'status': system_health.get('health_status', 'unknown'),
                    'active_alerts': len(self.active_alerts),
                    'critical_alerts': len([a for a in self.active_alerts.values() if a.severity == AlertSeverity.CRITICAL])
                },
                'user_activity': {
                    'active_users_1h': user_summary.get('active_users', {}).get('last_hour', 0),
                    'active_users_24h': user_summary.get('active_users', {}).get('last_24_hours', 0),
                    'active_sessions': user_summary.get('active_sessions', 0),
                    'avg_engagement_score': user_summary.get('avg_engagement_score', 0)
                },
                'content_performance': {
                    'trending_items': len(trending_content),
                    'top_trending_score': max([item.trending_score for item in trending_content], default=0),
                    'avg_trending_score': sum([item.trending_score for item in trending_content]) / len(trending_content) if trending_content else 0
                },
                'system_performance': {
                    'response_time': system_health.get('current_metrics', {}).get('api_response_time', {}).get('value', 0),
                    'cpu_usage': system_health.get('current_metrics', {}).get('cpu_usage', {}).get('value', 0),
                    'memory_usage': system_health.get('current_metrics', {}).get('memory_usage', {}).get('value', 0),
                    'uptime_hours': system_health.get('monitoring_stats', {}).get('monitoring_uptime', 0) / 3600
                },
                'dashboard_stats': self.stats
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get system summary: {e}")
            return {'error': str(e)}
    
    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get advanced dashboard system statistics"""
        try:
            return {
                "service": "Advanced Dashboard System",
                "status": "active" if self.system_active else "inactive",
                "stats": self.stats,
                "configuration": self.config,
                "system_status": {
                    "total_dashboards": len(self.dashboards),
                    "active_alerts": len(self.active_alerts),
                    "metrics_streams": len(self.metrics_streams),
                    "total_data_points": sum(len(stream) for stream in self.metrics_streams.values()),
                    "alerts_history_size": len(self.alerts_history),
                    "last_update": self.last_update_time,
                    "subscribers": sum(len(subs) for subs in self.dashboard_subscribers.values())
                },
                "capabilities": {
                    "real_time_dashboards": True,
                    "predictive_analytics": self.config['enable_predictive_analytics'],
                    "custom_alerts": True,
                    "multi_source_data": True,
                    "interactive_widgets": True,
                    "streaming_updates": True
                }
            }
        except Exception as e:
            logger.error(f"Failed to get service statistics: {e}")
            return {"service": "Advanced Dashboard System", "error": str(e)}


# Global advanced dashboard system instance
_advanced_dashboard_system: Optional[AdvancedDashboardSystem] = None

async def get_advanced_dashboard_system(config: Optional[Dict[str, Any]] = None) -> AdvancedDashboardSystem:
    """Get or create global advanced dashboard system instance"""
    global _advanced_dashboard_system
    
    if _advanced_dashboard_system is None:
        _advanced_dashboard_system = AdvancedDashboardSystem(config)
    
    return _advanced_dashboard_system