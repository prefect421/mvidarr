# MVidarr System Monitoring Guide

## Overview

This guide provides comprehensive monitoring procedures for MVidarr deployments, covering system health, performance tracking, resource usage, and proactive maintenance. These procedures help ensure optimal performance and early detection of issues.

## 🖥️ System Health Monitoring

### Container Status (Docker Deployments)

#### Check Container Health
```bash
# Check if MVidarr container is running
docker ps | grep mvidarr

# Inspect container health
docker inspect mvidarr-app --format='{{.State.Health.Status}}'

# View container logs (last 100 lines)
docker logs --tail 100 mvidarr-app

# Follow live logs
docker logs -f mvidarr-app
```

#### Container Resource Usage
```bash
# Real-time resource usage
docker stats mvidarr-app

# Container resource limits and usage
docker inspect mvidarr-app | grep -A 10 -B 5 "Memory\|Cpu"
```

### Application Health Checks

#### Service Status
```bash
# Check if MVidarr web interface is accessible
curl -f http://localhost:5001/health || echo "Service unavailable"

# Check API endpoint responsiveness
curl -f http://localhost:5001/api/videos?limit=1 || echo "API unavailable"

# Check database connectivity
curl -f http://localhost:5001/api/settings || echo "Database connection failed"
```

#### Performance Monitoring
```bash
# Get API performance summary
curl http://localhost:5001/api/performance/summary

# Check for slow endpoints (>500ms)
curl "http://localhost:5001/api/performance/slow?threshold=500"
```

## 💾 Storage and Disk Space Monitoring

### Disk Space Monitoring

#### Check Available Space
```bash
# Check disk space for video storage
df -h /path/to/video/storage

# Check database storage
df -h /path/to/database

# Check Docker volume usage (if using Docker)
docker system df
```

#### Video Library Size Tracking
```bash
# Monitor video library growth
du -sh /path/to/video/library

# Count files by extension
find /path/to/video/library -name "*.mp4" | wc -l
find /path/to/video/library -name "*.mkv" | wc -l

# Largest video files (potential space recovery)
find /path/to/video/library -type f -exec du -h {} + | sort -rh | head -20
```

### Database Monitoring

#### Database Size and Growth
```bash
# Database size (MariaDB/MySQL - mvidarr does not use SQLite)
mysql -u mvidarr -p -e "SELECT table_schema AS db, ROUND(SUM(data_length+index_length)/1024/1024,1) AS size_mb FROM information_schema.tables WHERE table_schema='mvidarr' GROUP BY table_schema;"
```

#### Database Performance
```bash
# Check table status/integrity
mysql -u mvidarr -p mvidarr -e "CHECK TABLE artists, videos, downloads, settings;"

# Database statistics
mysql -u mvidarr -p mvidarr -e "SHOW TABLE STATUS;"
```

## 📊 Performance Monitoring

### CPU and Memory Usage

#### System Resource Monitoring
```bash
# Overall system resources
htop
# or
top -p $(pgrep -f mvidarr)

# Memory usage breakdown
ps aux | grep mvidarr
free -h

# CPU usage over time
sar -u 1 5  # 5 samples, 1 second intervals
```

#### Application-Specific Monitoring
```bash
# Python process memory usage
ps -o pid,ppid,cmd,%mem,%cpu -p $(pgrep -f mvidarr)

# Docker container resource limits
docker stats mvidarr-app --no-stream
```

### Network and I/O Monitoring

#### Network Activity
```bash
# Network connections
netstat -tulpn | grep 5001
ss -tulpn | grep 5001

# Network I/O for container
docker exec mvidarr-app iftop  # if available
```

#### Disk I/O Monitoring
```bash
# Disk I/O activity
iotop -o
iostat -x 1 5

# Check for high I/O processes
iotop -a -o -d 1
```

## 🔍 Log Analysis and Monitoring

### Application Logs

#### Log Locations
```bash
# Docker deployment logs
docker logs mvidarr-app > /tmp/mvidarr-logs.txt

# Local deployment logs (typical locations)
tail -f /var/log/mvidarr/app.log
tail -f ~/.local/share/mvidarr/logs/app.log
```

#### Log Analysis Commands
```bash
# Error analysis
grep -i error /path/to/mvidarr.log | tail -20

# Performance warnings
grep -i "slow\|performance" /path/to/mvidarr.log

# Download failures
grep -i "download.*fail\|failed.*download" /path/to/mvidarr.log

# Database issues
grep -i "database\|sqlite" /path/to/mvidarr.log | grep -i error
```

#### Log Rotation and Cleanup
```bash
# Implement log rotation (cron job example)
# Add to crontab: 0 2 * * 0 /usr/bin/find /path/to/logs -name "*.log" -mtime +30 -delete

# Manual log cleanup
find /path/to/logs -name "*.log" -mtime +30 -delete
```

## 📈 Automated Monitoring Scripts

### System Health Check Script

Create `/usr/local/bin/mvidarr-health-check.sh`:
```bash
#!/bin/bash

# MVidarr Health Check Script
LOGFILE="/var/log/mvidarr-health.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting MVidarr health check" >> $LOGFILE

# Check container status
if docker ps | grep -q mvidarr-app; then
    echo "[$TIMESTAMP] ✅ Container running" >> $LOGFILE
else
    echo "[$TIMESTAMP] ❌ Container not running" >> $LOGFILE
    exit 1
fi

# Check web interface
if curl -f -s http://localhost:5001/health > /dev/null; then
    echo "[$TIMESTAMP] ✅ Web interface responding" >> $LOGFILE
else
    echo "[$TIMESTAMP] ❌ Web interface not responding" >> $LOGFILE
fi

# Check disk space (warn if >80% full)
DISK_USAGE=$(df /path/to/video/storage | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "[$TIMESTAMP] ⚠️  Disk usage high: ${DISK_USAGE}%" >> $LOGFILE
else
    echo "[$TIMESTAMP] ✅ Disk usage OK: ${DISK_USAGE}%" >> $LOGFILE
fi

echo "[$TIMESTAMP] Health check completed" >> $LOGFILE
```

### Performance Monitoring Script

Create `/usr/local/bin/mvidarr-perf-monitor.sh`:
```bash
#!/bin/bash

# MVidarr Performance Monitoring Script
LOGFILE="/var/log/mvidarr-performance.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log system resources
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
DISK_USAGE=$(df /path/to/video/storage | tail -1 | awk '{print $5}')

echo "[$TIMESTAMP] CPU: ${CPU_USAGE}%, Memory: ${MEM_USAGE}%, Disk: ${DISK_USAGE}" >> $LOGFILE

# Check API performance
API_RESPONSE=$(curl -s -w "%{time_total}" -o /dev/null http://localhost:5001/api/videos?limit=1)
echo "[$TIMESTAMP] API Response Time: ${API_RESPONSE}s" >> $LOGFILE
```

### Automated Setup

#### Cron Job Configuration
```bash
# Add to crontab (crontab -e)

# Health check every 5 minutes
*/5 * * * * /usr/local/bin/mvidarr-health-check.sh

# Performance monitoring every 15 minutes
*/15 * * * * /usr/local/bin/mvidarr-perf-monitor.sh

# Daily log rotation
0 2 * * * find /var/log/mvidarr* -mtime +7 -delete

# Weekly disk usage report
0 9 * * 1 df -h /path/to/video/storage | mail -s "MVidarr Disk Usage Report" admin@domain.com
```

## 🚨 Alert and Notification Setup

### Email Alerts

#### Configure System Alerts
```bash
# Install mail utility (if not present)
sudo apt-get install mailutils  # Ubuntu/Debian
sudo yum install mailx          # CentOS/RHEL

# Test email functionality
echo "MVidarr monitoring test" | mail -s "Test Alert" admin@domain.com
```

#### Critical Alert Script
Create `/usr/local/bin/mvidarr-alert.sh`:
```bash
#!/bin/bash

ALERT_EMAIL="admin@domain.com"
SERVICE_NAME="MVidarr"

# Check if service is down
if ! curl -f -s http://localhost:5001/health > /dev/null; then
    echo "CRITICAL: $SERVICE_NAME is not responding" | mail -s "$SERVICE_NAME DOWN" $ALERT_EMAIL
fi

# Check disk space (alert if >90% full)
DISK_USAGE=$(df /path/to/video/storage | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
    echo "WARNING: Disk usage is ${DISK_USAGE}% - immediate action required" | mail -s "$SERVICE_NAME Disk Full" $ALERT_EMAIL
fi
```

## 📋 Monitoring Checklist

### Daily Monitoring Tasks
- [ ] Check container/service status
- [ ] Review error logs for new issues
- [ ] Monitor disk space usage
- [ ] Verify backup completion
- [ ] Check API response times

### Weekly Monitoring Tasks
- [ ] Analyze performance trends
- [ ] Review and rotate logs
- [ ] Check database integrity
- [ ] Update system health dashboard
- [ ] Verify monitoring scripts functionality

### Monthly Monitoring Tasks
- [ ] Analyze storage growth patterns
- [ ] Review and optimize performance
- [ ] Update monitoring thresholds
- [ ] Test backup/restore procedures
- [ ] Security and access review

## 🔧 Troubleshooting Common Issues

### High Memory Usage
```bash
# Identify memory-consuming processes
ps aux --sort=-%mem | head

# Check for memory leaks
valgrind --tool=memcheck --leak-check=yes python app.py  # Development only
```

### Slow Performance
```bash
# Check I/O wait
iostat -x 1 5

# Analyze slow queries (if applicable)
curl "http://localhost:5001/api/performance/slow?threshold=1000"

# Check network latency
ping -c 10 api.imvdb.com
```

### High Disk Usage
```bash
# Find large files
find /path/to/video/storage -type f -size +1G -exec ls -lh {} \;

# Analyze directory sizes
du -sh /path/to/video/storage/* | sort -rh

# Check for duplicate files
fdupes -r /path/to/video/storage
```

## 📊 Performance Baselines

### Expected Response Times
- **Main page load**: < 2 seconds
- **Video listing API**: < 500ms
- **Search operations**: < 1 second
- **Video download start**: < 5 seconds

### Resource Usage Guidelines
- **Memory usage**: < 1GB for typical libraries
- **CPU usage**: < 20% during normal operation
- **Disk I/O**: < 100MB/s during active downloads

### Storage Planning
- **Average video size**: 50-150MB
- **Database growth**: ~10MB per 1000 videos
- **Thumbnail storage**: ~5KB per video

## 🔄 Maintenance Schedule

### Automated Maintenance
- **Log rotation**: Weekly
- **Database vacuum**: Monthly
- **Temporary file cleanup**: Daily
- **Performance statistics**: Real-time

### Manual Maintenance
- **System updates**: Monthly
- **Backup verification**: Weekly  
- **Performance review**: Monthly
- **Security audit**: Quarterly

---

## Additional Resources

- **Performance Monitoring**: See `PERFORMANCE_MONITORING.md`
- **Docker Troubleshooting**: See `TROUBLESHOOTING_DOCKER.md`
- **System Architecture**: See `ARCHITECTURE.md`
- **Installation Guide**: See `installation.md`

This monitoring guide ensures optimal MVidarr performance and early issue detection through comprehensive system observation and proactive maintenance procedures.