# MVidarr Simple Deployment Guide

> **For Self-Hosters**: Easy Docker deployment without enterprise complexity

## Quick Start (5 Minutes)

### Prerequisites
- Docker and Docker Compose installed
- 2GB+ RAM available
- Storage for your music videos

### 1. Get MVidarr

```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
```

### 2. Configure Environment

```bash
# Copy the example configuration
cp .env.simple.example .env

# Edit configuration
nano .env
```

**Required settings to change**:
- `MUSIC_VIDEOS_PATH` - Path to your music video folder
- `DB_PASSWORD` - Secure database password
- `MYSQL_ROOT_PASSWORD` - Secure root password  
- `REDIS_PASSWORD` - Secure Redis password
- `SECRET_KEY` - Long random secret (32+ characters)

**Generate secure passwords**:
```bash
openssl rand -base64 32
```

### 3. Start MVidarr

```bash
docker-compose -f docker-compose.simple.yml up -d
```

### 4. Access MVidarr

Open your browser to: **http://localhost:5000**

The installation wizard will guide you through first-time setup!

---

## Architecture

MVidarr uses three required services:

1. **MVidarr App** (Port 5000) - Main application
2. **MariaDB** (Internal) - Database for metadata
3. **Redis** (Internal) - Cache and background job queue

Optional service:
- **MeTube** (Port 8081) - yt-dlp Web UI for downloading videos

---

## Common Operations

### View Logs

```bash
# All services
docker-compose -f docker-compose.simple.yml logs -f

# Just MVidarr
docker-compose -f docker-compose.simple.yml logs -f mvidarr

# Just database
docker-compose -f docker-compose.simple.yml logs -f mariadb
```

### Check Status

```bash
# Container status
docker-compose -f docker-compose.simple.yml ps

# Health check
curl http://localhost:5000/api/health/dashboard | jq
```

### Stop MVidarr

```bash
docker-compose -f docker-compose.simple.yml stop
```

### Restart MVidarr

```bash
docker-compose -f docker-compose.simple.yml restart
```

### Full Shutdown

```bash
docker-compose -f docker-compose.simple.yml down
```

---

## Updating MVidarr

### Automatic Update (Recommended)

```bash
./scripts/deployment/deploy.sh
```

This script will:
1. Create automatic backup
2. Pull latest version
3. Update containers
4. Verify health
5. Clean up old images

### Manual Update

```bash
# Pull latest image
docker pull ghcr.io/prefect421/mvidarr:latest

# Recreate container
docker-compose -f docker-compose.simple.yml up -d --force-recreate mvidarr
```

### Specific Version

```bash
./scripts/deployment/deploy.sh --tag v1.0.0
```

---

## Rollback

If an update causes issues:

```bash
./scripts/deployment/rollback.sh
```

This will restore the previous working version.

---

## Backup & Recovery

### Create Backup (Manual)

```bash
# Via CLI
python3 scripts/manage_backups.py create --type full

# Via API
curl -X POST http://localhost:5000/api/backups/create \
  -H "Content-Type: application/json" \
  -d '{"backup_type":"full"}'
```

### List Backups

```bash
python3 scripts/manage_backups.py list
```

### Restore Backup

```bash
python3 scripts/manage_backups.py restore <backup_id>
```

Backups are stored in: `${DATA_PATH}/backups/`

---

## Adding MeTube (YouTube Downloader)

Enable the optional MeTube service for downloading music videos:

```bash
docker-compose -f docker-compose.simple.yml --profile metube up -d
```

Access MeTube at: **http://localhost:8081**

Downloads will automatically go to your `MUSIC_VIDEOS_PATH` folder.

---

## Storage Configuration

MVidarr stores data in directories you configure:

```bash
MUSIC_VIDEOS_PATH=/path/to/videos  # Your music video collection (scanned by MVidarr)
DATA_PATH=./data                    # Application data (created automatically)
```

The `DATA_PATH` contains:
- `thumbnails/` - Video thumbnail cache
- `database/` - SQLite metadata
- `mariadb/` - MariaDB database files
- `redis/` - Redis persistence
- `logs/` - Application logs
- `downloads/` - Temporary download folder
- `cache/` - Metadata cache
- `backups/` - Backup archives

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose -f docker-compose.simple.yml logs mvidarr

# Verify .env file
cat .env

# Check file permissions
ls -la data/
```

### Database Connection Failed

```bash
# Check MariaDB health
docker-compose -f docker-compose.simple.yml logs mariadb

# Verify password in .env matches
grep DB_PASSWORD .env
```

### Port Already in Use

Edit `.env` and change:
```bash
MVIDARR_PORT=5001  # Use different port
```

### Reset Everything

```bash
# WARNING: This deletes all data!
docker-compose -f docker-compose.simple.yml down -v
rm -rf data/
```

Then start fresh with Quick Start steps.

---

## Advanced Configuration

### Custom Network

The compose file creates a bridge network `mvidarr-network`. Containers can communicate using service names:
- `mariadb` - Database server
- `redis` - Redis cache
- `metube` - MeTube downloader (if enabled)

### Health Checks

All services have automatic health checks:
- **MVidarr**: Checks `/api/health` endpoint
- **MariaDB**: MySQL ping
- **Redis**: Redis ping

Failed health checks trigger automatic restarts.

### Resource Limits

Add resource limits to `.env`:

```bash
MVIDARR_CPU_LIMIT=2.0
MVIDARR_MEMORY_LIMIT=2g
```

Update docker-compose.simple.yml to use these limits.

---

## Monitoring

### Health Dashboard

Comprehensive health information:
```bash
curl http://localhost:5000/api/health/dashboard | jq
```

Shows:
- Application status
- Database health
- System resources (CPU, memory, disk)
- v1.0.0 components (wizard, backups, migrations)
- Background jobs
- Active alerts

### v1.0.0 Components

Monitor installation wizard, backups, and migrations:
```bash
curl http://localhost:5000/api/health/v1-components | jq
```

### Background Jobs

Monitor video indexing and metadata enrichment:
```bash
curl http://localhost:5000/api/health/background-jobs | jq
```

---

## Security Recommendations

1. **Change Default Passwords**: Always use secure random passwords
2. **Use HTTPS**: Add nginx reverse proxy with SSL certificates
3. **Firewall**: Limit port 5000 to trusted networks
4. **Regular Backups**: Schedule automated backups
5. **Update Regularly**: Keep MVidarr updated with `deploy.sh`

### Adding SSL with Nginx

Create `docker/nginx/nginx.conf` and add nginx service to compose file.

Use Let's Encrypt for free SSL certificates:
```bash
certbot certonly --standalone -d your-domain.com
```

---

## Getting Help

- **Documentation**: https://prefect421.github.io/mvidarr
- **Issues**: https://github.com/prefect421/mvidarr/issues
- **Health Check**: http://localhost:5000/api/health/dashboard

---

## Environment Reference

Complete `.env` template with all options:

```bash
# Application
MVIDARR_PORT=5000
TZ=America/New_York

# Security (CHANGE THESE!)
DB_PASSWORD=your_secure_password
MYSQL_ROOT_PASSWORD=your_secure_root_password
REDIS_PASSWORD=your_secure_redis_password
SECRET_KEY=your_very_long_random_secret_key_32_chars_minimum

# Storage Paths
MUSIC_VIDEOS_PATH=/path/to/your/musicvideos
DATA_PATH=./data

# Optional APIs
IMVDB_API_KEY=your_imvdb_key
YOUTUBE_API_KEY=your_youtube_key

# Optional MeTube
METUBE_PORT=8081
METUBE_URL=http://metube:8081
```

---

**Happy Self-Hosting! 🎵**
