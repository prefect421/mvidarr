---
layout: page
title: Installation
permalink: /installation/
---

# Installation Guide

This guide provides comprehensive instructions for installing and configuring MVidarr in various environments.

## 🐳 Docker Deployment (Recommended)

Docker deployment is the recommended method for production use, offering consistent environments and easy maintenance.

### Quick Start

```bash
# Clone the repository
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr

# Start with Docker Compose
docker-compose up -d
```

**Access the application:**
- Open your browser to `http://localhost:5001`
- Default login: `admin` / `admin` (⚠️ **Change immediately**)

### Production Docker Image

Use our optimized production image:

```bash
# Pull the latest release
docker pull ghcr.io/prefect421/mvidarr:v0.9.8

# Or use in docker-compose.yml
services:
  mvidarr:
    image: ghcr.io/prefect421/mvidarr:v0.9.8
    # ... other configuration
```

### Docker Configuration

Create a `docker-compose.override.yml` for customization:

```yaml
version: '3.8'
services:
  mvidarr:
    environment:
      - SECRET_KEY=your-secure-secret-key
      - IMVDB_API_KEY=your-imvdb-api-key
      - YOUTUBE_API_KEY=your-youtube-api-key
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "5001:5000"
  
  mariadb:
    environment:
      - MYSQL_ROOT_PASSWORD=secure-root-password
      - MYSQL_PASSWORD=secure-app-password
    volumes:
      - mariadb_data:/var/lib/mysql

volumes:
  mariadb_data:
```

## 🔧 Manual Installation

### Prerequisites

- **Python**: 3.12+ (required)
- **Database**: MariaDB 11.4+ (recommended) or MySQL 8.0+
- **Media Processing**: FFmpeg (required for video processing)
- **Operating System**: Linux, macOS, or Windows

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
sudo apt install mariadb-server mariadb-client
sudo apt install ffmpeg
sudo apt install build-essential pkg-config default-libmysqlclient-dev
```

**CentOS/RHEL:**
```bash
sudo yum install python3.12 python3.12-venv python3-pip
sudo yum install mariadb-server mariadb
sudo yum install ffmpeg
sudo yum install gcc gcc-c++ pkgconfig mysql-devel
```

**macOS:**
```bash
brew install python@3.12
brew install mariadb
brew install ffmpeg
brew install pkg-config mysql-client
```

### Database Setup

1. **Install and start MariaDB:**
```bash
sudo systemctl start mariadb
sudo systemctl enable mariadb
sudo mysql_secure_installation
```

2. **Create database and user:**
```sql
CREATE DATABASE mvidarr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mvidarr'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON mvidarr.* TO 'mvidarr'@'localhost';
FLUSH PRIVILEGES;
```

### Application Installation

1. **Clone the repository:**
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
```

2. **Create virtual environment:**
```bash
python3.12 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

3. **Install dependencies:**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database:**
```bash
python -c "
from src.database.init_db import initialize_database
if initialize_database():
    print('✅ Database initialized successfully')
else:
    print('❌ Database initialization failed')
"
```

6. **Start the application:**
```bash
python app.py
```

**Access:** `http://localhost:5000`

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with your configuration:

```bash
# Database Configuration
DB_HOST=localhost
DB_NAME=mvidarr
DB_USER=mvidarr
DB_PASSWORD=secure_password
DB_PORT=3306

# Application Configuration
SECRET_KEY=your-super-secret-key-here
FLASK_ENV=production
PORT=5000
HOST=0.0.0.0

# API Keys (Optional but recommended)
IMVDB_API_KEY=your-imvdb-api-key
YOUTUBE_API_KEY=your-youtube-api-key

# Media Processing
DOWNLOADS_PATH=data/downloads
MUSIC_VIDEOS_PATH=data/musicvideos
THUMBNAILS_PATH=data/thumbnails

# Security Settings
REQUIRE_AUTHENTICATION=true
SESSION_TIMEOUT=24
MAX_LOGIN_ATTEMPTS=5
```

### Directory Structure

Ensure these directories exist and have proper permissions:

```bash
mkdir -p data/{downloads,musicvideos,thumbnails,logs,cache,backups,database}
mkdir -p config
chmod 755 data/
chmod 750 config/
```

## 🛡️ Security Configuration

### Default Credentials

**⚠️ IMPORTANT**: Change default credentials immediately after installation:

- **Default Username**: `admin`
- **Default Password**: `mvidarr` (for simple auth) or `MVidarr@P4ss!` (for user auth)

### User Management

Create additional users through the web interface or using the management commands:

```bash
python -c "
from src.database.models import User, UserRole
from src.database.connection import get_db

with get_db() as session:
    user = User(
        username='your_username',
        email='your_email@example.com',
        password='SecurePassword123!',
        role=UserRole.USER
    )
    session.add(user)
    session.commit()
    print('User created successfully')
"
```

## 🔍 Verification

### System Health Check

After installation, verify everything is working:

1. **Database Connection**: Check the System Health page in the web interface
2. **Media Processing**: Verify FFmpeg is detected
3. **API Integration**: Test IMVDB and YouTube API connections (if configured)
4. **File Permissions**: Ensure data directories are writable

### Performance Optimization

For production deployments:

- **Use a reverse proxy** (nginx, Apache) for SSL termination
- **Configure log rotation** for application logs  
- **Set up monitoring** for system resources
- **Regular backups** of database and configuration

## 🆙 Updating

### Docker Updates

```bash
# Pull latest image
docker pull ghcr.io/prefect421/mvidarr:latest

# Restart containers
docker-compose down
docker-compose up -d
```

### Manual Updates

```bash
# Backup database first
mysqldump -u mvidarr -p mvidarr > backup-$(date +%Y%m%d).sql

# Update code
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Run any database migrations
python -c "from src.database.init_db import initialize_database; initialize_database()"

# Restart application
sudo systemctl restart mvidarr  # if using systemd
```

## 📞 Support

- **Installation Issues**: Check our [troubleshooting guide]({{ site.github.repository_url }}/blob/main/docs/TROUBLESHOOTING.md)
- **Configuration Help**: See our [configuration documentation]({{ site.github.repository_url }}/blob/main/docs/CONFIGURATION.md)
- **Community Support**: Join our [GitHub Discussions]({{ site.github.repository_url }}/discussions)
- **Bug Reports**: Submit [GitHub Issues]({{ site.github.repository_url }}/issues)

---

Need help? Don't hesitate to ask in our [community discussions]({{ site.github.repository_url }}/discussions)!