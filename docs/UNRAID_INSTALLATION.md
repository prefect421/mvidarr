# 🖥️ MVidarr - Unraid Installation Guide

Complete guide for installing and configuring MVidarr on Unraid using the Community Applications template.

---

## 📋 Prerequisites

Before installing MVidarr on Unraid, ensure you have:

- **Unraid 6.9+** (6.12+ recommended)
- **Community Applications plugin** installed
- **MariaDB container** running (or plan to install one)
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

## 🎬 Step 2: Install MVidarr

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

1. Open **Docker** tab in Unraid
2. Scroll to bottom and click **Add Container**
3. In the **Template** dropdown, select **Select another template**
4. Paste this URL:
   ```
   https://raw.githubusercontent.com/prefect421/mvidarr/main/unraid-template.xml
   ```
5. Configure settings and click **Apply**

---

## ⚙️ Step 3: Configuration

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

## 🚀 Step 4: Start and Access MVidarr

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

## 🔧 Post-Installation Setup

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

**View MVidarr logs:**
```bash
docker logs mvidarr
# Look for database connection errors
```

### Common Issues:

#### "Database connection failed"
- Verify `DB_HOST` matches your MariaDB container name
- Ensure `DB_PASSWORD` matches MariaDB user password
- Check MariaDB container is running
- Verify database `mvidarr` exists in MariaDB

#### "Permission denied" errors
- Check Unraid user permissions on appdata directories
- Ensure container has read/write access to mapped paths

#### Can't access WebUI
- Verify port `5000` is not used by another container
- Check Unraid firewall settings
- Try accessing via `http://localhost:5000` from Unraid console

### Reset Configuration:

If you need to start over:
```bash
# Stop container
docker stop mvidarr

# Remove container (keeps data)
docker rm mvidarr

# Delete appdata (WARNING: removes all data)
rm -rf /mnt/user/appdata/mvidarr/

# Reinstall container from template
```

---

## 📊 Performance Tips

### For Better Performance on Unraid:

1. **Use Cache Drive** for appdata:
   - Set MVidarr appdata to use cache drive
   - Enable mover for periodic backup to array

2. **Optimize Database**:
   - Put MariaDB data on cache/SSD if possible
   - Regular database maintenance via MVidarr settings

3. **Video Storage**:
   - Keep video files on array for capacity
   - Use cache for downloads/thumbnails

4. **Resource Allocation**:
   - Assign 2-4 CPU cores to MVidarr container
   - Allocate 2-4GB RAM depending on library size

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

---

## ✅ Installation Complete!

Your MVidarr installation should now be running. Access it at `http://[UNRAID-IP]:5000` and enjoy managing your music video collection!
