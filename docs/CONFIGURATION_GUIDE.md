# MVidarr Configuration Guide

## Overview

This guide provides comprehensive instructions for configuring MVidarr, including settings management, API integrations, security configuration, and optimization options. MVidarr uses a flexible database-driven configuration system with web UI management and environment variable support.

## 🏗️ Configuration Architecture

### Configuration Hierarchy
1. **Database Settings** (Primary) - Managed via web UI, stored in database
2. **Environment Variables** (Fallback) - Used when database is unavailable  
3. **Default Values** - Built-in application defaults

### Settings Management
- **Web Interface**: `Settings` page with tabbed organization
- **API Access**: RESTful endpoints for programmatic access
- **Caching System**: In-memory cache with automatic invalidation
- **Dynamic Reloading**: Services automatically reload when settings change

## 🔧 Core Application Settings

### General Settings

#### Basic Configuration
| Setting | Default | Description |
|---------|---------|-------------|
| `app_port` | 5000 | Port for web interface |
| `app_host` | 0.0.0.0 | Host binding address |
| `debug_mode` | false | Enable debug logging |
| `secret_key` | auto-generated | Session signing secret |
| `language` | en | Application language |
| `ui_theme` | default | User interface theme |

**Configuration Example:**
```bash
# Environment variables
export PORT=5001
export DEBUG=false
export SECRET_KEY="your-secure-random-key"
```

### File System Paths

#### Directory Configuration
| Setting | Default | Description |
|---------|---------|-------------|
| `downloads_path` | data/downloads | Temporary downloads location |
| `music_videos_path` | data/musicvideos | Organized video library |
| `thumbnails_path` | data/thumbnails | Thumbnail cache directory |

**Best Practices:**
```bash
# Recommended directory structure
/mvidarr-data/
├── downloads/          # Temporary processing
├── musicvideos/       # Final organized library
├── thumbnails/        # Generated thumbnails
└── logs/               # Application logs
```

MVidarr requires MariaDB/MySQL — there's no SQLite database file to place here.

**Permissions Setup:**
```bash
# Set ownership to match the container/service user, then grant group write
# access where the app needs it - avoid 777, it grants write to every user
sudo chown -R $(id -u):$(id -g) /path/to/mvidarr-data
chmod -R 755 /path/to/mvidarr-data
chmod -R 775 /path/to/mvidarr-data/downloads  # needs write access
```

## 🔐 Authentication & Security

### Simple Authentication

#### Enable Authentication
```bash
# Via web interface: Settings → General → Authentication
require_authentication=true
simple_auth_username="admin"
simple_auth_password="..."  # set via the Settings UI - hashed with bcrypt automatically
```

#### Password Hashing
Passwords are hashed with **bcrypt** (`src/services/simple_auth_service.py`) — don't hash a password yourself and paste in the hash. Set the password through the Settings UI or the installation wizard and let the app hash it. (Older installs with a pre-existing SHA-256 hash are lazily migrated to bcrypt on next successful login; SHA-256 is not used for anything new.)

### SSL/HTTPS Configuration

#### SSL Settings
| Setting | Default | Description |
|---------|---------|-------------|
| `ssl_required` | false | Force HTTPS redirects |
| `ssl_port` | 443 | HTTPS port |
| `ssl_hsts_enabled` | false | HTTP Strict Transport Security |
| `ssl_hsts_max_age` | 31536000 | HSTS max age (1 year) |
| `ssl_redirect_permanent` | false | Use 301 vs 302 redirects |

**SSL Configuration Example:**
```bash
# Enable SSL with HSTS
ssl_required=true
ssl_port=443
ssl_hsts_enabled=true
ssl_hsts_max_age=31536000
```

**Reverse Proxy Setup (Nginx):**
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🌐 External Service Integration

### IMVDB Integration

#### API Key Configuration
```bash
# Get API key from https://imvdb.com/developers
imvdb_api_key="your_imvdb_api_key"
```

**Features Enabled:**
- Artist metadata enrichment
- Music video discovery
- Album artwork and biographies
- Video metadata validation

### YouTube Integration

#### YouTube API Setup
```bash
# Get API key from Google Cloud Console
youtube_api_key="your_youtube_api_key"
youtube_enabled=true
youtube_auto_download=false
youtube_playlist_sync_interval=60  # minutes
```

**Required Google Cloud APIs:**
- YouTube Data API v3
- YouTube Analytics API (optional)

**Usage Quotas:**
- Free tier: 10,000 units/day
- Search operations: ~100 units each
- Monitor usage in Google Cloud Console

### MeTube Integration

#### MeTube Server Configuration
```bash
# MeTube server settings
metube_host="localhost"
metube_port=8081
```

**Docker Compose Setup:**
```yaml
version: '3.8'
services:
  mvidarr:
    image: mvidarr:latest
    ports:
      - "5000:5000"
    depends_on:
      - metube
      
  metube:
    image: ghcr.io/alexta69/metube
    ports:
      - "8081:8081"
    volumes:
      - ./downloads:/downloads
```

### Spotify Integration

#### OAuth Configuration
```bash
# Create Spotify app at https://developer.spotify.com
spotify_enabled=true
spotify_client_id="your_spotify_client_id"
spotify_client_secret="your_spotify_client_secret"
spotify_redirect_uri="http://localhost:5000/api/spotify/callback"
```

**Spotify App Setup:**
1. Create app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Add redirect URI: `http://your-domain.com/api/spotify/callback`
3. Copy Client ID and Client Secret to MVidarr settings

### Lidarr Integration

#### Lidarr Connection
```bash
# Lidarr server configuration
lidarr_enabled=true
lidarr_server_url="http://localhost:8686"
lidarr_api_key="your_lidarr_api_key"
lidarr_sync_interval=6  # hours
```

**Features:**
- Artist synchronization
- Album monitoring
- Quality profile matching
- Automatic music video downloads for monitored artists

## 📥 Download & Processing Settings

### Download Configuration

#### Quality and Processing
```bash
# Video quality preferences
video_quality_preference="best"  # Options: best, worst, 1080p, 720p, 480p
max_concurrent_downloads=3
auto_organize_downloads=true
```

**Quality Options:**
- `best` - Highest available quality
- `worst` - Lowest available quality  
- `1080p`, `720p`, `480p` - Specific resolutions
- `bestaudio` - Audio only
- `bestvideo` - Video only (no audio)

### Automated Scheduling (Scheduler V2)

**NOTE:** Scheduler V2 configuration is now managed through the **database via the Settings page** in the web UI. Environment variables for scheduling are no longer used.

#### Accessing Scheduler V2 Settings

1. Navigate to **Settings** → **Scheduler** in the web UI
2. Configure schedules directly through the interface
3. Changes take effect immediately without restart

#### Auto-Download Schedule
Configure via Settings page:
- **Enable/Disable**: Auto download scheduling toggle
- **Schedule Time**: Time of day to run (e.g., "02:00")
- **Schedule Frequency**: daily, hourly, weekly, or custom cron
- **Max Videos**: Maximum videos to download per run

#### Auto-Discovery Schedule
Configure via Settings page:
- **Enable/Disable**: Auto discovery scheduling toggle
- **Schedule Time**: Time of day to run (e.g., "06:00")
- **Schedule Frequency**: daily, hourly, weekly, or custom cron
- **Max Videos per Artist**: Limit per artist

#### Scheduler V2 API Endpoints

Like all MVidarr API endpoints, these require an authenticated session (add `-H "Cookie: session=..."` or use `curl -b`/`-c` with a prior login) — omitted below for brevity.

```bash
# Get scheduler status
curl http://localhost:5000/api/v2/scheduler/status

# Manually trigger discovery
curl -X POST http://localhost:5000/api/v2/scheduler/trigger/discovery

# Manually trigger downloads
curl -X POST http://localhost:5000/api/v2/scheduler/trigger/downloads

# Reload settings from database
curl -X POST http://localhost:5000/api/v2/scheduler/settings/reload
```

**Benefits of Scheduler V2:**
- **Database-Driven**: All settings stored in database
- **Web UI Management**: No need to edit environment files
- **Dynamic Updates**: Changes apply immediately
- **Job History**: Track all scheduled job executions
- **Health Monitoring**: Built-in health checks and status
- **API Control**: Full REST API for automation

## 🗄️ Database Configuration

### Connection Settings

#### Database Connection
```bash
# MySQL/MariaDB configuration
db_host="localhost"
db_port=3306
db_name="mvidarr"
db_user="mvidarr_user"
db_password="secure_db_password"
```

#### Connection Pool Settings
```bash
# Performance optimization
db_pool_size=10
db_max_overflow=20
db_pool_timeout=30
```

**Database Setup:**
```sql
-- Create database and user
CREATE DATABASE mvidarr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mvidarr_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON mvidarr.* TO 'mvidarr_user'@'localhost';
FLUSH PRIVILEGES;
```

MVidarr requires MariaDB or MySQL — there is no SQLite mode, for any deployment size.

## 📊 Logging & Monitoring

### Logging Configuration

#### Log Level Settings
```bash
# Logging configuration
log_level="INFO"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
log_max_size=10485760  # 10MB
log_backup_count=5
```

**Log Levels Explained:**
- `DEBUG` - Detailed diagnostic information
- `INFO` - General application flow
- `WARNING` - Warning messages
- `ERROR` - Error messages  
- `CRITICAL` - Critical system errors

#### Log File Locations
```bash
# Docker deployment
/app/logs/mvidarr.log

# Local installation
~/.local/share/mvidarr/logs/mvidarr.log
/var/log/mvidarr/mvidarr.log  # System-wide install
```

### Notifications

#### System Notifications
```bash
# Enable notifications
enable_notifications=true
```

**Notification Types:**
- Download completions
- Error alerts
- System status changes
- Scheduled task results

## 🐳 Docker Configuration

### Environment Variables

#### Complete Docker Environment
```bash
# docker-compose.env
# Core Application
PORT=5000
DEBUG=false
SECRET_KEY=your-secure-secret-key

# Database
DB_HOST=db
DB_PORT=3306
DB_NAME=mvidarr
DB_USER=mvidarr
DB_PASSWORD=secure-password

# Redis Configuration
# Use these when connecting to a non-default or external Redis server
REDIS_HOST=redis           # Redis hostname (default: redis)
REDIS_PORT=6379            # Redis port (default: 6379)
REDIS_URL=redis://redis:6379/0         # Full Redis URL for main cache
CELERY_BROKER_URL=redis://redis:6379/0 # Celery broker URL
CELERY_RESULT_BACKEND=redis://redis:6379/1  # Celery results backend

# External Services
IMVDB_API_KEY=your-imvdb-api-key
YOUTUBE_API_KEY=your-youtube-api-key

# MeTube Integration
METUBE_HOST=metube
METUBE_PORT=8081

# Paths (container paths)
DOWNLOADS_PATH=/app/downloads
MUSIC_VIDEOS_PATH=/app/musicvideos
THUMBNAILS_PATH=/app/thumbnails

# NOTE: Scheduler configuration moved to database (Scheduler V2)
# Configure via Settings page in web UI instead of environment variables
```

### Docker Compose Configuration

#### Complete docker-compose.yml
```yaml
version: '3.8'

services:
  mvidarr:
    image: mvidarr:latest
    container_name: mvidarr-app
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
      - ./downloads:/app/downloads
      - ./musicvideos:/app/musicvideos
      - ./thumbnails:/app/thumbnails
      - ./database:/app/database
      - ./logs:/app/logs
    environment:
      - DB_HOST=db
      - DB_NAME=mvidarr
      - DB_USER=mvidarr
      - DB_PASSWORD=${DB_PASSWORD}
      - IMVDB_API_KEY=${IMVDB_API_KEY}
      - YOUTUBE_API_KEY=${YOUTUBE_API_KEY}
    env_file:
      - .env
    depends_on:
      - db
      - metube
    networks:
      - mvidarr-network

  db:
    image: mariadb:10.11
    container_name: mvidarr-db
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=mvidarr
      - MYSQL_USER=mvidarr
      - MYSQL_PASSWORD=${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/mysql
      - ./database/backup:/backup
    networks:
      - mvidarr-network

  metube:
    image: ghcr.io/alexta69/metube
    container_name: mvidarr-metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - ./downloads:/downloads
    networks:
      - mvidarr-network

volumes:
  db_data:

networks:
  mvidarr-network:
    driver: bridge
```

## ⚡ Performance Optimization

### Resource Configuration

#### Memory and CPU Settings
```yaml
# In docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2.0'
    reservations:
      memory: 512M
      cpus: '0.5'
```

### Database Optimization

#### Connection Pool Tuning
```bash
# For high-traffic deployments
db_pool_size=20
db_max_overflow=40
db_pool_timeout=60
```

#### Index Optimization
```sql
-- Performance indexes (applied automatically)
CREATE INDEX idx_videos_artist_id ON videos(artist_id);
CREATE INDEX idx_videos_status ON videos(status);
CREATE INDEX idx_downloads_status ON downloads(status);
```

## 🔄 Configuration Management

### Settings API

#### Programmatic Access
```bash
# Get all settings
curl http://localhost:5000/api/settings/

# Get specific setting
curl http://localhost:5000/api/settings/imvdb_api_key

# Update setting
curl -X PUT http://localhost:5000/api/settings/max_concurrent_downloads \
  -H "Content-Type: application/json" \
  -d '{"value": "5"}'

# Bulk update
curl -X PUT http://localhost:5000/api/settings/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "imvdb_api_key": "new-key",
    "max_concurrent_downloads": "3",
    "video_quality_preference": "720p"
  }'
```

### Configuration Backup

#### Export Settings
```bash
# Export all settings
curl http://localhost:5000/api/settings/ > mvidarr-settings-backup.json

# Create full database backup (MariaDB/MySQL - see CLAUDE.md, mvidarr does not use SQLite)
docker exec mvidarr-mariadb mysqldump -u mvidarr -p mvidarr > full-backup.sql
```

#### Import Settings
```bash
# Import settings via API
curl -X PUT http://localhost:5000/api/settings/bulk \
  -H "Content-Type: application/json" \
  -d @mvidarr-settings-backup.json
```

## 🚨 Security Considerations

### API Key Security

#### Best Practices
- Store API keys in environment variables
- Use different keys for development/production
- Regularly rotate API keys
- Monitor API usage quotas

#### Key Storage
```bash
# Secure environment file (.env)
# Never commit this to version control
IMVDB_API_KEY=abc123def456
YOUTUBE_API_KEY=xyz789uvw012
DB_PASSWORD=secure-random-password
```

### Access Control

#### Network Security
```bash
# Firewall configuration (example)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw deny 5000/tcp   # Block direct access (use reverse proxy)
```

## 📋 Configuration Checklist

### Initial Setup
- [ ] Configure file system paths
- [ ] Set up database connection
- [ ] Configure authentication (if required)
- [ ] Add IMVDB API key
- [ ] Add YouTube API key (if using)
- [ ] Configure MeTube connection
- [ ] Set video quality preferences
- [ ] Configure download scheduling

### Security Setup
- [ ] Enable authentication
- [ ] Configure SSL/HTTPS
- [ ] Set up reverse proxy
- [ ] Configure firewall rules
- [ ] Secure API key storage
- [ ] Enable HSTS (if using SSL)

### Performance Optimization
- [ ] Tune database connection pool
- [ ] Configure resource limits
- [ ] Set up log rotation
- [ ] Enable appropriate caching
- [ ] Monitor resource usage

### Integration Setup
- [ ] Configure Spotify (if using)
- [ ] Set up Lidarr integration (if using)
- [ ] Configure scheduled tasks
- [ ] Test external service connections
- [ ] Set up monitoring and alerts

## 🔗 Related Documentation

- **Installation Guide**: See `installation.md`
- **Docker Troubleshooting**: See `TROUBLESHOOTING_DOCKER.md`
- **System Monitoring**: See `MONITORING.md`
- **API Documentation**: See `API_DOCUMENTATION.md`
- **User Guide**: See `USER-GUIDE.md`

This configuration guide provides comprehensive coverage of all MVidarr configuration options and best practices for optimal performance and security.