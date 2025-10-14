"""
Analytics & Reporting FastAPI Endpoints - Phase 3 Week 27
Comprehensive API endpoints for analytics, reporting, and real-time dashboards
"""

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from src.services.analytics_service import get_analytics_service
from src.services.content_analytics_engine import (
    ContentType,
    MetricType,
    get_content_analytics_engine,
    record_video_view,
)
from src.services.performance_monitor import get_performance_monitor
from src.services.real_time_reporting_system import (
    ReportConfiguration,
    ReportFormat,
    ReportSchedule,
    ReportType,
    get_real_time_reporting_system,
)
from src.services.user_behavior_analytics import (
    UserActionType,
    get_user_behavior_analytics,
    track_page_view,
    track_search_query,
    track_video_play,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.analytics_reporting")

# Create router
analytics_router = APIRouter(prefix="/analytics", tags=["analytics", "reporting"])


# Pydantic models for request/response
class UserActionRequest(BaseModel):
    user_id: str = Field(..., description="User identifier")
    action_type: str = Field(..., description="Type of action performed")
    page_url: str = Field(..., description="URL where action occurred")
    user_agent: str = Field(..., description="User's browser/client info")
    session_id: Optional[str] = Field(None, description="Session identifier")
    ip_address: Optional[str] = Field("", description="User's IP address")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional action data"
    )
    duration_ms: Optional[int] = Field(
        None, description="Action duration in milliseconds"
    )


class ContentMetricRequest(BaseModel):
    content_id: str = Field(..., description="Content identifier")
    content_type: str = Field(..., description="Type of content")
    metric_type: str = Field(..., description="Type of metric")
    value: float = Field(..., description="Metric value")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metric data"
    )


class ReportConfigRequest(BaseModel):
    report_type: str = Field(..., description="Type of report")
    format: str = Field(..., description="Report format")
    schedule: str = Field(..., description="Report schedule")
    title: str = Field(..., description="Report title")
    description: str = Field(..., description="Report description")
    time_window_hours: int = Field(24, description="Analysis time window in hours")
    include_charts: bool = Field(True, description="Include charts in report")
    include_insights: bool = Field(True, description="Include insights in report")
    include_recommendations: bool = Field(True, description="Include recommendations")
    recipients: List[str] = Field([], description="Report recipients")
    webhook_urls: List[str] = Field([], description="Webhook URLs for delivery")


class AnalyticsResponse(BaseModel):
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    processing_time_ms: Optional[float] = Field(None, description="Processing time")


# User Behavior Analytics Endpoints
@analytics_router.post("/user-actions", response_model=AnalyticsResponse)
async def track_user_action(request: UserActionRequest):
    """Track a user action event"""
    try:
        start_time = time.time()

        user_analytics = await get_user_behavior_analytics()

        # Validate action type
        try:
            action_type = UserActionType(request.action_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid action type: {request.action_type}"
            )

        # Track the action
        action_id = await user_analytics.track_user_action(
            user_id=request.user_id,
            action_type=action_type,
            page_url=request.page_url,
            user_agent=request.user_agent,
            session_id=request.session_id,
            ip_address=request.ip_address or "",
            metadata=request.metadata or {},
            duration_ms=request.duration_ms,
        )

        processing_time = (time.time() - start_time) * 1000

        return AnalyticsResponse(
            success=True,
            message="User action tracked successfully",
            data={"action_id": action_id},
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Failed to track user action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/user-engagement/{user_id}", response_model=AnalyticsResponse)
async def get_user_engagement_metrics(user_id: str):
    """Get engagement metrics for a specific user"""
    try:
        user_analytics = await get_user_behavior_analytics()

        engagement_metrics = await user_analytics.get_user_engagement_metrics(user_id)

        if not engagement_metrics:
            raise HTTPException(
                status_code=404, detail="User engagement data not found"
            )

        return AnalyticsResponse(
            success=True,
            message="User engagement metrics retrieved successfully",
            data=engagement_metrics.to_dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user engagement metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/user-behavior-summary", response_model=AnalyticsResponse)
async def get_user_behavior_summary():
    """Get comprehensive user behavior analytics summary"""
    try:
        user_analytics = await get_user_behavior_analytics()

        summary = await user_analytics.get_analytics_summary()

        return AnalyticsResponse(
            success=True,
            message="User behavior summary retrieved successfully",
            data=summary,
        )

    except Exception as e:
        logger.error(f"Failed to get user behavior summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/popular-content", response_model=AnalyticsResponse)
async def get_popular_content(
    hours: int = Query(24, description="Time window in hours")
):
    """Get popular content based on user interactions"""
    try:
        user_analytics = await get_user_behavior_analytics()

        popular_content = await user_analytics.get_popular_content(hours=hours)

        return AnalyticsResponse(
            success=True,
            message="Popular content retrieved successfully",
            data=popular_content,
        )

    except Exception as e:
        logger.error(f"Failed to get popular content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Content Analytics Endpoints
@analytics_router.post("/content-metrics", response_model=AnalyticsResponse)
async def record_content_metric(request: ContentMetricRequest):
    """Record a content performance metric"""
    try:
        start_time = time.time()

        content_analytics = await get_content_analytics_engine()

        # Validate content and metric types
        try:
            content_type = ContentType(request.content_type)
            metric_type = MetricType(request.metric_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {e}")

        # Record the metric
        await content_analytics.record_content_metric(
            content_id=request.content_id,
            content_type=content_type,
            metric_type=metric_type,
            value=request.value,
            user_id=request.user_id,
            session_id=request.session_id,
            metadata=request.metadata or {},
        )

        processing_time = (time.time() - start_time) * 1000

        return AnalyticsResponse(
            success=True,
            message="Content metric recorded successfully",
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record content metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get(
    "/content-performance/{content_id}", response_model=AnalyticsResponse
)
async def get_content_performance(content_id: str):
    """Get performance analysis for specific content"""
    try:
        content_analytics = await get_content_analytics_engine()

        performance = await content_analytics.get_content_performance(content_id)

        if not performance:
            raise HTTPException(
                status_code=404, detail="Content performance data not found"
            )

        return AnalyticsResponse(
            success=True,
            message="Content performance retrieved successfully",
            data=performance.to_dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get content performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/trending-content", response_model=AnalyticsResponse)
async def get_trending_content(
    limit: int = Query(20, description="Maximum number of results")
):
    """Get current trending content"""
    try:
        content_analytics = await get_content_analytics_engine()

        trending_content = await content_analytics.get_trending_content(limit=limit)

        trending_data = [item.to_dict() for item in trending_content]

        return AnalyticsResponse(
            success=True,
            message="Trending content retrieved successfully",
            data={"trending_content": trending_data, "count": len(trending_data)},
        )

    except Exception as e:
        logger.error(f"Failed to get trending content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get(
    "/content-insights/{content_id}", response_model=AnalyticsResponse
)
async def get_content_insights(content_id: str):
    """Get comprehensive insights for specific content"""
    try:
        content_analytics = await get_content_analytics_engine()

        insights = await content_analytics.get_content_insights(content_id)

        return AnalyticsResponse(
            success=True,
            message="Content insights retrieved successfully",
            data=insights,
        )

    except Exception as e:
        logger.error(f"Failed to get content insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Real-Time Reporting Endpoints
@analytics_router.post("/reports/configure", response_model=AnalyticsResponse)
async def create_report_configuration(request: ReportConfigRequest):
    """Create a new report configuration"""
    try:
        reporting_system = await get_real_time_reporting_system()

        # Validate enum values
        try:
            report_type = ReportType(request.report_type)
            format_type = ReportFormat(request.format)
            schedule_type = ReportSchedule(request.schedule)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")

        # Generate report ID
        import hashlib

        report_id = f"report_{hashlib.md5(f'{request.title}_{time.time()}'.encode()).hexdigest()[:12]}"

        # Create configuration
        config = ReportConfiguration(
            report_id=report_id,
            report_type=report_type,
            format=format_type,
            schedule=schedule_type,
            title=request.title,
            description=request.description,
            time_window_hours=request.time_window_hours,
            include_charts=request.include_charts,
            include_insights=request.include_insights,
            include_recommendations=request.include_recommendations,
            recipients=request.recipients,
            webhook_urls=request.webhook_urls,
        )

        # Create the configuration
        created_id = await reporting_system.create_report_configuration(config)

        return AnalyticsResponse(
            success=True,
            message="Report configuration created successfully",
            data={"report_id": created_id, "config": config.to_dict()},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create report configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.post(
    "/reports/generate/{report_id}", response_model=AnalyticsResponse
)
async def generate_report(report_id: str, background_tasks: BackgroundTasks):
    """Generate a report on-demand"""
    try:
        reporting_system = await get_real_time_reporting_system()

        # Generate report in background
        background_tasks.add_task(reporting_system.generate_report, report_id)

        return AnalyticsResponse(
            success=True,
            message="Report generation started",
            data={"report_id": report_id, "status": "generating"},
        )

    except Exception as e:
        logger.error(f"Failed to start report generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/reports/{report_id}", response_model=AnalyticsResponse)
async def get_generated_report(report_id: str):
    """Get a generated report"""
    try:
        reporting_system = await get_real_time_reporting_system()

        report = await reporting_system.get_generated_report(report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return AnalyticsResponse(
            success=True, message="Report retrieved successfully", data=report.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get generated report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/reports/{report_id}/download")
async def download_report_file(report_id: str):
    """Download report file if available"""
    try:
        reporting_system = await get_real_time_reporting_system()

        report = await reporting_system.get_generated_report(report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        if not report.file_path:
            raise HTTPException(status_code=404, detail="Report file not available")

        return FileResponse(
            path=report.file_path,
            filename=f"{report.config.title.replace(' ', '_')}.{report.config.format.value}",
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Real-Time Dashboard Endpoints
@analytics_router.get("/real-time/metrics", response_model=AnalyticsResponse)
async def get_real_time_metrics():
    """Get current real-time metrics"""
    try:
        reporting_system = await get_real_time_reporting_system()

        metrics = await reporting_system.get_real_time_metrics()

        if not metrics:
            raise HTTPException(
                status_code=404, detail="Real-time metrics not available"
            )

        return AnalyticsResponse(
            success=True,
            message="Real-time metrics retrieved successfully",
            data=metrics.to_dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/real-time/history", response_model=AnalyticsResponse)
async def get_metrics_history(
    minutes: int = Query(60, description="History window in minutes")
):
    """Get historical real-time metrics"""
    try:
        reporting_system = await get_real_time_reporting_system()

        history = await reporting_system.get_metrics_history(minutes=minutes)

        history_data = [metrics.to_dict() for metrics in history]

        return AnalyticsResponse(
            success=True,
            message="Metrics history retrieved successfully",
            data={
                "history": history_data,
                "count": len(history_data),
                "window_minutes": minutes,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/dashboard", response_class=HTMLResponse)
async def get_analytics_dashboard():
    """Get live analytics dashboard HTML"""
    try:
        dashboard_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>MVidarr Analytics Dashboard</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: white; }
                .header { text-align: center; margin-bottom: 30px; }
                .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
                .metric-card { background: #2a2a2a; padding: 20px; border-radius: 8px; border: 1px solid #444; }
                .metric-value { font-size: 2em; font-weight: bold; color: #4CAF50; }
                .metric-label { color: #ccc; margin-top: 5px; }
                .chart-container { height: 400px; margin: 20px 0; }
                .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
                .status-good { background: #4CAF50; }
                .status-warning { background: #FF9800; }
                .status-critical { background: #f44336; }
                .refresh-info { text-align: center; color: #888; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎬 MVidarr Analytics Dashboard</h1>
                <p>Real-time system and content analytics</p>
            </div>
            
            <div class="refresh-info">
                <span id="last-update">Loading...</span> | Auto-refresh every 30 seconds
            </div>
            
            <div class="metrics-grid" id="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value" id="active-users">-</div>
                    <div class="metric-label">Active Users (24h)</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-value" id="system-health">-</div>
                    <div class="metric-label">
                        <span class="status-indicator" id="health-indicator"></span>
                        System Health
                    </div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-value" id="trending-content">-</div>
                    <div class="metric-label">Trending Content Items</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-value" id="response-time">-</div>
                    <div class="metric-label">Avg Response Time (ms)</div>
                </div>
            </div>
            
            <div class="chart-container">
                <canvas id="activity-chart"></canvas>
            </div>
            
            <script>
                let activityChart = null;
                
                async function updateDashboard() {
                    try {
                        const response = await fetch('/analytics/real-time/metrics');
                        const data = await response.json();
                        
                        if (data.success) {
                            const metrics = data.data;
                            
                            // Update metric values
                            document.getElementById('active-users').textContent = 
                                metrics.user_metrics.active_users?.last_24_hours || 0;
                            
                            const healthScore = metrics.performance_metrics.health_score || 0;
                            document.getElementById('system-health').textContent = 
                                healthScore.toFixed(1) + '%';
                            
                            // Update health indicator
                            const healthIndicator = document.getElementById('health-indicator');
                            if (healthScore >= 90) {
                                healthIndicator.className = 'status-indicator status-good';
                            } else if (healthScore >= 70) {
                                healthIndicator.className = 'status-indicator status-warning';
                            } else {
                                healthIndicator.className = 'status-indicator status-critical';
                            }
                            
                            document.getElementById('trending-content').textContent = 
                                metrics.content_metrics.trending_content?.length || 0;
                            
                            document.getElementById('response-time').textContent = 
                                metrics.system_metrics.application?.response_time_ms?.toFixed(1) || 0;
                            
                            // Update timestamp
                            const updateTime = new Date(metrics.timestamp * 1000);
                            document.getElementById('last-update').textContent = 
                                'Last updated: ' + updateTime.toLocaleTimeString();
                            
                            // Update chart would go here
                            updateActivityChart(metrics);
                        }
                    } catch (error) {
                        console.error('Failed to update dashboard:', error);
                    }
                }
                
                function updateActivityChart(metrics) {
                    // Chart update logic would go here
                    // This is a placeholder for the actual chart implementation
                }
                
                // Initialize dashboard
                updateDashboard();
                
                // Auto-refresh every 30 seconds
                setInterval(updateDashboard, 30000);
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=dashboard_html)

    except Exception as e:
        logger.error(f"Failed to generate dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System Analytics Endpoints
@analytics_router.get("/system/health", response_model=AnalyticsResponse)
async def get_system_health():
    """Get comprehensive system health analytics"""
    try:
        performance_monitor = await get_performance_monitor()
        analytics_service = await get_analytics_service()

        system_health = await performance_monitor.get_system_health_summary()
        dashboard_summary = await analytics_service.get_dashboard_summary()

        return AnalyticsResponse(
            success=True,
            message="System health retrieved successfully",
            data={
                "system_health": system_health,
                "dashboard_summary": dashboard_summary,
                "timestamp": time.time(),
            },
        )

    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.get("/services/status", response_model=AnalyticsResponse)
async def get_analytics_services_status():
    """Get status of all analytics services"""
    try:
        user_analytics = await get_user_behavior_analytics()
        content_analytics = await get_content_analytics_engine()
        reporting_system = await get_real_time_reporting_system()

        user_stats = await user_analytics.get_service_statistics()
        content_stats = await content_analytics.get_service_statistics()
        reporting_stats = await reporting_system.get_service_statistics()

        return AnalyticsResponse(
            success=True,
            message="Analytics services status retrieved successfully",
            data={
                "user_behavior_analytics": user_stats,
                "content_analytics_engine": content_stats,
                "real_time_reporting_system": reporting_stats,
                "overall_status": "operational",
            },
        )

    except Exception as e:
        logger.error(f"Failed to get analytics services status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Convenience endpoints for common tracking operations
@analytics_router.post("/track/video-play", response_model=AnalyticsResponse)
async def track_video_play_endpoint(
    user_id: str, video_id: str, session_id: str, page_url: str, user_agent: str
):
    """Track video play action (convenience endpoint)"""
    try:
        action_id = await track_video_play(
            user_id, video_id, session_id, page_url, user_agent
        )
        await record_video_view(
            video_id, user_id, session_id, {"title": "Unknown", "artist": "Unknown"}
        )

        return AnalyticsResponse(
            success=True,
            message="Video play tracked successfully",
            data={"action_id": action_id},
        )

    except Exception as e:
        logger.error(f"Failed to track video play: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.post("/track/search", response_model=AnalyticsResponse)
async def track_search_endpoint(
    user_id: str,
    query: str,
    results_count: int,
    session_id: str,
    page_url: str,
    user_agent: str,
):
    """Track search query action (convenience endpoint)"""
    try:
        action_id = await track_search_query(
            user_id, query, results_count, session_id, page_url, user_agent
        )

        return AnalyticsResponse(
            success=True,
            message="Search tracked successfully",
            data={"action_id": action_id},
        )

    except Exception as e:
        logger.error(f"Failed to track search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@analytics_router.post("/track/page-view", response_model=AnalyticsResponse)
async def track_page_view_endpoint(
    user_id: str, page_url: str, user_agent: str, session_id: str, referrer: str = ""
):
    """Track page view action (convenience endpoint)"""
    try:
        action_id = await track_page_view(
            user_id, page_url, user_agent, session_id, referrer
        )

        return AnalyticsResponse(
            success=True,
            message="Page view tracked successfully",
            data={"action_id": action_id},
        )

    except Exception as e:
        logger.error(f"Failed to track page view: {e}")
        raise HTTPException(status_code=500, detail=str(e))
