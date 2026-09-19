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

**Required: `TRUSTED_PROXY_HOSTS`**

Setting `X-Forwarded-Proto` in the proxy config above isn't enough by itself — MVidarr only trusts that header from peers listed in the `TRUSTED_PROXY_HOSTS` env var (defaults to loopback-only, `127.0.0.1`, since v1.0.2 / issue #488). Without it set to your proxy's address, MVidarr thinks every request arrived over plain HTTP even though the browser is on `https://`, and any endpoint that issues a redirect (e.g. FastAPI's trailing-slash redirects) will emit an `http://` `Location` header — which the browser then blocks as **mixed active content**, breaking API calls on pages like `/videos`.

```bash
# In your MVidarr .env:
TRUSTED_PROXY_HOSTS=<proxy's IP or hostname, comma-separated if multiple>
```

⚠️ **Same-host Docker gotcha**: if the proxy runs in Docker on the *same host* as MVidarr but reaches it via the **published port** (`proxy → http://<host-ip>:5050`) rather than a shared Docker network, Docker's hairpin NAT rewrites the connection's source address to the network's **bridge gateway IP** (typically `172.x.x.1`) — not the proxy container's own IP. `TRUSTED_PROXY_HOSTS` set to the proxy's container IP will never match in that topology, and you'll keep seeing the mixed-content error even after setting it. Either:
- Set `TRUSTED_PROXY_HOSTS` to the bridge gateway IP instead (find it via `docker network inspect <network>`, or empirically — see below), understanding this trusts forwarded headers from *any* local process reaching the published port, not just the proxy specifically; or
- Put the proxy on MVidarr's Docker network (or a shared external network) so it connects by container name/IP directly, and trust that IP — a tighter boundary.

To find the actual peer address MVidarr sees, run this while making a request through the proxy (`1388` hex = port 5000):
```bash
docker exec <mvidarr-container> sh -c "grep ' 01 ' /proc/net/tcp | grep ':1388 '"
```
The remote-address column is a hex-encoded, byte-reversed IPv4 address (e.g. `010015AC` → reverse the byte pairs → `AC.15.00.01` → `172.21.0.1`).

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

**Running MeTube alongside MVidarr:**

MVidarr's own `docker-compose.yml` doesn't bundle a MeTube container — MeTube is an optional, separately-run service you point MVidarr at via the `metube_host`/`metube_port` settings above. To run one on the same Docker host, add this service block into the `services:` section of your existing `docker-compose.yml`, alongside `mvidarr`, `mariadb`, and `redis` (it reuses that same file's `mvidarr` network, so no extra network setup is needed):

```yaml
  metube:
    image: ghcr.io/alexta69/metube
    container_name: mvidarr-metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - ./data/downloads:/downloads
    networks:
      - mvidarr
```

Then `docker compose up -d` to start it, and set `metube_host=metube` and `metube_port=8081` in Settings — or `metube_host=localhost` if MeTube instead runs directly on the host, outside Docker.

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

### The docker-compose.yml File

MVidarr ships a ready-to-use `docker-compose.yml` in the repo root — **you don't write one from scratch**; you configure the shipped one through a `.env` file next to it. It defines a 3-container stack, all on a shared `mvidarr` bridge network:

| Service | Container name | Image | Purpose |
|---------|----------------|-------|---------|
| `mvidarr` | `mvidarr` | `ghcr.io/prefect421/mvidarr:latest` | FastAPI app + Celery worker (managed by supervisord) |
| `mariadb` | `mvidarr-mariadb` | `mariadb:11.4` | Database |
| `redis` | `mvidarr-redis` | `redis:7-alpine` | Cache and Celery job queue (password-protected) |

There's also a separate `docker-compose.dev.yml`, which builds the `mvidarr` image from local source instead of pulling it — that one's for working on MVidarr itself, not for a normal deployment.

### Setting Up .env

```bash
cp .env.example .env
nano .env
```

`.env.example` is the only environment-file template that matches the shipped `docker-compose.yml` — use it, not anything else you may find referenced in older forum posts or issues.

**Required — the compose file has no working default for these:**

| Variable | Description |
|----------|-------------|
| `DB_PASSWORD` | Password for the MariaDB app user (`mvidarr`) |
| `MYSQL_ROOT_PASSWORD` | MariaDB root password (used for admin/backup tasks) |
| `SECRET_KEY` | Session-signing secret — generate with `openssl rand -hex 32` |
| `MUSIC_VIDEOS_PATH` | Host path to your music video library — no default, must be an absolute path that exists |

**Optional — sensible defaults are built into `docker-compose.yml`:**

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_USER` | `mvidarr` | MariaDB app user |
| `DB_NAME` | `mvidarr` | Database name |
| `MVIDARR_PORT` | `5000` | Host port mapped to the app's container port (always `5000` internally) |
| `REDIS_PASSWORD` | `mvidarr_redis_default` | Redis auth password — Redis isn't published to the host, but set your own anyway |
| `DOWNLOADS_PATH` | `./data/downloads` | Host path for in-progress downloads |
| `THUMBNAILS_PATH` | `./data/thumbnails` | Host path for cached thumbnails |
| `DATABASE_PATH` | `./data/database` | Host path for MVidarr's own DB backup/export files — **not** MariaDB's live data, which lives in the separate `mariadb_data` named Docker volume (back that up with `mysqldump`, not this path) |
| `LOGS_PATH` | `./data/logs` | Host path for application logs |
| `CACHE_PATH` | `./data/cache` | Host path for temp/cache files |
| `IMVDB_API_KEY`, `YOUTUBE_API_KEY` | *(empty)* | Metadata enrichment — can also be set later via the Settings UI |
| `TZ` | `America/New_York` | Container timezone |
| `PUID`, `PGID` | `1000` | User/group IDs the app writes files as — match your host user |
| `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_HOSTS` | *(project defaults)* | See [Reverse Proxy Setup](#sslhttps-configuration) above if you're behind one |
| `CELERY_WORKER_EXTRA_ARGS` | *(empty)* | Extra arguments appended to the Docker Celery worker command (the worker already runs with `--without-mingle`) |

> **Scheduler settings are not environment variables.** Scheduler V2 (auto-download/auto-discovery timing) is configured entirely through the Settings page in the web UI, database-backed — there's nothing to set here or in `docker-compose.yml`.

### Starting the Stack

```bash
docker compose up -d      # or: docker-compose up -d, depending on your Docker install
```

`mariadb` and `redis` both have healthchecks, and `mvidarr` waits (`depends_on: condition: service_healthy`) for both before it starts — so a first `up -d` can take a little while as MariaDB initializes.

### Customizing docker-compose.yml

If you need to change something the `.env` variables above don't cover — memory/CPU limits, a MeTube sidecar (see [MeTube Integration](#metube-integration) above), a different MariaDB storage location, etc. — edit `docker-compose.yml` directly rather than writing a replacement from scratch, so you don't lose the healthchecks and network wiring the shipped file already gets right. A couple of things worth knowing before you do:

- The app's container port is hardcoded to `5000`; only the host-side mapping (`MVIDARR_PORT`) is configurable.
- Container-internal data paths are all under `/app/data/...` (e.g. `/app/data/musicvideos`), not `/app/...` — this changed from older, pre-1.0 layouts you may see referenced in old issues.
- `DB_HOST` inside the `mvidarr` service is hardcoded to `mariadb` (the service name) — it's not one of the `.env` variables, since it always needs to match the `mariadb` service block.

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