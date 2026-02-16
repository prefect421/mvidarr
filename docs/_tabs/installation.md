---
layout: page
title: Installation
permalink: /installation/
---

# Installation Guide

This guide provides comprehensive instructions for installing and configuring MVidarr in various environments.

## 🐳 Docker Deployment (Recommended)

Docker deployment is the recommended method for production use, offering consistent environments and easy maintenance.

### Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- At least 2GB RAM available
- Path to your music video collection

### Quick Start

**1. Clone the repository:**
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
```

**2. Create your environment file:**
```bash
cp .env.example .env
```

**3. Edit your .env file:**
```bash
nano .env  # or use your preferred editor
```

**Required settings to configure:**
```bash
# Database passwords
DB_PASSWORD=your_secure_database_password_here
MYSQL_ROOT_PASSWORD=your_secure_root_password_here

# Application security (generate with: openssl rand -hex 32)
SECRET_KEY=your_secret_key_here_minimum_32_characters

# Path to your music video collection
MUSIC_VIDEOS_PATH=/path/to/your/music/videos
```

**Optional settings:**
```bash
# API Keys for metadata enrichment
IMVDB_API_KEY=your_imvdb_api_key
YOUTUBE_API_KEY=your_youtube_api_key

# Port configuration
MVIDARR_PORT=5000

# Timezone
TZ=America/New_York
```

**4. Start MVidarr:**
```bash
docker-compose up -d
```

**5. Access the application:**
- Open your browser to `http://localhost:5000`
- Default login: `admin` / `admin` (⚠️ **Change immediately**)
- Complete the first-run setup wizard

### Production Docker Image

Use our production image:

```bash
# Pull the latest stable release
docker pull ghcr.io/prefect421/mvidarr:latest

# Or specific version
docker pull ghcr.io/prefect421/mvidarr:v0.12.3
```

The `docker-compose.yml` automatically uses the `:latest` tag for production deployments.

### Docker Architecture

MVidarr uses a simplified 3-container architecture:

- **mvidarr** - FastAPI application + Celery worker (managed by supervisord)
- **mariadb** - MySQL-compatible database (MariaDB 11.4)
- **redis** - Cache and job queue

All background jobs run inside the main container, making deployment simple and efficient.

### Updating

To update to the latest version:

```bash
cd mvidarr
git pull origin main
docker-compose pull
docker-compose up -d
```

### Managing Containers

```bash
# View logs
docker-compose logs -f mvidarr

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Stop and remove volumes (⚠️ deletes database)
docker-compose down -v
```

## 🖥️ Unraid Installation

MVidarr can be easily installed on Unraid using the Community Applications template.

### Quick Installation

1. Open **Apps** tab in Unraid
2. Search for **"MVidarr"**
3. Click **Install** and configure settings
4. Access at `http://[UNRAID-IP]:5000`

### Requirements

- **Unraid 6.9+** (6.12+ recommended)
- **MariaDB container** (install from Community Applications if needed)
- **Community Applications plugin** installed

### Detailed Instructions

For complete Unraid installation instructions including:
- MariaDB setup and configuration
- Container configuration and path mapping
- Troubleshooting common Unraid issues
- Performance optimization tips
- Reverse proxy configuration

**See our comprehensive [Unraid Installation Guide](https://github.com/prefect421/mvidarr/blob/main/docs/UNRAID_INSTALLATION.md)**

## 🐧 Manual Installation (Linux/macOS)

For development or non-Docker deployments.

### Prerequisites

- Python 3.12+
- MariaDB 11.4+ or MySQL 8.0+
- Redis 7+
- FFmpeg
- yt-dlp

### Installation Steps

**1. Clone the repository:**
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
```

**2. Create virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
pip install -r requirements-fastapi.txt
```

**4. Configure database:**
```bash
# Install MariaDB
sudo apt install mariadb-server  # Ubuntu/Debian
# OR
brew install mariadb  # macOS

# Create database and user
mysql -u root -p << EOF
CREATE DATABASE mvidarr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mvidarr'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON mvidarr.* TO 'mvidarr'@'localhost';
FLUSH PRIVILEGES;
EOF
```

**5. Configure environment:**
```bash
cp .env.example .env
nano .env
```

Set database connection:
```bash
DB_HOST=localhost
DB_USER=mvidarr
DB_PASSWORD=your_password
DB_NAME=mvidarr
SECRET_KEY=$(openssl rand -hex 32)
```

**6. Initialize database:**
```bash
python scripts/init_db.py
```

**7. Start services:**
```bash
# Terminal 1: Start FastAPI application
python fastapi_app.py

# Terminal 2: Start Celery worker (optional, for background jobs)
celery -A src.celery_app worker --loglevel=info

# Terminal 3: Start Celery beat (optional, for scheduled tasks)
celery -A src.celery_app beat --loglevel=info
```

**8. Access the application:**
- Open your browser to `http://localhost:5000`
- Default login: `admin` / `admin`

### Production Service (systemd)

For production deployments, use systemd:

```bash
# Copy service file
sudo cp mvidarr.service /etc/systemd/system/

# Edit paths in service file
sudo nano /etc/systemd/system/mvidarr.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mvidarr.service
sudo systemctl start mvidarr.service

# Check status
sudo systemctl status mvidarr.service
```

## 🪟 Windows Installation

### Using Docker Desktop (Recommended)

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. Enable WSL 2 backend
3. Follow the Docker deployment instructions above

### Manual Installation

1. Install [Python 3.12+](https://www.python.org/downloads/)
2. Install [MariaDB](https://mariadb.org/download/)
3. Install [FFmpeg](https://ffmpeg.org/download.html)
4. Follow manual installation steps (use `venv\Scripts\activate` for venv)

## 🔧 Configuration

After installation, configure MVidarr through:

1. **Environment Variables** (`.env` file) - Database, security, paths
2. **Web UI Settings** - API keys, metadata preferences, themes
3. **Setup Wizard** - First-run configuration guide

See [Configuration Guide](https://github.com/prefect421/mvidarr/blob/main/docs/CONFIGURATION_GUIDE.md) for detailed configuration options.

## 🔍 Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs mvidarr

# Common issues:
# - Missing .env file (copy from .env.example)
# - Invalid SECRET_KEY (must be 32+ characters)
# - MUSIC_VIDEOS_PATH doesn't exist
```

### Database connection errors
```bash
# Check MariaDB is healthy
docker-compose ps

# Verify database credentials in .env match docker-compose.yml
```

### Permission issues
```bash
# Set correct PUID/PGID in .env
# Run 'id' command to get your user/group IDs
PUID=1000
PGID=1000
```

See [Troubleshooting Guide](https://github.com/prefect421/mvidarr/blob/main/docs/TROUBLESHOOTING.md) for more help.

## 📚 Next Steps

- [User Guide](https://github.com/prefect421/mvidarr/blob/main/docs/USER-GUIDE.md) - Learn how to use MVidarr
- [Configuration Guide](https://github.com/prefect421/mvidarr/blob/main/docs/CONFIGURATION_GUIDE.md) - Advanced configuration
- [API Documentation](https://github.com/prefect421/mvidarr/blob/main/docs/API_DOCUMENTATION.md) - REST API reference

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/prefect421/mvidarr/issues)
- **Documentation**: [Full Documentation](https://prefect421.github.io/mvidarr/)
- **Community**: [Discussions](https://github.com/prefect421/mvidarr/discussions)
