# 🖥️ MVidarr - Unraid Installation Guide

Complete guide for installing and configuring MVidarr on Unraid using the Community Applications template.

## 🚀 Quick Start Overview

MVidarr requires **three containers** to run on Unraid:

1. **MariaDB** - Database for storing video metadata and application data
2. **Redis** - Cache and job queue for background processing
3. **MVidarr** - Main application container

**Installation Order:**
1. Install MariaDB container (Step 1)
2. Install Redis container (Step 2)
3. Install MVidarr container (Step 3)
4. Configure MVidarr settings (Step 4)
5. Start using MVidarr! (Step 5)

**Estimated Installation Time:** 15-20 minutes

---

## 📋 Prerequisites

Before installing MVidarr on Unraid, ensure you have:

- **Unraid 6.9+** (6.12+ recommended, 7.2.0+ for optimized template)
- **Community Applications plugin** installed
- **MariaDB container** running (or plan to install one)
- **Redis container** running (or plan to install one)
- **2GB RAM** minimum, 4GB recommended
- **5GB disk space** minimum, 50GB+ recommended for music video storage

---

## 🗄️ Step 1: Install MariaDB (if not already installed)

MVidarr requires a MariaDB/MySQL database. If you don't have one running:

### Using Community Applications:

1. Open **Apps** tab in Unraid
2. Search for **"MariaDB"**
3. Click **Install** on the official MariaDB template
4. Configure the following settings:
   - **Container Name**: `mariadb` (important - MVidarr template expects this name)
   - **Root Password**: Set a strong password (save this!)
   - **Database**: `mvidarr`
   - **Database User**: `mvidarr`
   - **Database Password**: Set a strong password (save this!)
   - **Port**: `3306` (default)

5. Click **Apply** and wait for MariaDB to start

### Verify MariaDB is running:
```bash
# From Unraid console
docker ps | grep mariadb
# Should show the mariadb container running
```

---

## 🔴 Step 2: Install Redis (if not already installed)

MVidarr requires Redis for job queuing, caching, and background task management.

### Using Community Applications:

1. Open **Apps** tab in Unraid
2. Search for **"Redis"**
3. Click **Install** on the official Redis template (redis:7-alpine recommended)
4. Configure the following settings:
   - **Container Name**: `redis` (important - MVidarr template expects this name)
   - **Port**: `6379` (default)
   - **Network Type**: `bridge` (same as MariaDB and MVidarr)
   - **Data Path**: `/mnt/user/appdata/redis/` (for persistence)

5. **Advanced Settings** (Optional but Recommended):
   - **Extra Parameters**: Add these for better performance:
     ```
     --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
     ```
   - This enables persistence and sets a 512MB memory limit with LRU eviction

6. Click **Apply** and wait for Redis to start

### Manual Redis Configuration:

If you prefer to manually configure Redis:

```bash
# From Unraid console - Create Redis container
docker run -d \
  --name=redis \
  --network=bridge \
  -p 6379:6379 \
  -v /mnt/user/appdata/redis:/data \
  redis:7-alpine \
  redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
```

### Verify Redis is running:
```bash
# From Unraid console
docker ps | grep redis
# Should show the redis container running

# Test Redis connection
docker exec -it redis redis-cli ping
# Should respond with "PONG"
```

---

## 🎬 Step 3: Install MVidarr

### Method A: Community Applications (Recommended)

1. Open **Apps** tab in Unraid
2. Search for **"MVidarr"**
3. Click **Install** on the MVidarr template
4. Configure the settings (see Configuration section below)
5. Click **Apply**

### Method B: Manual Template Installation

If MVidarr is not yet in Community Applications:

1. Open **Docker** tab in Unraid
2. Click **Add Container** at the bottom
3. Click **Template repositories**
4. Add: `https://github.com/prefect421/mvidarr`
5. Search for **MVidarr** and install

### Method C: Direct Template URL

**For Unraid 6.9 - 6.x:**
1. Open **Docker** tab in Unraid
2. Scroll to bottom and click **Add Container**
3. In the **Template** dropdown, select **Select another template**
4. Paste this URL:
   ```
   https://raw.githubusercontent.com/prefect421/mvidarr/main/unraid-template.xml
   ```
5. Configure settings and click **Apply**

**For Unraid 7.2.0+:**
1. Open **Docker** tab in Unraid
2. Scroll to bottom and click **Add Container**
3. In the **Template** dropdown, select **Select another template**
4. Paste this URL:
   ```
   https://raw.githubusercontent.com/prefect421/mvidarr/main/unraid-template-7.2.0.xml
   ```
5. Configure settings and click **Apply**

---

## ⚙️ Step 4: Configuration

### Required Settings:

#### **Paths** (adjust to your Unraid setup):

| Setting | Default | Description |
|---------|---------|-------------|
| **Music Videos** | `/mnt/user/music-videos/` | Where your music video files are stored |
| **Thumbnails** | `/mnt/user/appdata/mvidarr/thumbnails/` | Thumbnail and artwork storage |
| **Database Folder** | `/mnt/user/appdata/mvidarr/database/` | Application database |
| **Logs** | `/mnt/user/appdata/mvidarr/logs/` | Log files |
| **Downloads** | `/mnt/user/appdata/mvidarr/downloads/` | Temporary download storage |

#### **Database Settings**:

| Setting | Value | Description |
|---------|-------|-------------|
| **DB_HOST** | `mariadb` | Container name of your MariaDB instance |
| **DB_PORT** | `3306` | Database port |
| **DB_USER** | `mvidarr` | Database username (must match MariaDB setup) |
| **DB_PASSWORD** | *(your password)* | **Must match your MariaDB password** |
| **DB_NAME** | `mvidarr` | Database name (must match MariaDB setup) |

#### **Redis Settings**:

| Setting | Value | Description |
|---------|-------|-------------|
| **REDIS_HOST** | `redis` | Container name of your Redis instance |
| **REDIS_PORT** | `6379` | Redis port (default) |
| **REDIS_URL** | `redis://redis:6379/0` | Auto-configured, uses database 0 |
| **CELERY_BROKER_URL** | `redis://redis:6379/0` | Job queue broker (auto-configured) |
| **CELERY_RESULT_BACKEND** | `redis://redis:6379/1` | Job results storage (auto-configured) |

**Note:** Redis settings are auto-configured if you use the default container name `redis`. Only change if using a different Redis container name or custom port.

#### **Security Settings**:

| Setting | Description |
|---------|-------------|
| **SECRET_KEY** | Generate a random 32+ character string for session encryption |
| **MVIDARR_SECRET_KEY** | Should match SECRET_KEY (auto-populated) |

**Generate a secure SECRET_KEY:**
```bash
# From Unraid console
openssl rand -base64 32
# Copy the output and paste as SECRET_KEY
```

#### **API Keys** (Optional but Recommended):

| Setting | Description | Get From |
|---------|-------------|----------|
| **IMVDB_API_KEY** | Music video metadata | https://imvdb.com/developers |
| **YOUTUBE_API_KEY** | YouTube metadata | Google Cloud Console |

#### **Other Settings**:

| Setting | Default | Description |
|---------|---------|-------------|
| **TZ** | `America/New_York` | Your timezone (e.g., `Europe/London`) |
| **WebUI Port** | `5000` | Port to access web interface |

---

## 🚀 Step 5: Start and Access MVidarr

1. Click **Apply** to start the container
2. Wait for the container to initialize (check logs if needed)
3. Access MVidarr at: `http://[UNRAID-IP]:5000`
4. Complete the first-run setup wizard

### Check Container Logs:
```bash
# From Unraid console
docker logs -f mvidarr
```

---

## 🔧 Step 6: Post-Installation Setup

### 1. Complete First-Run Wizard

On first access, MVidarr will guide you through:
- Directory validation and setup
- API key configuration
- Initial video import
- Basic settings configuration

### 2. Configure Video Directory

1. Navigate to **Settings** → **Configuration**
2. Verify the music videos path matches your Unraid share
3. Click **Scan Videos** to import your collection

### 3. Set Up Automatic Downloads (Optional)

1. Go to **Settings** → **Downloads**
2. Configure yt-dlp settings
3. Set up automatic discovery for new videos

---

## 🐛 Troubleshooting

### Container Won't Start

**Check all required containers are running:**
```bash
docker ps | grep -E "mariadb|redis|mvidarr"
# Should show all three containers running
```

**Check MariaDB is running:**
```bash
docker ps | grep mariadb
```

**Check database connection:**
```bash
docker exec -it mariadb mysql -u mvidarr -p
# Enter your DB_PASSWORD
# If successful, you'll see MariaDB prompt
USE mvidarr;
SHOW TABLES;
```

**Check Redis is running:**
```bash
docker ps | grep redis

# Test Redis connection
docker exec -it redis redis-cli ping
# Should respond with "PONG"
```

**View MVidarr logs:**
```bash
docker logs mvidarr
# Look for database or Redis connection errors
```

### Common Issues:

#### "Database connection failed"
- Verify `DB_HOST` matches your MariaDB container name (case-sensitive)
- Ensure `DB_PASSWORD` matches MariaDB user password
- Check MariaDB container is running
- Verify database `mvidarr` exists in MariaDB
- Ensure MariaDB and MVidarr are on the same Docker network

#### "Redis connection failed" or "Background jobs not working"
- Verify `REDIS_HOST` matches your Redis container name (case-sensitive)
- Check Redis container is running: `docker ps | grep redis`
- Test Redis connection: `docker exec -it redis redis-cli ping`
- Ensure Redis and MVidarr are on the same Docker network
- Check Redis logs: `docker logs redis`
- Verify REDIS_URL is correctly formatted: `redis://redis:6379/0`

#### "Permission denied" errors
- Check Unraid user permissions on appdata directories
- Ensure container has read/write access to mapped paths
- Verify PUID (99) and PGID (100) are correct for Unraid
- Check appdata folder ownership: `ls -la /mnt/user/appdata/mvidarr/`

#### Can't access WebUI
- Verify port `5000` is not used by another container
- Check Unraid firewall settings
- Try accessing via `http://localhost:5000` from Unraid console
- Check MVidarr container logs for startup errors

### Reset Configuration:

If you need to start over:
```bash
# Stop all containers
docker stop mvidarr

# Remove MVidarr container (keeps data)
docker rm mvidarr

# Delete MVidarr appdata (WARNING: removes all MVidarr data)
rm -rf /mnt/user/appdata/mvidarr/

# Optional: Clear Redis cache (WARNING: clears all cached data)
docker exec -it redis redis-cli FLUSHALL

# Reinstall MVidarr container from template
```

**Complete Reset (including database and Redis):**
```bash
# Stop all containers
docker stop mvidarr redis mariadb

# Remove containers
docker rm mvidarr redis mariadb

# Remove all data (WARNING: deletes everything!)
rm -rf /mnt/user/appdata/mvidarr/
rm -rf /mnt/user/appdata/redis/
# Note: MariaDB data location depends on your setup

# Reinstall all containers from templates
```

---

## 📊 Performance Tips

### For Better Performance on Unraid:

1. **Use Cache Drive** for appdata:
   - Set MVidarr appdata to use cache drive for best performance
   - Set Redis appdata to use cache drive (critical for job queue speed)
   - Set MariaDB appdata to use cache drive if possible
   - Enable mover for periodic backup to array

2. **Optimize Database**:
   - Put MariaDB data on cache/SSD if possible
   - Regular database maintenance via MVidarr settings
   - Consider using MariaDB with InnoDB for better performance

3. **Optimize Redis**:
   - Redis appdata should be on cache/SSD for fast job processing
   - Use the recommended memory limit: `--maxmemory 512mb`
   - Enable persistence: `--appendonly yes`
   - Monitor Redis memory usage: `docker exec redis redis-cli INFO memory`

4. **Video Storage**:
   - Keep video files on array for capacity
   - Use cache for downloads/thumbnails for faster processing
   - Consider cache pool for transcoding temp files

5. **Resource Allocation**:
   - Assign 2-4 CPU cores to MVidarr container (for video transcoding)
   - Allocate 2-4GB RAM depending on library size
   - Allocate 512MB-1GB RAM to Redis (set via maxmemory)
   - Allocate 1-2GB RAM to MariaDB for optimal database performance

6. **Network Performance**:
   - Keep all containers (MVidarr, MariaDB, Redis) on the same Docker network
   - Use bridge mode for best compatibility
   - Consider custom Docker network for isolation if needed

---

## 🔄 Updating MVidarr

### Update via Unraid UI:

1. Go to **Docker** tab
2. Click **Check for Updates**
3. If update available, click **Update**
4. Wait for new image to download
5. Container will auto-restart with new version

### Manual Update:

```bash
# Stop container
docker stop mvidarr

# Pull latest image
docker pull ghcr.io/prefect421/mvidarr:latest

# Start container
docker start mvidarr
```

---

## 🆘 Getting Help

- **GitHub Issues**: https://github.com/prefect421/mvidarr/issues
- **Documentation**: https://prefect421.github.io/mvidarr
- **Logs**: Check MVidarr container logs via Unraid Docker tab

---

## 📝 Advanced Configuration

### Custom Network Setup

If using custom Docker networks in Unraid:

1. Stop MVidarr container
2. Edit container settings
3. Change **Network Type** to your custom network
4. Update `DB_HOST` to use MariaDB IP or hostname
5. Apply changes

### Reverse Proxy Setup (Nginx Proxy Manager)

If using Nginx Proxy Manager on Unraid:

1. Create new proxy host in NPM
2. Set **Domain Name** to your desired domain
3. Set **Forward Hostname/IP** to Unraid IP
4. Set **Forward Port** to `5000`
5. Enable **WebSocket Support**
6. Apply SSL certificate
7. In MVidarr's `.env`, set `TRUSTED_PROXY_HOSTS` to NPM's address and recreate the container — **required**, not optional, or pages will fail to load with a browser "mixed active content" error once you're accessing MVidarr over `https://` through NPM. See the "Required: `TRUSTED_PROXY_HOSTS`" note in [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md#ssl-https-configuration) — because NPM here reaches MVidarr via the Unraid host's own IP + published port (as set up above) rather than a shared Docker network, you likely need Docker's *bridge gateway* IP rather than NPM's own container IP; that doc explains why and how to find the right value.

---

## ✅ Installation Complete!

Your MVidarr installation should now be running. Access it at `http://[UNRAID-IP]:5000` and enjoy managing your music video collection!
