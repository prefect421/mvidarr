# MVidarr Deployment Guide

## Overview

This comprehensive deployment guide covers all aspects of deploying MVidarr in production environments, including Docker deployments, traditional server installations, cloud deployments, and security considerations. The guide provides step-by-step instructions, best practices, and troubleshooting procedures.

## 🚀 Deployment Options

### Deployment Methods Overview
1. **Docker Compose** (Recommended) - Complete containerized solution
2. **Docker Swarm** - Multi-node container orchestration
3. **Kubernetes** - Enterprise container orchestration
4. **Traditional Server** - Direct installation on server
5. **Cloud Platforms** - AWS, GCP, Azure deployments

### Minimum System Requirements
- **CPU**: 2 cores minimum, 4 cores recommended
- **Memory**: 4GB minimum, 8GB recommended for large libraries
- **Storage**: 20GB minimum system space + video storage
- **Network**: Stable internet connection for external APIs
- **OS**: Linux (Ubuntu 20.04+), Windows Server 2019+, macOS 10.15+

## 🐳 Docker Deployment (Recommended)

### Docker Compose Production Setup

#### Complete docker-compose.yml
```yaml
version: '3.8'

services:
  mvidarr-app:
    build: .
    container_name: mvidarr-app
    ports:
      - "5000:5000"
    environment:
      - FASTAPI_ENV=production
      - DATABASE_URL=mysql://mvidarr:${DB_PASSWORD}@mvidarr-db:3306/mvidarr
      - SECRET_KEY=${SECRET_KEY}
      - IMVDB_API_KEY=${IMVDB_API_KEY}
      - YOUTUBE_API_KEY=${YOUTUBE_API_KEY}
      - TIMEZONE=${TIMEZONE:-UTC}
    volumes:
      - /path/to/video/storage:/app/data/videos
      - /path/to/downloads:/app/data/downloads
      - /path/to/thumbnails:/app/data/thumbnails
      - /path/to/database:/app/data/database
      - /path/to/logs:/app/logs
    depends_on:
      - mvidarr-db
      - mvidarr-redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - mvidarr-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  mvidarr-db:
    image: mariadb:11.2
    container_name: mvidarr-db
    environment:
      - MARIADB_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
      - MARIADB_DATABASE=mvidarr
      - MARIADB_USER=mvidarr
      - MARIADB_PASSWORD=${DB_PASSWORD}
      - MARIADB_AUTO_UPGRADE=1
    volumes:
      - mvidarr-db-data:/var/lib/mysql
      - ./database/init:/docker-entrypoint-initdb.d:ro
    ports:
      - "3306:3306"  # Remove in production
    restart: unless-stopped
    command: >
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --innodb-buffer-pool-size=256M
      --max-connections=200
    networks:
      - mvidarr-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  mvidarr-redis:
    image: redis:7.2-alpine
    container_name: mvidarr-redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - mvidarr-redis-data:/data
    ports:
      - "6379:6379"  # Remove in production
    restart: unless-stopped
    networks:
      - mvidarr-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  mvidarr-nginx:
    image: nginx:1.25-alpine
    container_name: mvidarr-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - /path/to/video/storage:/var/www/videos:ro
    depends_on:
      - mvidarr-app
    restart: unless-stopped
    networks:
      - mvidarr-network

volumes:
  mvidarr-db-data:
    driver: local
  mvidarr-redis-data:
    driver: local

networks:
  mvidarr-network:
    driver: bridge
```

#### Environment Configuration (.env)
```bash
# Production Environment Configuration
FASTAPI_ENV=production
SECRET_KEY=your-super-secret-key-min-32-chars-long
TIMEZONE=America/New_York

# Database Configuration
DB_ROOT_PASSWORD=secure-root-password
DB_PASSWORD=secure-mvidarr-password

# Redis Configuration
REDIS_PASSWORD=secure-redis-password

# External API Keys
IMVDB_API_KEY=your-imvdb-api-key
YOUTUBE_API_KEY=your-youtube-api-key

# SSL Configuration
SSL_CERT_PATH=/etc/nginx/ssl/cert.pem
SSL_KEY_PATH=/etc/nginx/ssl/key.pem

# Optional: External Services
PLEX_SERVER_URL=http://plex-server:32400
PLEX_TOKEN=your-plex-token
```

### NGINX Configuration

#### nginx.conf
```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                   '$status $body_bytes_sent "$http_referer" '
                   '"$http_user_agent" "$http_x_forwarded_for"';
    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;

    # Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;

    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Upstream MVidarr
    upstream mvidarr {
        server mvidarr-app:5000;
        keepalive 32;
    }

    # HTTP to HTTPS Redirect
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # HTTPS Server
    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Proxy to MVidarr
        location / {
            proxy_pass http://mvidarr;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 10s;
        }

        # Static video files
        location /videos/ {
            alias /var/www/videos/;
            expires 7d;
            add_header Cache-Control "public, immutable";
            
            # Security for video files
            location ~* \.(mp4|mkv|avi|mov|wmv|flv)$ {
                # Optional: Require authentication
                # auth_request /auth;
            }
        }

        # Static assets
        location /static/ {
            proxy_pass http://mvidarr;
            expires 30d;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### Docker Deployment Commands

#### Initial Deployment
```bash
# Create deployment directory
mkdir -p /opt/mvidarr
cd /opt/mvidarr

# Download configuration files
curl -o docker-compose.yml https://raw.githubusercontent.com/prefect421/mvidarr/main/docker-compose.prod.yml
curl -o .env.example https://raw.githubusercontent.com/prefect421/mvidarr/main/.env.example

# Configure environment
cp .env.example .env
nano .env  # Edit configuration

# Create necessary directories
mkdir -p {videos,downloads,thumbnails,database,logs,nginx/ssl}
chmod 755 {videos,downloads,thumbnails,database,logs}

# Generate SSL certificates (Let's Encrypt recommended)
certbot certonly --standalone -d your-domain.com

# Start services
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f mvidarr-app
```

#### Update Deployment
```bash
# Update to latest version
docker-compose pull
docker-compose down
docker-compose up -d

# Check for issues
docker-compose logs -f mvidarr-app
```

## ☸️ Kubernetes Deployment

### Kubernetes Manifests

#### Namespace
```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mvidarr
  labels:
    name: mvidarr
```

#### ConfigMap
```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mvidarr-config
  namespace: mvidarr
data:
  FASTAPI_ENV: "production"
  TIMEZONE: "UTC"
  DATABASE_URL: "mysql://mvidarr:$(DB_PASSWORD)@mvidarr-db:3306/mvidarr"
```

#### Secret
```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: mvidarr-secrets
  namespace: mvidarr
type: Opaque
stringData:
  SECRET_KEY: "your-super-secret-key-min-32-chars-long"
  DB_PASSWORD: "secure-database-password"
  IMVDB_API_KEY: "your-imvdb-api-key"
  YOUTUBE_API_KEY: "your-youtube-api-key"
```

#### Persistent Volume
```yaml
# pv.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: mvidarr-storage
spec:
  capacity:
    storage: 500Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-storage
  local:
    path: /mnt/mvidarr-data
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - your-storage-node
```

#### Application Deployment
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mvidarr-app
  namespace: mvidarr
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mvidarr-app
  template:
    metadata:
      labels:
        app: mvidarr-app
    spec:
      containers:
      - name: mvidarr
        image: prefect421/mvidarr:latest
        ports:
        - containerPort: 5000
        env:
        - name: FASTAPI_ENV
          valueFrom:
            configMapKeyRef:
              name: mvidarr-config
              key: FASTAPI_ENV
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: mvidarr-secrets
              key: SECRET_KEY
        - name: DATABASE_URL
          valueFrom:
            configMapKeyRef:
              name: mvidarr-config
              key: DATABASE_URL
        volumeMounts:
        - name: video-storage
          mountPath: /app/data/videos
        - name: download-storage
          mountPath: /app/data/downloads
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: video-storage
        persistentVolumeClaim:
          claimName: mvidarr-videos-pvc
      - name: download-storage
        persistentVolumeClaim:
          claimName: mvidarr-downloads-pvc
```

## 🖥️ Traditional Server Deployment

### Ubuntu Server Setup

#### System Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3.10 python3.10-venv python3-pip
sudo apt install -y nginx mysql-server redis-server
sudo apt install -y git curl wget unzip
sudo apt install -y ffmpeg yt-dlp

# Create mvidarr user
sudo useradd -r -s /bin/false -m -d /opt/mvidarr mvidarr
sudo mkdir -p /opt/mvidarr/{app,data,logs}
sudo chown -R mvidarr:mvidarr /opt/mvidarr
```

#### Application Installation
```bash
# Switch to mvidarr user
sudo -u mvidarr -i

# Clone repository
cd /opt/mvidarr
git clone https://github.com/prefect421/mvidarr.git app
cd app

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements-prod.txt

# Configure application
cp .env.example .env
nano .env  # Edit configuration

# Initialize database
python -c "from src.database.connection import init_database; init_database()"

# Test application
python fastapi_app.py  # Should start successfully
```

#### Systemd Service Configuration

**Current Production Service File:**
```ini
# /etc/systemd/system/mvidarr.service
[Unit]
Description=MVidarr Enhanced - Professional Music Video Management System with Advanced Processing
Documentation=file:///home/mike/mvidarr/README.md file:///home/mike/mvidarr/MILESTONE_ROADMAP.md
After=network-online.target mysql.service mariadb.service
Wants=network-online.target
RequiresMountsFor=/home/mike/mvidarr

[Service]
Type=exec
User=mike
Group=mike
WorkingDirectory=/home/mike/mvidarr

# Create required directories and start application
ExecStartPre=/usr/bin/mkdir -p /home/mike/mvidarr/data/logs /home/mike/mvidarr/data/downloads /home/mike/mvidarr/data/thumbnails /home/mike/mvidarr/data/cache /home/mike/mvidarr/data/backups /home/mike/mvidarr/data/processing
ExecStart=/home/mike/mvidarr/venv/bin/python /home/mike/mvidarr/fastapi_app.py
ExecReload=/bin/kill -HUP $MAINPID

# Enhanced restart and failure handling
Restart=always
RestartSec=20
StartLimitInterval=600
StartLimitBurst=3
TimeoutStartSec=120
TimeoutStopSec=60
KillMode=mixed
KillSignal=SIGTERM

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mvidarr

# Environment variables for FastAPI Application
Environment=PATH=/home/mike/mvidarr/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/home/mike/mvidarr
Environment=FLASK_ENV=production
Environment=FASTAPI_ENV=production
Environment=PYTHONUNBUFFERED=1
Environment=ASYNC_MODE=enabled
Environment=PHASE_2_ADVANCED_PROCESSING=enabled
Environment=FFMPEG_ADVANCED_TASKS=enabled
Environment=CONCURRENT_VIDEO_PROCESSING=enabled
Environment=QUALITY_ANALYSIS_ENABLED=enabled
Environment=BULK_OPERATIONS_ENABLED=enabled

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes

# Enhanced resource limits for advanced processing
LimitNOFILE=131072
LimitNPROC=8192

[Install]
WantedBy=multi-user.target
```

**Installation Commands:**
```bash
# Copy and install the service
sudo cp /home/mike/mvidarr/mvidarr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mvidarr.service
sudo systemctl start mvidarr.service
```

#### Service Management
```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable mvidarr
sudo systemctl start mvidarr

# Check status
sudo systemctl status mvidarr
sudo journalctl -u mvidarr -f

# Service management
sudo systemctl restart mvidarr
sudo systemctl stop mvidarr
sudo systemctl reload mvidarr
```

### Database Setup (MySQL/MariaDB)

#### Database Configuration
```bash
# Secure MySQL installation
sudo mysql_secure_installation

# Create database and user
sudo mysql -u root -p
```

```sql
-- Database setup
CREATE DATABASE mvidarr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mvidarr'@'localhost' IDENTIFIED BY 'secure_password_here';
GRANT ALL PRIVILEGES ON mvidarr.* TO 'mvidarr'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

#### MySQL Optimization
```ini
# /etc/mysql/mysql.conf.d/mvidarr.cnf
[mysqld]
# Connection settings
max_connections = 200
connect_timeout = 60
wait_timeout = 600
interactive_timeout = 600

# Buffer settings
innodb_buffer_pool_size = 512M
innodb_log_file_size = 128M
innodb_log_buffer_size = 16M
innodb_flush_log_at_trx_commit = 2

# Query cache
query_cache_type = 1
query_cache_size = 64M
query_cache_limit = 2M

# Character set
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# Logging
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mysql-slow.log
long_query_time = 2
```

### NGINX Configuration (Traditional)

#### Site Configuration
```nginx
# /etc/nginx/sites-available/mvidarr
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/mvidarr.access.log;
    error_log /var/log/nginx/mvidarr.error.log;

    # Main proxy
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }

    # Static files
    location /static/ {
        alias /opt/mvidarr/app/frontend/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Video files
    location /videos/ {
        alias /opt/mvidarr/data/videos/;
        expires 7d;
        add_header Cache-Control "public, immutable";
        
        # Optional authentication
        # auth_basic "Restricted Content";
        # auth_basic_user_file /etc/nginx/.htpasswd;
    }

    # File upload size
    client_max_body_size 100M;
}
```

#### Enable Site
```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/mvidarr /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## ☁️ Cloud Deployment

### AWS Deployment

#### EC2 Instance Setup
```bash
# Launch EC2 instance (Ubuntu 22.04, t3.medium or larger)
# Configure Security Group:
# - HTTP (80) from anywhere
# - HTTPS (443) from anywhere
# - SSH (22) from your IP

# Connect and setup
ssh -i your-key.pem ubuntu@your-ec2-ip

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Deploy MVidarr
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
cp docker-compose.prod.yml docker-compose.yml
cp .env.example .env
nano .env  # Configure

# Start services
docker-compose up -d
```

#### RDS Database Setup
```bash
# Create RDS MySQL instance
aws rds create-db-instance \
    --db-instance-identifier mvidarr-db \
    --db-instance-class db.t3.micro \
    --engine mysql \
    --engine-version 8.0 \
    --master-username mvidarr \
    --master-user-password SecurePassword123 \
    --allocated-storage 20 \
    --storage-type gp2 \
    --vpc-security-group-ids sg-12345678 \
    --db-subnet-group-name default \
    --backup-retention-period 7 \
    --multi-az \
    --storage-encrypted

# Update .env with RDS endpoint
DATABASE_URL=mysql://mvidarr:SecurePassword123@mvidarr-db.xyz.rds.amazonaws.com:3306/mvidarr
```

### Google Cloud Platform Deployment

#### Cloud Run Deployment
```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/mvidarr:$COMMIT_SHA', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/mvidarr:$COMMIT_SHA']
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'mvidarr'
      - '--image'
      - 'gcr.io/$PROJECT_ID/mvidarr:$COMMIT_SHA'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'
      - '--memory'
      - '2Gi'
      - '--cpu'
      - '2'
      - '--max-instances'
      - '10'
```

## 🔧 Production Configuration

### Environment Variables
```bash
# Core Application Settings
FASTAPI_ENV=production
SECRET_KEY=your-super-secret-key-minimum-32-characters
DEBUG=false
TESTING=false

# Database Configuration
DATABASE_URL=mysql://user:password@host:port/database
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
DB_POOL_TIMEOUT=30

# Redis Configuration (for caching/sessions)
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=secure-redis-password

# External API Keys
IMVDB_API_KEY=your-imvdb-api-key
YOUTUBE_API_KEY=your-youtube-api-key

# File Paths
DOWNLOADS_PATH=/path/to/downloads
VIDEOS_PATH=/path/to/organized/videos
THUMBNAILS_PATH=/path/to/thumbnails
LOG_PATH=/path/to/logs

# Security Settings
REQUIRE_AUTHENTICATION=true
SESSION_TIMEOUT=3600
ENABLE_TWO_FACTOR=true
MAX_LOGIN_ATTEMPTS=5
ACCOUNT_LOCKOUT_DURATION=900

# Performance Settings
ENABLE_CACHING=true
CACHE_TIMEOUT=300
MAX_CONCURRENT_DOWNLOADS=3
MAX_WORKERS=4

# Monitoring and Logging
LOG_LEVEL=INFO
ENABLE_METRICS=true
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project

# Backup Configuration
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
BACKUP_RETENTION_DAYS=30
```

### Security Hardening

#### SSL/TLS Configuration
```bash
# Generate Let's Encrypt SSL certificates
sudo certbot certonly --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

#### Firewall Configuration
```bash
# UFW Firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Check status
sudo ufw status verbose
```

#### Security Headers
```nginx
# Additional security headers in nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
```

## 📊 Monitoring and Maintenance

### Health Monitoring

#### Health Check Endpoint
```python
# Application health check
@app.route('/health')
def health_check():
    """Comprehensive health check endpoint."""
    checks = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': get_version(),
        'database': check_database_connection(),
        'redis': check_redis_connection(),
        'external_apis': check_external_apis(),
        'disk_space': check_disk_space(),
        'memory_usage': get_memory_usage()
    }
    
    # Determine overall health
    if any(not check for check in checks.values() if isinstance(check, bool)):
        checks['status'] = 'unhealthy'
        return jsonify(checks), 503
    
    return jsonify(checks), 200
```

#### Monitoring Script
```bash
#!/bin/bash
# monitor_mvidarr.sh

LOG_FILE="/var/log/mvidarr/monitoring.log"
HEALTH_URL="http://localhost:5000/health"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> $LOG_FILE
}

# Check service health
check_health() {
    local response=$(curl -s -w "%{http_code}" -o /tmp/health_response $HEALTH_URL)
    
    if [ "$response" = "200" ]; then
        log "INFO: Health check passed"
        return 0
    else
        log "ERROR: Health check failed with code $response"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    local usage=$(df /opt/mvidarr | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$usage" -gt 90 ]; then
        log "WARNING: Disk usage is ${usage}%"
        return 1
    fi
    
    return 0
}

# Check memory usage
check_memory() {
    local memory_usage=$(free | awk 'NR==2{printf "%.2f", $3*100/$2 }')
    local memory_int=${memory_usage%.*}
    
    if [ "$memory_int" -gt 85 ]; then
        log "WARNING: Memory usage is ${memory_usage}%"
        return 1
    fi
    
    return 0
}

# Main monitoring function
main() {
    log "Starting health check"
    
    if ! check_health; then
        log "ERROR: Restarting MVidarr service"
        systemctl restart mvidarr
        sleep 30
        
        if ! check_health; then
            log "CRITICAL: Service restart failed"
            # Send alert (email, webhook, etc.)
        fi
    fi
    
    check_disk_space
    check_memory
    
    log "Health check completed"
}

main
```

#### Cron Jobs for Monitoring
```bash
# Add to crontab
sudo crontab -e

# Health check every 5 minutes
*/5 * * * * /opt/mvidarr/scripts/monitor_mvidarr.sh

# Log rotation daily
0 0 * * * /usr/sbin/logrotate /etc/logrotate.d/mvidarr

# Database optimization weekly
0 2 * * 0 /opt/mvidarr/scripts/optimize_database.sh

# Cleanup old downloads monthly
0 3 1 * * /opt/mvidarr/scripts/cleanup_downloads.sh
```

### Backup and Recovery

#### Database Backup Script
```bash
#!/bin/bash
# backup_database.sh

BACKUP_DIR="/opt/mvidarr/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="mvidarr"
DB_USER="mvidarr"
DB_PASS="your_password"

mkdir -p $BACKUP_DIR

# Create backup
mysqldump -u $DB_USER -p$DB_PASS $DB_NAME > $BACKUP_DIR/mvidarr_$DATE.sql

# Compress backup
gzip $BACKUP_DIR/mvidarr_$DATE.sql

# Remove backups older than 30 days
find $BACKUP_DIR -name "mvidarr_*.sql.gz" -mtime +30 -delete

# Log backup completion
echo "$(date): Database backup completed" >> /var/log/mvidarr/backup.log
```

#### System Backup
```bash
#!/bin/bash
# full_backup.sh

BACKUP_DIR="/mnt/backups/mvidarr"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directories
mkdir -p $BACKUP_DIR/$DATE/{database,config,data}

# Backup database
mysqldump -u mvidarr -p mvidarr | gzip > $BACKUP_DIR/$DATE/database/mvidarr.sql.gz

# Backup configuration
cp -r /opt/mvidarr/app/.env $BACKUP_DIR/$DATE/config/
cp -r /etc/nginx/sites-available/mvidarr $BACKUP_DIR/$DATE/config/
cp -r /etc/systemd/system/mvidarr.service $BACKUP_DIR/$DATE/config/

# Backup essential data (thumbnails, small files)
rsync -av --exclude='*.mp4' --exclude='*.mkv' /opt/mvidarr/data/ $BACKUP_DIR/$DATE/data/

# Create manifest
echo "Backup created: $(date)" > $BACKUP_DIR/$DATE/manifest.txt
echo "Database size: $(du -h $BACKUP_DIR/$DATE/database/)" >> $BACKUP_DIR/$DATE/manifest.txt
echo "Config size: $(du -h $BACKUP_DIR/$DATE/config/)" >> $BACKUP_DIR/$DATE/manifest.txt
echo "Data size: $(du -h $BACKUP_DIR/$DATE/data/)" >> $BACKUP_DIR/$DATE/manifest.txt

# Cleanup old backups (keep 7 days)
find $BACKUP_DIR -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```

## 🚨 Troubleshooting

### Common Deployment Issues

#### Application Won't Start
```bash
# Check service status
sudo systemctl status mvidarr

# Check logs
sudo journalctl -u mvidarr -n 50
tail -f /opt/mvidarr/logs/mvidarr.log

# Common fixes
# 1. Database connection issues
mysql -u mvidarr -p -h localhost mvidarr

# 2. Permission issues
sudo chown -R mvidarr:mvidarr /opt/mvidarr
sudo chmod -R 755 /opt/mvidarr/data

# 3. Port conflicts
sudo netstat -tulpn | grep :5000
sudo lsof -i :5000
```

#### Database Connection Issues
```bash
# Test database connection
mysql -u mvidarr -p -h localhost mvidarr

# Check MySQL status
sudo systemctl status mysql
sudo journalctl -u mysql -n 50

# Reset MySQL password
sudo mysql -u root -p
ALTER USER 'mvidarr'@'localhost' IDENTIFIED BY 'new_password';
FLUSH PRIVILEGES;
```

#### NGINX Issues
```bash
# Test NGINX configuration
sudo nginx -t

# Check NGINX logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/mvidarr.error.log

# Reload configuration
sudo systemctl reload nginx
```

### Performance Issues

#### High Memory Usage
```bash
# Monitor memory usage
htop
ps aux --sort=-%mem | head

# Restart service if needed
sudo systemctl restart mvidarr

# Check for memory leaks
valgrind --tool=memcheck --leak-check=full python fastapi_app.py
```

#### Database Performance
```sql
-- Check slow queries
SELECT * FROM information_schema.PROCESSLIST WHERE Time > 5;

-- Optimize tables
OPTIMIZE TABLE artists, videos, downloads, settings;

-- Update statistics
ANALYZE TABLE artists, videos, downloads, settings;
```

## 📋 Deployment Checklist

### Pre-deployment
- [ ] System requirements met
- [ ] SSL certificates obtained
- [ ] Database configured and tested
- [ ] Environment variables configured
- [ ] External API keys configured
- [ ] Storage paths created with proper permissions
- [ ] Firewall configured
- [ ] Backup strategy implemented

### Deployment
- [ ] Application deployed successfully
- [ ] Service starts automatically
- [ ] Health check endpoint responds
- [ ] Database connection working
- [ ] External APIs accessible
- [ ] Static files served correctly
- [ ] SSL/HTTPS working
- [ ] Authentication functioning

### Post-deployment
- [ ] Monitoring configured
- [ ] Log rotation setup
- [ ] Backup tested
- [ ] Performance baseline established
- [ ] Documentation updated
- [ ] Team trained on maintenance procedures

## 🔗 Related Documentation

- **Configuration**: `CONFIGURATION_GUIDE.md`
- **Security**: `SECURITY_AUDIT.md`
- **Monitoring**: `MONITORING.md`
- **Performance**: `PERFORMANCE_OPTIMIZATION.md`
- **Troubleshooting**: `TROUBLESHOOTING.md`

This comprehensive deployment guide ensures successful MVidarr deployment in any production environment with proper security, monitoring, and maintenance procedures.