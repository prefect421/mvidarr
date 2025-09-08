#!/usr/bin/env python3
"""
MVidarr Self-Hosted System Monitor
Simple monitoring for Docker-based MVidarr deployments
"""

import json
import logging
import os
import smtplib
import socket
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread

import docker
import psutil
import requests
import schedule
from flask import Flask, jsonify, render_template_string

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/data/monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MVidarrMonitor:
    def __init__(self):
        self.docker_client = docker.from_env()
        self.config = {
            'monitor_interval': int(os.getenv('MONITOR_INTERVAL', 60)),
            'alert_email': os.getenv('ALERT_EMAIL'),
            'discord_webhook': os.getenv('DISCORD_WEBHOOK'),
            'smtp_server': os.getenv('SMTP_SERVER'),
            'smtp_port': int(os.getenv('SMTP_PORT', 587)),
            'smtp_username': os.getenv('SMTP_USERNAME'),
            'smtp_password': os.getenv('SMTP_PASSWORD'),
        }
        
        self.status = {
            'last_check': None,
            'services': {},
            'system': {},
            'alerts': []
        }
        
        self.alert_history = []
        self.service_containers = ['mvidarr-app', 'mvidarr-database', 'mvidarr-cache']

    def check_service_health(self):
        """Check health of all MVidarr services"""
        logger.info("Checking service health...")
        
        for container_name in self.service_containers:
            try:
                container = self.docker_client.containers.get(container_name)
                
                # Basic container status
                is_running = container.status == 'running'
                
                # Health check if available
                health_status = 'unknown'
                if container.attrs.get('State', {}).get('Health'):
                    health_status = container.attrs['State']['Health']['Status']
                
                # Resource usage
                stats = container.stats(stream=False)
                cpu_percent = self._calculate_cpu_percent(stats)
                memory_usage = stats['memory_stats'].get('usage', 0)
                memory_limit = stats['memory_stats'].get('limit', 1)
                memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0
                
                self.status['services'][container_name] = {
                    'status': container.status,
                    'running': is_running,
                    'health': health_status,
                    'cpu_percent': cpu_percent,
                    'memory_percent': round(memory_percent, 1),
                    'memory_usage_mb': round(memory_usage / 1024 / 1024, 1),
                    'uptime': self._get_container_uptime(container),
                    'restart_count': container.attrs.get('RestartCount', 0)
                }
                
                # Alert if service is down
                if not is_running:
                    self._send_alert(
                        f"🔴 Service Down: {container_name}",
                        f"Container {container_name} is not running. Status: {container.status}"
                    )
                
                # Alert if high resource usage
                if cpu_percent > 90:
                    self._send_alert(
                        f"⚠️ High CPU: {container_name}",
                        f"Container {container_name} is using {cpu_percent:.1f}% CPU"
                    )
                
                if memory_percent > 90:
                    self._send_alert(
                        f"⚠️ High Memory: {container_name}",
                        f"Container {container_name} is using {memory_percent:.1f}% memory"
                    )
                    
            except docker.errors.NotFound:
                self.status['services'][container_name] = {
                    'status': 'not_found',
                    'running': False,
                    'error': 'Container not found'
                }
                self._send_alert(
                    f"❌ Container Missing: {container_name}",
                    f"Container {container_name} was not found"
                )
            except Exception as e:
                logger.error(f"Error checking {container_name}: {e}")
                self.status['services'][container_name] = {
                    'status': 'error',
                    'running': False,
                    'error': str(e)
                }

    def check_system_health(self):
        """Check overall system health"""
        try:
            # System resources
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            self.status['system'] = {
                'cpu_percent': round(cpu_percent, 1),
                'memory_percent': round(memory.percent, 1),
                'memory_available_gb': round(memory.available / 1024**3, 1),
                'disk_percent': round(disk.percent, 1),
                'disk_free_gb': round(disk.free / 1024**3, 1),
                'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None,
                'uptime': self._get_system_uptime()
            }
            
            # System alerts
            if cpu_percent > 85:
                self._send_alert("⚠️ High System CPU", f"System CPU usage at {cpu_percent:.1f}%")
            
            if memory.percent > 85:
                self._send_alert("⚠️ High System Memory", f"System memory usage at {memory.percent:.1f}%")
            
            if disk.percent > 90:
                self._send_alert("⚠️ Low Disk Space", f"Disk usage at {disk.percent:.1f}%")
                
        except Exception as e:
            logger.error(f"Error checking system health: {e}")

    def check_application_health(self):
        """Check MVidarr application health"""
        try:
            # Check if MVidarr API is responding
            response = requests.get('http://mvidarr-app:5000/health', timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                self.status['application'] = {
                    'status': 'healthy',
                    'response_time': response.elapsed.total_seconds(),
                    'details': health_data
                }
            else:
                self.status['application'] = {
                    'status': 'unhealthy',
                    'status_code': response.status_code
                }
                self._send_alert(
                    "🔴 Application Health Check Failed",
                    f"MVidarr health endpoint returned {response.status_code}"
                )
                
        except requests.exceptions.RequestException as e:
            self.status['application'] = {
                'status': 'unreachable',
                'error': str(e)
            }
            self._send_alert(
                "❌ Application Unreachable",
                f"Cannot reach MVidarr application: {e}"
            )

    def _calculate_cpu_percent(self, stats):
        """Calculate CPU percentage from Docker stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0 and cpu_delta >= 0:
                cpu_percent = (cpu_delta / system_delta) * \
                             len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
                return round(cpu_percent, 1)
        except (KeyError, ZeroDivisionError):
            pass
        return 0.0

    def _get_container_uptime(self, container):
        """Get container uptime in human readable format"""
        try:
            started_at = datetime.fromisoformat(
                container.attrs['State']['StartedAt'].replace('Z', '+00:00')
            )
            uptime = datetime.now(started_at.tzinfo) - started_at
            return str(uptime).split('.')[0]  # Remove microseconds
        except:
            return 'unknown'

    def _get_system_uptime(self):
        """Get system uptime"""
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            uptime = timedelta(seconds=int(uptime_seconds))
            return str(uptime)
        except:
            return 'unknown'

    def _send_alert(self, title, message):
        """Send alert via configured channels"""
        # Prevent duplicate alerts within 5 minutes
        alert_key = f"{title}:{message}"
        now = datetime.now()
        
        # Check for recent duplicate alerts
        for alert_time, alert_msg in self.alert_history:
            if alert_msg == alert_key and (now - alert_time).seconds < 300:
                return  # Skip duplicate alert
        
        # Add to history
        self.alert_history.append((now, alert_key))
        
        # Keep only last 50 alerts in history
        if len(self.alert_history) > 50:
            self.alert_history = self.alert_history[-50:]
        
        # Store alert
        self.status['alerts'].insert(0, {
            'timestamp': now.isoformat(),
            'title': title,
            'message': message
        })
        
        # Keep only last 20 alerts
        if len(self.status['alerts']) > 20:
            self.status['alerts'] = self.status['alerts'][:20]
        
        logger.warning(f"ALERT: {title} - {message}")
        
        # Send email alert
        if self.config['alert_email'] and self.config['smtp_server']:
            self._send_email_alert(title, message)
        
        # Send Discord alert
        if self.config['discord_webhook']:
            self._send_discord_alert(title, message)

    def _send_email_alert(self, title, message):
        """Send email alert"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['smtp_username']
            msg['To'] = self.config['alert_email']
            msg['Subject'] = f"MVidarr Alert: {title}"
            
            body = f"""
            MVidarr System Alert
            
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Alert: {title}
            Details: {message}
            
            Check your MVidarr system monitor dashboard for more information.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['smtp_username'], self.config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email alert sent: {title}")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def _send_discord_alert(self, title, message):
        """Send Discord webhook alert"""
        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": 0xff0000 if "🔴" in title or "❌" in title else 0xff9900,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {
                        "text": "MVidarr System Monitor"
                    }
                }]
            }
            
            response = requests.post(self.config['discord_webhook'], 
                                   json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Discord alert sent: {title}")
            
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")

    def run_check(self):
        """Run complete health check"""
        self.status['last_check'] = datetime.now().isoformat()
        
        self.check_service_health()
        self.check_system_health()
        self.check_application_health()
        
        logger.info("Health check completed")

# Flask web interface
app = Flask(__name__)
monitor = MVidarrMonitor()

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MVidarr System Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
               background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; 
                  box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h3 { margin-bottom: 15px; color: #333; }
        .status-good { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-error { color: #dc3545; }
        .metric { display: flex; justify-content: space-between; margin-bottom: 10px; 
                  padding: 8px; background: #f8f9fa; border-radius: 4px; }
        .progress-bar { background: #e9ecef; border-radius: 4px; height: 8px; 
                        overflow: hidden; margin-top: 5px; }
        .progress-fill { height: 100%; transition: width 0.3s; }
        .progress-good { background: #28a745; }
        .progress-warning { background: #ffc107; }
        .progress-error { background: #dc3545; }
        .alert { margin-bottom: 10px; padding: 10px; border-radius: 4px; 
                 border-left: 4px solid #dc3545; background: #f8d7da; }
        .refresh-btn { background: #007bff; color: white; border: none; 
                       padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #0056b3; }
    </style>
    <script>
        function refreshData() {
            location.reload();
        }
        setInterval(refreshData, 60000); // Auto-refresh every minute
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 MVidarr System Monitor</h1>
            <p>Last updated: {{ status.last_check }}</p>
            <button class="refresh-btn" onclick="refreshData()">Refresh Now</button>
        </div>
        
        <div class="grid">
            <!-- Services Status -->
            <div class="card">
                <h3>Services</h3>
                {% for name, service in status.services.items() %}
                <div class="metric">
                    <span>{{ name.replace('mvidarr-', '').title() }}</span>
                    <span class="{% if service.running %}status-good{% else %}status-error{% endif %}">
                        {{ "Running" if service.running else service.status.title() }}
                    </span>
                </div>
                {% if service.get('cpu_percent') is not none %}
                <div class="metric">
                    <span>CPU: {{ service.cpu_percent }}%</span>
                    <span>Memory: {{ service.memory_percent }}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill {% if service.cpu_percent > 80 %}progress-error{% elif service.cpu_percent > 60 %}progress-warning{% else %}progress-good{% endif %}" 
                         style="width: {{ service.cpu_percent }}%"></div>
                </div>
                {% endif %}
                {% endfor %}
            </div>
            
            <!-- System Status -->
            <div class="card">
                <h3>System Resources</h3>
                {% if status.system %}
                <div class="metric">
                    <span>CPU Usage</span>
                    <span>{{ status.system.cpu_percent }}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill {% if status.system.cpu_percent > 80 %}progress-error{% elif status.system.cpu_percent > 60 %}progress-warning{% else %}progress-good{% endif %}" 
                         style="width: {{ status.system.cpu_percent }}%"></div>
                </div>
                
                <div class="metric">
                    <span>Memory Usage</span>
                    <span>{{ status.system.memory_percent }}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill {% if status.system.memory_percent > 80 %}progress-error{% elif status.system.memory_percent > 60 %}progress-warning{% else %}progress-good{% endif %}" 
                         style="width: {{ status.system.memory_percent }}%"></div>
                </div>
                
                <div class="metric">
                    <span>Disk Usage</span>
                    <span>{{ status.system.disk_percent }}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill {% if status.system.disk_percent > 90 %}progress-error{% elif status.system.disk_percent > 75 %}progress-warning{% else %}progress-good{% endif %}" 
                         style="width: {{ status.system.disk_percent }}%"></div>
                </div>
                
                <div class="metric">
                    <span>System Uptime</span>
                    <span>{{ status.system.uptime }}</span>
                </div>
                {% endif %}
            </div>
            
            <!-- Application Status -->
            <div class="card">
                <h3>Application Health</h3>
                {% if status.application %}
                <div class="metric">
                    <span>Status</span>
                    <span class="{% if status.application.status == 'healthy' %}status-good{% elif status.application.status == 'unhealthy' %}status-warning{% else %}status-error{% endif %}">
                        {{ status.application.status.title() }}
                    </span>
                </div>
                {% if status.application.response_time %}
                <div class="metric">
                    <span>Response Time</span>
                    <span>{{ "%.2f"|format(status.application.response_time * 1000) }}ms</span>
                </div>
                {% endif %}
                {% endif %}
            </div>
            
            <!-- Recent Alerts -->
            <div class="card">
                <h3>Recent Alerts</h3>
                {% if status.alerts %}
                    {% for alert in status.alerts[:5] %}
                    <div class="alert">
                        <strong>{{ alert.title }}</strong><br>
                        {{ alert.message }}<br>
                        <small>{{ alert.timestamp }}</small>
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color: #28a745;">No recent alerts</p>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE, status=monitor.status)

@app.route('/api/status')
def api_status():
    return jsonify(monitor.status)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

def run_monitor():
    """Run monitoring in background"""
    # Initial check
    monitor.run_check()
    
    # Schedule regular checks
    schedule.every(monitor.config['monitor_interval']).seconds.do(monitor.run_check)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # Start monitoring in background thread
    monitor_thread = Thread(target=run_monitor, daemon=True)
    monitor_thread.start()
    
    # Start web interface
    app.run(host='0.0.0.0', port=8080, debug=False)