"""
Visualization Service - Phase 3 Week 36
Chart generation and data visualization for monitoring dashboard  
"""

import json
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from src.utils.logger import get_logger

logger = get_logger("mvidarr.visualization")


class ChartType(Enum):
    """Chart types supported"""
    LINE = "line"
    AREA = "area"
    BAR = "bar"
    GAUGE = "gauge"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"


class TimeRange(Enum):
    """Time range options"""
    LAST_HOUR = "1h"
    LAST_4_HOURS = "4h" 
    LAST_12_HOURS = "12h"
    LAST_24_HOURS = "24h"
    LAST_WEEK = "7d"


@dataclass
class ChartConfig:
    """Chart configuration"""
    chart_type: ChartType
    title: str
    metric_name: str
    time_range: TimeRange
    height: int = 300
    width: int = 600
    show_grid: bool = True
    show_legend: bool = True
    color_scheme: str = "dark"
    threshold_lines: List[Dict[str, Any]] = None
    y_axis_min: Optional[float] = None
    y_axis_max: Optional[float] = None


@dataclass
class ChartData:
    """Chart data structure"""
    config: ChartConfig
    data_points: List[Dict[str, Any]]
    summary_stats: Dict[str, float]
    generated_at: datetime
    chart_definition: Dict[str, Any]


class VisualizationService:
    """Service for generating dashboard visualizations"""
    
    def __init__(self):
        self.color_schemes = {
            "dark": {
                "primary": "#4CAF50",
                "secondary": "#2196F3", 
                "warning": "#FF9800",
                "error": "#f44336",
                "background": "#1a1a1a",
                "text": "#ffffff"
            },
            "light": {
                "primary": "#4CAF50",
                "secondary": "#2196F3",
                "warning": "#FF9800", 
                "error": "#f44336",
                "background": "#ffffff",
                "text": "#000000"
            }
        }
        
        logger.info("📈 Visualization service initialized")
    
    def create_line_chart(self, config: ChartConfig, data_points: List[Dict[str, Any]]) -> ChartData:
        """Create line chart configuration"""
        
        # Prepare data for chart
        chart_data = []
        for point in data_points:
            chart_data.append({
                "x": point["timestamp"].isoformat() if isinstance(point["timestamp"], datetime) else point["timestamp"],
                "y": point["value"]
            })
        
        # Sort by timestamp
        chart_data.sort(key=lambda x: x["x"])
        
        # Calculate summary statistics
        values = [point["value"] for point in data_points if "value" in point]
        summary_stats = self._calculate_summary_stats(values)
        
        # Generate Chart.js configuration
        colors = self.color_schemes[config.color_scheme]
        
        chart_definition = {
            "type": "line",
            "data": {
                "datasets": [{
                    "label": config.title,
                    "data": chart_data,
                    "borderColor": colors["primary"],
                    "backgroundColor": colors["primary"] + "20",
                    "borderWidth": 2,
                    "fill": config.chart_type == ChartType.AREA,
                    "tension": 0.4
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": config.title,
                        "color": colors["text"]
                    },
                    "legend": {
                        "display": config.show_legend,
                        "labels": {"color": colors["text"]}
                    }
                },
                "scales": {
                    "x": {
                        "type": "time",
                        "time": {
                            "unit": self._get_time_unit(config.time_range)
                        },
                        "grid": {"display": config.show_grid, "color": colors["text"] + "20"},
                        "ticks": {"color": colors["text"]}
                    },
                    "y": {
                        "beginAtZero": config.y_axis_min is None,
                        "min": config.y_axis_min,
                        "max": config.y_axis_max,
                        "grid": {"display": config.show_grid, "color": colors["text"] + "20"},
                        "ticks": {"color": colors["text"]}
                    }
                },
                "elements": {
                    "point": {
                        "radius": 3,
                        "hoverRadius": 6
                    }
                }
            }
        }
        
        # Add threshold lines if configured
        if config.threshold_lines:
            chart_definition["options"]["plugins"]["annotation"] = {
                "annotations": {}
            }
            
            for i, threshold in enumerate(config.threshold_lines):
                chart_definition["options"]["plugins"]["annotation"]["annotations"][f"threshold_{i}"] = {
                    "type": "line",
                    "yMin": threshold["value"],
                    "yMax": threshold["value"],
                    "borderColor": threshold.get("color", colors["warning"]),
                    "borderWidth": 2,
                    "label": {
                        "content": threshold.get("label", f"Threshold: {threshold['value']}"),
                        "enabled": True,
                        "position": "end"
                    }
                }
        
        return ChartData(
            config=config,
            data_points=data_points,
            summary_stats=summary_stats,
            generated_at=datetime.utcnow(),
            chart_definition=chart_definition
        )
    
    def create_gauge_chart(self, config: ChartConfig, current_value: float, 
                          max_value: float, thresholds: Dict[str, float] = None) -> ChartData:
        """Create gauge chart for single metric display"""
        
        colors = self.color_schemes[config.color_scheme]
        
        # Determine color based on thresholds
        value_color = colors["primary"]
        if thresholds:
            if current_value >= thresholds.get("critical", float('inf')):
                value_color = colors["error"]
            elif current_value >= thresholds.get("warning", float('inf')):
                value_color = colors["warning"]
        
        chart_definition = {
            "type": "doughnut",
            "data": {
                "datasets": [{
                    "data": [current_value, max_value - current_value],
                    "backgroundColor": [value_color, colors["background"]],
                    "borderWidth": 0,
                    "cutout": "80%"
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {"display": False},
                    "title": {
                        "display": True,
                        "text": config.title,
                        "color": colors["text"]
                    }
                },
                "rotation": -90,
                "circumference": 180
            },
            "plugins": [{
                "id": "gaugeText",
                "afterDraw": f"""
                function(chart) {{
                    var ctx = chart.ctx;
                    ctx.save();
                    ctx.font = 'bold 24px Arial';
                    ctx.fillStyle = '{colors["text"]}';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    var centerX = chart.width / 2;
                    var centerY = chart.height / 2 + 20;
                    ctx.fillText('{current_value:.1f}', centerX, centerY);
                    ctx.restore();
                }}
                """
            }]
        }
        
        summary_stats = {
            "current": current_value,
            "max": max_value,
            "percentage": (current_value / max_value) * 100
        }
        
        return ChartData(
            config=config,
            data_points=[{"value": current_value, "timestamp": datetime.utcnow()}],
            summary_stats=summary_stats,
            generated_at=datetime.utcnow(),
            chart_definition=chart_definition
        )
    
    def create_bar_chart(self, config: ChartConfig, categories: List[str], 
                        values: List[float], colors_override: List[str] = None) -> ChartData:
        """Create bar chart for categorical data"""
        
        colors = self.color_schemes[config.color_scheme]
        
        chart_colors = colors_override or [colors["primary"]] * len(values)
        
        chart_definition = {
            "type": "bar",
            "data": {
                "labels": categories,
                "datasets": [{
                    "label": config.title,
                    "data": values,
                    "backgroundColor": chart_colors,
                    "borderColor": chart_colors,
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": config.title,
                        "color": colors["text"]
                    },
                    "legend": {
                        "display": config.show_legend,
                        "labels": {"color": colors["text"]}
                    }
                },
                "scales": {
                    "x": {
                        "grid": {"display": config.show_grid, "color": colors["text"] + "20"},
                        "ticks": {"color": colors["text"]}
                    },
                    "y": {
                        "beginAtZero": True,
                        "grid": {"display": config.show_grid, "color": colors["text"] + "20"},
                        "ticks": {"color": colors["text"]}
                    }
                }
            }
        }
        
        summary_stats = self._calculate_summary_stats(values)
        
        data_points = [
            {"category": cat, "value": val, "timestamp": datetime.utcnow()}
            for cat, val in zip(categories, values)
        ]
        
        return ChartData(
            config=config,
            data_points=data_points,
            summary_stats=summary_stats,
            generated_at=datetime.utcnow(),
            chart_definition=chart_definition
        )
    
    def create_pie_chart(self, config: ChartConfig, labels: List[str], 
                        values: List[float]) -> ChartData:
        """Create pie chart for distribution data"""
        
        colors = self.color_schemes[config.color_scheme]
        
        # Generate colors for each slice
        chart_colors = []
        base_colors = [colors["primary"], colors["secondary"], colors["warning"], colors["error"]]
        for i in range(len(values)):
            chart_colors.append(base_colors[i % len(base_colors)])
        
        chart_definition = {
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": values,
                    "backgroundColor": chart_colors,
                    "borderColor": colors["background"],
                    "borderWidth": 2
                }]
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": config.title,
                        "color": colors["text"]
                    },
                    "legend": {
                        "display": config.show_legend,
                        "labels": {"color": colors["text"]},
                        "position": "right"
                    }
                }
            }
        }
        
        total = sum(values)
        summary_stats = {
            "total": total,
            "largest_slice": max(values) if values else 0,
            "smallest_slice": min(values) if values else 0
        }
        
        data_points = [
            {"label": label, "value": val, "percentage": (val/total*100) if total > 0 else 0}
            for label, val in zip(labels, values)
        ]
        
        return ChartData(
            config=config,
            data_points=data_points,
            summary_stats=summary_stats,
            generated_at=datetime.utcnow(),
            chart_definition=chart_definition
        )
    
    def create_dashboard_layout(self, charts: List[ChartData]) -> Dict[str, Any]:
        """Create complete dashboard layout with multiple charts"""
        
        layout = {
            "dashboard": {
                "title": "MVidarr Monitoring Dashboard",
                "generated_at": datetime.utcnow().isoformat(),
                "chart_count": len(charts),
                "layout": "grid",
                "theme": "dark"
            },
            "charts": []
        }
        
        for i, chart in enumerate(charts):
            chart_config = {
                "id": f"chart_{i}",
                "position": {
                    "row": i // 2,
                    "col": i % 2,
                    "width": chart.config.width,
                    "height": chart.config.height
                },
                "chart_definition": chart.chart_definition,
                "summary_stats": chart.summary_stats,
                "last_updated": chart.generated_at.isoformat()
            }
            
            layout["charts"].append(chart_config)
        
        return layout
    
    def _calculate_summary_stats(self, values: List[float]) -> Dict[str, float]:
        """Calculate summary statistics for data"""
        if not values:
            return {}
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values) if len(values) > 1 else values[0],
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
            "range": max(values) - min(values)
        }
    
    def _get_time_unit(self, time_range: TimeRange) -> str:
        """Get appropriate time unit for chart x-axis"""
        mapping = {
            TimeRange.LAST_HOUR: "minute",
            TimeRange.LAST_4_HOURS: "minute", 
            TimeRange.LAST_12_HOURS: "hour",
            TimeRange.LAST_24_HOURS: "hour",
            TimeRange.LAST_WEEK: "day"
        }
        return mapping.get(time_range, "minute")
    
    def generate_performance_dashboard(self, metrics_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Generate complete performance dashboard"""
        charts = []
        
        # CPU Usage Line Chart
        if "system.cpu.percent" in metrics_data:
            cpu_config = ChartConfig(
                chart_type=ChartType.AREA,
                title="CPU Usage (%)",
                metric_name="system.cpu.percent",
                time_range=TimeRange.LAST_HOUR,
                threshold_lines=[
                    {"value": 80, "label": "Warning", "color": "#FF9800"},
                    {"value": 95, "label": "Critical", "color": "#f44336"}
                ]
            )
            cpu_chart = self.create_line_chart(cpu_config, metrics_data["system.cpu.percent"])
            charts.append(cpu_chart)
        
        # Memory Usage Gauge
        if "system.memory.percent" in metrics_data:
            memory_data = metrics_data["system.memory.percent"]
            current_memory = memory_data[-1]["value"] if memory_data else 0
            
            memory_config = ChartConfig(
                chart_type=ChartType.GAUGE,
                title="Memory Usage",
                metric_name="system.memory.percent",
                time_range=TimeRange.LAST_HOUR
            )
            memory_chart = self.create_gauge_chart(
                memory_config, 
                current_memory, 
                100,
                {"warning": 80, "critical": 95}
            )
            charts.append(memory_chart)
        
        # Response Time Line Chart
        if "app.response_time.avg_ms" in metrics_data:
            response_config = ChartConfig(
                chart_type=ChartType.LINE,
                title="Average Response Time (ms)",
                metric_name="app.response_time.avg_ms", 
                time_range=TimeRange.LAST_HOUR
            )
            response_chart = self.create_line_chart(response_config, metrics_data["app.response_time.avg_ms"])
            charts.append(response_chart)
        
        return self.create_dashboard_layout(charts)