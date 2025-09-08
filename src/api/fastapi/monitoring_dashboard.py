"""
Monitoring Dashboard API - Phase 3 Week 36
Real-time monitoring dashboard with WebSocket support and interactive analytics
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.services.analytics_service import get_analytics_service, MetricPoint, MetricType, AlertRule
from src.middleware.auto_scaling_middleware import get_scaling_status
from src.middleware.circuit_breaker_middleware import CircuitBreakerAPI
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.monitoring_dashboard")

router = APIRouter(
    prefix="/api/dashboard",
    tags=["monitoring-dashboard"],
    responses={
        404: {"description": "Dashboard data not found"},
        500: {"description": "Dashboard service error"}
    }
)


# Response Models
class DashboardSummaryResponse(BaseModel):
    """Dashboard summary data"""
    timestamp: datetime
    system: Dict[str, Any]
    application: Dict[str, Any] 
    analytics: Dict[str, Any]


class MetricHistoryResponse(BaseModel):
    """Metric history data"""
    metric_name: str
    time_window_hours: int
    data_points: List[Dict[str, Any]]
    summary: Dict[str, float]


class AlertRuleRequest(BaseModel):
    """Alert rule creation request"""
    rule_id: str
    metric_name: str
    threshold: float
    comparison: str = Field(pattern=r'^(>|<|>=|<=|==)$')
    time_window_minutes: int = Field(ge=1, le=1440)
    severity: str = Field(pattern=r'^(low|medium|high|critical)$')
    description: str = ""
    notification_channels: List[str] = []


class DashboardConfigResponse(BaseModel):
    """Dashboard configuration"""
    refresh_interval_seconds: int
    available_metrics: List[str]
    chart_types: List[str]
    alert_severities: List[str]
    time_windows: List[str]


# WebSocket connection manager
class DashboardWebSocketManager:
    """Manage WebSocket connections for real-time dashboard updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.update_task = None
        
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # Start update task if first connection
        if len(self.active_connections) == 1:
            self.update_task = asyncio.create_task(self._broadcast_updates())
        
        logger.info(f"📡 WebSocket connected. Active connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            
        # Stop update task if no connections
        if not self.active_connections and self.update_task:
            self.update_task.cancel()
            self.update_task = None
        
        logger.info(f"📡 WebSocket disconnected. Active connections: {len(self.active_connections)}")
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
        
        message_json = json.dumps(message, default=str)
        
        # Send to all connections, remove dead connections
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except WebSocketDisconnect:
                dead_connections.append(connection)
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")
                dead_connections.append(connection)
        
        # Remove dead connections
        for connection in dead_connections:
            self.disconnect(connection)
    
    async def _broadcast_updates(self):
        """Background task to broadcast dashboard updates"""
        while self.active_connections:
            try:
                # Get current dashboard data
                analytics_service = await get_analytics_service()
                dashboard_summary = await analytics_service.get_dashboard_summary()
                
                # Get scaling status
                scaling_status = await get_scaling_status()
                
                # Broadcast update
                await self.broadcast_message({
                    "type": "dashboard_update",
                    "timestamp": datetime.utcnow(),
                    "data": {
                        "summary": dashboard_summary,
                        "scaling": scaling_status
                    }
                })
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dashboard broadcast error: {e}")
                await asyncio.sleep(10)  # Wait before retrying


# Global WebSocket manager
websocket_manager = DashboardWebSocketManager()


# WebSocket endpoint for real-time updates
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await websocket_manager.connect(websocket)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong, requests, etc.)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle client requests
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.utcnow()
                    }, default=str))
                
                elif message.get("type") == "request_metric_history":
                    metric_name = message.get("metric_name")
                    time_window = message.get("time_window_hours", 1)
                    
                    analytics_service = await get_analytics_service()
                    history = await analytics_service.get_metric_history(metric_name, time_window)
                    
                    await websocket.send_text(json.dumps({
                        "type": "metric_history",
                        "metric_name": metric_name,
                        "data": history
                    }, default=str))
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(websocket)


# REST API endpoints
@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary():
    """Get dashboard summary statistics"""
    try:
        analytics_service = await get_analytics_service()
        analytics_service.increment_dashboard_views()
        
        summary = await analytics_service.get_dashboard_summary()
        
        return DashboardSummaryResponse(
            timestamp=summary["timestamp"],
            system=summary["system"],
            application=summary["application"],
            analytics=summary["analytics"]
        )
        
    except Exception as e:
        logger.error(f"Dashboard summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_name}/history", response_model=MetricHistoryResponse)
async def get_metric_history(
    metric_name: str,
    time_window_hours: int = Query(1, ge=1, le=24, description="Time window in hours")
):
    """Get metric history for dashboard charts"""
    try:
        analytics_service = await get_analytics_service()
        history = await analytics_service.get_metric_history(metric_name, time_window_hours)
        
        # Calculate summary statistics
        values = [point["value"] for point in history if "value" in point]
        summary = {}
        if values:
            summary = {
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "count": len(values)
            }
        
        return MetricHistoryResponse(
            metric_name=metric_name,
            time_window_hours=time_window_hours,
            data_points=history,
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"Metric history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/available")
async def get_available_metrics():
    """Get list of available metrics for dashboard"""
    return {
        "system_metrics": [
            "system.cpu.percent",
            "system.memory.percent", 
            "system.memory.used_gb",
            "system.disk.usage_percent"
        ],
        "application_metrics": [
            "app.connections.active",
            "app.requests.per_second",
            "app.response_time.avg_ms",
            "app.error_rate.percent"
        ],
        "performance_metrics": [
            "performance.throughput.rps",
            "performance.latency.p95_ms",
            "performance.latency.p99_ms"
        ]
    }


@router.get("/alerts/active")
async def get_active_alerts():
    """Get all active alerts"""
    try:
        analytics_service = await get_analytics_service()
        alerts = await analytics_service.get_active_alerts()
        
        return {
            "alerts": alerts,
            "count": len(alerts),
            "by_severity": {
                "critical": len([a for a in alerts if a.get("severity") == "critical"]),
                "high": len([a for a in alerts if a.get("severity") == "high"]),
                "medium": len([a for a in alerts if a.get("severity") == "medium"]),
                "low": len([a for a in alerts if a.get("severity") == "low"])
            }
        }
        
    except Exception as e:
        logger.error(f"Active alerts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/rules")
async def create_alert_rule(rule_request: AlertRuleRequest):
    """Create new alert rule"""
    try:
        analytics_service = await get_analytics_service()
        
        rule = AlertRule(
            rule_id=rule_request.rule_id,
            metric_name=rule_request.metric_name,
            threshold=rule_request.threshold,
            comparison=rule_request.comparison,
            time_window_minutes=rule_request.time_window_minutes,
            severity=rule_request.severity,
            description=rule_request.description,
            notification_channels=rule_request.notification_channels
        )
        
        await analytics_service.add_alert_rule(rule)
        
        return {
            "message": f"Alert rule '{rule_request.rule_id}' created successfully",
            "rule_id": rule_request.rule_id
        }
        
    except Exception as e:
        logger.error(f"Create alert rule error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=DashboardConfigResponse)
async def get_dashboard_config():
    """Get dashboard configuration"""
    return DashboardConfigResponse(
        refresh_interval_seconds=5,
        available_metrics=[
            "system.cpu.percent", "system.memory.percent", "system.disk.usage_percent",
            "app.connections.active", "app.requests.per_second", "app.response_time.avg_ms", 
            "app.error_rate.percent"
        ],
        chart_types=["line", "area", "bar", "gauge"],
        alert_severities=["low", "medium", "high", "critical"],
        time_windows=["1h", "4h", "12h", "24h"]
    )


@router.get("/status")
async def get_dashboard_status():
    """Get dashboard service status"""
    try:
        analytics_service = await get_analytics_service()
        
        # Get auto-scaling status
        scaling_status = await get_scaling_status()
        
        return {
            "service_status": "operational",
            "websocket_connections": len(websocket_manager.active_connections),
            "analytics_enabled": True,
            "real_time_updates": len(websocket_manager.active_connections) > 0,
            "auto_scaling_enabled": scaling_status.get("auto_scaling_enabled", False),
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Dashboard status error: {e}")
        return {
            "service_status": "degraded",
            "error": str(e),
            "timestamp": datetime.utcnow()
        }


@router.get("/demo")
async def get_dashboard_demo():
    """Demo dashboard page (basic HTML)"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MVidarr Monitoring Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #fff; }
            .header { text-align: center; margin-bottom: 30px; }
            .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .metric-card { background: #2d2d2d; padding: 20px; border-radius: 8px; border: 1px solid #444; }
            .metric-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #4CAF50; }
            .metric-value { font-size: 24px; font-weight: bold; margin-bottom: 5px; }
            .metric-status { font-size: 14px; opacity: 0.8; }
            .status-healthy { color: #4CAF50; }
            .status-warning { color: #FF9800; }
            .status-error { color: #f44336; }
            .websocket-status { position: fixed; top: 10px; right: 10px; padding: 10px; background: #333; border-radius: 4px; }
            .connected { color: #4CAF50; }
            .disconnected { color: #f44336; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 MVidarr Monitoring Dashboard</h1>
            <p>Phase 3 Week 36: Real-time Analytics & Monitoring</p>
        </div>
        
        <div class="websocket-status" id="wsStatus">
            <span id="wsIndicator">🔴 Connecting...</span>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">System CPU</div>
                <div class="metric-value" id="cpuValue">--</div>
                <div class="metric-status" id="cpuStatus">Loading...</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Memory Usage</div>
                <div class="metric-value" id="memoryValue">--</div>
                <div class="metric-status" id="memoryStatus">Loading...</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Response Time</div>
                <div class="metric-value" id="responseTimeValue">--</div>
                <div class="metric-status" id="responseTimeStatus">Loading...</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Active Alerts</div>
                <div class="metric-value" id="alertsValue">--</div>
                <div class="metric-status" id="alertsStatus">Loading...</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Auto Scaling</div>
                <div class="metric-value" id="scalingValue">--</div>
                <div class="metric-status" id="scalingStatus">Loading...</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Dashboard Views</div>
                <div class="metric-value" id="viewsValue">--</div>
                <div class="metric-status" id="viewsStatus">Analytics active</div>
            </div>
        </div>
        
        <script>
            let ws;
            let reconnectTimer;
            
            function connect() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/api/dashboard/ws`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function() {
                    document.getElementById('wsIndicator').innerHTML = '🟢 Connected';
                    document.getElementById('wsIndicator').className = 'connected';
                    clearInterval(reconnectTimer);
                };
                
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    
                    if (message.type === 'dashboard_update') {
                        updateDashboard(message.data);
                    }
                };
                
                ws.onclose = function() {
                    document.getElementById('wsIndicator').innerHTML = '🔴 Disconnected';
                    document.getElementById('wsIndicator').className = 'disconnected';
                    
                    // Reconnect every 5 seconds
                    reconnectTimer = setTimeout(connect, 5000);
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                };
            }
            
            function updateDashboard(data) {
                if (data.summary) {
                    const summary = data.summary;
                    
                    // Update CPU
                    document.getElementById('cpuValue').textContent = summary.system.cpu_percent.toFixed(1) + '%';
                    document.getElementById('cpuStatus').textContent = summary.system.status;
                    document.getElementById('cpuStatus').className = 'metric-status status-' + (summary.system.status === 'healthy' ? 'healthy' : 'warning');
                    
                    // Update Memory
                    document.getElementById('memoryValue').textContent = summary.system.memory_percent.toFixed(1) + '%';
                    document.getElementById('memoryStatus').textContent = summary.system.status;
                    document.getElementById('memoryStatus').className = 'metric-status status-' + (summary.system.status === 'healthy' ? 'healthy' : 'warning');
                    
                    // Update Response Time
                    document.getElementById('responseTimeValue').textContent = summary.application.response_time_ms.toFixed(1) + 'ms';
                    document.getElementById('responseTimeStatus').textContent = summary.application.status;
                    
                    // Update Alerts
                    document.getElementById('alertsValue').textContent = summary.application.active_alerts;
                    document.getElementById('alertsStatus').textContent = summary.application.active_alerts > 0 ? 'Issues detected' : 'All clear';
                    document.getElementById('alertsStatus').className = 'metric-status status-' + (summary.application.active_alerts > 0 ? 'warning' : 'healthy');
                    
                    // Update Dashboard Views
                    document.getElementById('viewsValue').textContent = summary.analytics.dashboard_views;
                }
                
                if (data.scaling) {
                    document.getElementById('scalingValue').textContent = data.scaling.auto_scaling_enabled ? 'Enabled' : 'Disabled';
                    document.getElementById('scalingStatus').textContent = data.scaling.auto_scaling_enabled ? 'Monitoring load' : 'Manual scaling';
                }
            }
            
            // Connect on page load
            connect();
            
            // Send periodic pings
            setInterval(function() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({type: 'ping'}));
                }
            }, 30000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)