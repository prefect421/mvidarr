# 🏠 MVidarr Self-Hosted Production Guide

Complete guide for deploying MVidarr in a self-hosted production environment with monitoring, backups, and maintenance.

## 🚀 Quick Start

**Deploy with one command:**
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
./scripts/deploy-selfhosted.sh --quick
```

**Access your installation:**
- 📱 **Main App**: http://localhost:5000
- 📊 **System Monitor**: http://localhost:8080
- 📋 **API Health**: http://localhost:5000/health/production

---

## 📋 Prerequisites

### System Requirements
- **CPU**: 2+ cores (4+ recommended)
- **RAM**: 4GB minimum (8GB+ recommended)  
- **Storage**: 20GB+ free space (more for media)
- **OS**: Linux (Ubuntu/Debian/CentOS), macOS, or Windows with WSL2

### Software Requirements
- **Docker**: 20.10+ with Docker Compose
- **Git**: For cloning repository
- **Ports**: 5000, 8080, 80, 443 (optional)

---

## 🛠️ Installation Methods

### Method 1: Automated Setup (Recommended)
```bash
# Clone repository
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr

# Quick setup with defaults
./scripts/deploy-selfhosted.sh --quick

# Interactive setup with customization
./scripts/deploy-selfhosted.sh

# Enable additional features
./scripts/deploy-selfhosted.sh --enable-proxy --enable-auto-update
```

### Method 2: Manual Docker Compose
```bash
# Copy environment template
cp .env.selfhosted.example .env
nano .env  # Edit configuration

# Start services
docker-compose -f docker-compose.selfhosted.yml up -d

# Check status
docker-compose -f docker-compose.selfhosted.yml ps
```

---

## ⚙️ Configuration

### Environment Variables (.env)
```bash
# Database passwords (auto-generated)
MYSQL_ROOT_PASSWORD=your-secure-root-password
MYSQL_PASSWORD=your-secure-mvidarr-password
REDIS_PASSWORD=your-secure-redis-password

# Email alerts (optional)
ALERT_EMAIL=your-email@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Discord alerts (optional)  
DISCORD_WEBHOOK=https://discord.com/api/webhooks/your/webhook

# Backup settings
BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM
BACKUP_RETENTION_DAYS=7

# Features
MONITORING_ENABLED=true
BACKUP_ENABLED=true
```

### Service Profiles
Enable optional services by adding profiles:

```bash
# With monitoring + backup
docker-compose -f docker-compose.selfhosted.yml --profile monitor --profile backup up -d

# With nginx proxy for SSL
docker-compose -f docker-compose.selfhosted.yml --profile proxy up -d

# With automatic updates
docker-compose -f docker-compose.selfhosted.yml --profile updater up -d
```

---

## 📊 Monitoring & Health Checks

### Built-in Monitoring Dashboard
- **URL**: http://localhost:8080
- **Features**: System metrics, service status, recent alerts
- **Auto-refresh**: Updates every 60 seconds

### Health Check Endpoints
| Endpoint | Purpose | Status Codes |
|----------|---------|--------------|
| `/health` | Basic health check | 200 = Healthy |
| `/health/production` | Comprehensive status | 200 = All systems go |
| `/health/system` | System resource metrics | 200 = OK |
| `/health/readiness` | Load balancer ready | 200 = Ready |
| `/health/liveness` | Container health | 200 = Alive |

### Alerting
**Email Alerts**: Configure SMTP settings in `.env`
**Discord Alerts**: Add webhook URL to `DISCORD_WEBHOOK`

**Alert Conditions**:
- Service failures
- High CPU/memory usage (>90%)
- Low disk space (<10GB)
- Database connection issues
- Backup failures

---

## 💾 Backup & Recovery

### Automated Backups
Backups run daily at 2 AM by default. Includes:
- **Database**: Complete MySQL dump
- **Media Files**: All videos and thumbnails  
- **Configuration**: Docker Compose and environment files
- **Logs**: Recent application logs

### Manual Backup
```bash
# Create backup now
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./backup.sh

# List available backups
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh --list

# Backup report
cat data/backups/backup_report.json
```

### Restore Process
```bash
# List backups
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh -l

# Full restore
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh mvidarr_backup_20241201_120000

# Database only
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh -d mvidarr_backup_20241201_120000

# Media files only
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh -m mvidarr_backup_20241201_120000
```

---

## 🔒 Security & SSL

### Basic Security
- All containers run as non-root users
- Database and Redis require authentication
- Rate limiting on API endpoints
- Security headers via nginx proxy

### SSL Certificate Setup
```bash
# Enable nginx proxy
docker-compose -f docker-compose.selfhosted.yml --profile proxy up -d

# Generate self-signed certificate (development)
mkdir -p data/ssl
openssl req -x509 -newkey rsa:4096 -keyout data/ssl/key.pem -out data/ssl/cert.pem -days 365 -nodes

# For production, use Let's Encrypt with certbot
certbot --nginx -d yourdomain.com
```

### Firewall Configuration
```bash
# Ubuntu/Debian
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw allow 5000  # MVidarr (if no proxy)
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --add-service=http --permanent
sudo firewall-cmd --add-service=https --permanent
sudo firewall-cmd --add-port=5000/tcp --permanent
sudo firewall-cmd --reload
```

---

## 🛠️ Maintenance

### Daily Operations
```bash
# Check service status
docker-compose -f docker-compose.selfhosted.yml ps

# View logs
docker-compose -f docker-compose.selfhosted.yml logs -f mvidarr

# Restart services
docker-compose -f docker-compose.selfhosted.yml restart

# Update images and restart
./scripts/deploy-selfhosted.sh --update
```

### System Updates
```bash
# Update MVidarr to latest version
git pull origin main
docker-compose -f docker-compose.selfhosted.yml build
docker-compose -f docker-compose.selfhosted.yml up -d

# Update base images
docker-compose -f docker-compose.selfhosted.yml pull
docker-compose -f docker-compose.selfhosted.yml up -d
```

### Log Management
```bash
# View recent logs
docker-compose -f docker-compose.selfhosted.yml logs --tail=100 -f

# Clean old logs
docker system prune -f

# Check disk usage
du -sh data/logs/
```

### Database Maintenance
```bash
# Access database
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-db mysql -u root -p mvidarr

# Database backup
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-db mysqldump -u root -p mvidarr > backup.sql

# Optimize database
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-db mysqlcheck -u root -p --optimize mvidarr
```

---

## 🚨 Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check service logs
docker-compose -f docker-compose.selfhosted.yml logs mvidarr

# Check resource usage
docker stats

# Restart service
docker-compose -f docker-compose.selfhosted.yml restart mvidarr
```

#### Database Connection Issues
```bash
# Check database status
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-db mysql -u root -p -e "SELECT 1"

# Reset database password
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-db mysql -u root -p -e "ALTER USER 'mvidarr'@'%' IDENTIFIED BY 'new_password';"
```

#### High Resource Usage
```bash
# Check system resources
http://localhost:8080  # Monitoring dashboard
curl http://localhost:5000/health/system  # System metrics API

# Reduce workers if needed
echo "WORKERS=2" >> .env
docker-compose -f docker-compose.selfhosted.yml restart mvidarr
```

#### Backup Failures
```bash
# Check backup logs
docker-compose -f docker-compose.selfhosted.yml logs mvidarr-backup

# Test backup manually
docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./backup.sh

# Check backup permissions
ls -la data/backups/
```

### Getting Help

1. **Check logs first**: `docker-compose logs`
2. **Health endpoints**: Visit `/health/production`
3. **System monitor**: Check http://localhost:8080
4. **Community**: GitHub Issues and Discussions
5. **Documentation**: See `/docs` directory

---

## 🎯 Performance Optimization

### Resource Tuning
```bash
# Adjust worker processes
WORKERS=4  # Set in .env

# Database optimization
# Edit docker/mariadb/my.cnf

# Redis memory limit
# Set in docker-compose.selfhosted.yml
```

### Monitoring Performance
- **System Monitor**: Real-time resource usage
- **Health API**: `/health/system` for programmatic access
- **Application Metrics**: `/health/production` for comprehensive status

---

## 📈 Scaling

### Single Server Scaling
- Increase worker processes (`WORKERS` in `.env`)
- Add more CPU/RAM to server
- Use SSD storage for better performance
- Enable nginx proxy for better static file serving

### Multi-Server Setup
- Use external database (MySQL/MariaDB)
- Use external Redis cluster
- Use shared storage (NFS/GlusterFS) for media files
- Deploy multiple MVidarr instances behind load balancer

---

## 🎉 Success!

Your MVidarr self-hosted production deployment is now complete! 

**Next Steps:**
1. 📱 Visit http://localhost:5000 to access MVidarr
2. 📊 Check http://localhost:8080 for system monitoring  
3. ⚙️ Complete the setup wizard
4. 📁 Configure your media directories
5. 💾 Verify backups are working
6. 📧 Test alert notifications

**Happy Self-Hosting! 🏠**