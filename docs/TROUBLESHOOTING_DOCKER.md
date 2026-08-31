# MVidarr Docker Troubleshooting Guide

## Overview

This guide provides comprehensive troubleshooting solutions for common Docker-related issues when deploying and running MVidarr. It covers installation problems, runtime issues, performance concerns, and configuration challenges.

## 🚀 Installation and Setup Issues

### Docker Installation Problems

#### Docker Not Installed or Not Running
```bash
# Check if Docker is installed
docker --version

# Check if Docker daemon is running
sudo systemctl status docker

# Start Docker service
sudo systemctl start docker

# Enable Docker to start on boot
sudo systemctl enable docker
```

**Common Solutions:**
- **Ubuntu/Debian**: `sudo apt-get update && sudo apt-get install docker.io docker-compose`
- **CentOS/RHEL**: `sudo yum install docker docker-compose`
- **macOS**: Download Docker Desktop from docker.com
- **Windows**: Install Docker Desktop with WSL2 support

#### Permission Issues
```bash
# Add user to docker group (avoid using sudo with docker)
sudo usermod -aG docker $USER

# Log out and back in, or use:
newgrp docker

# Test docker without sudo
docker ps
```

### Docker Compose Issues

#### docker-compose Command Not Found
```bash
# Install docker-compose via pip
pip3 install docker-compose

# Or download binary directly
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker-compose --version
```

#### Docker Compose File Syntax Errors
```bash
# Validate docker-compose.yml syntax
docker-compose config

# Check for common YAML formatting issues:
# - Incorrect indentation (use spaces, not tabs)
# - Missing quotes around values with special characters
# - Incorrect port mapping format
```

**Example of correct docker-compose.yml format:**
```yaml
version: '3.8'
services:
  mvidarr:
    image: mvidarr:latest
    ports:
      - "5001:5001"
    volumes:
      - "./config:/app/config"
      - "./videos:/app/videos"
    environment:
      - MVIDARR_DEBUG=false
```

## 🔄 Container Runtime Issues

### Container Won't Start

#### Check Container Logs
```bash
# View recent logs
docker logs mvidarr-app

# Follow live logs
docker logs -f mvidarr-app

# Get last 50 lines
docker logs --tail 50 mvidarr-app

# Include timestamps
docker logs -t mvidarr-app
```

#### Common Startup Failures

**Port Already in Use:**
```bash
# Check what's using port 5001
sudo netstat -tulpn | grep 5001
# or
sudo lsof -i :5001

# Kill process using the port
sudo kill -9 <PID>

# Or change port in docker-compose.yml
ports:
  - "5002:5001"  # Use different external port
```

**Permission Issues with Volumes:**
```bash
# Fix volume permissions
sudo chown -R 1000:1000 /path/to/mvidarr/data
sudo chmod -R 755 /path/to/mvidarr/data

# Check current permissions
ls -la /path/to/mvidarr/data
```

**Database Issues:**
```bash
# Check if database file exists and is writable
ls -la /path/to/database/mvidarr.db

# Fix database permissions
sudo chown 1000:1000 /path/to/database/mvidarr.db
sudo chmod 664 /path/to/database/mvidarr.db
```

### Container Keeps Restarting

#### Check Exit Codes
```bash
# Get container exit code
docker ps -a | grep mvidarr-app

# Inspect container for exit code
docker inspect mvidarr-app --format='{{.State.ExitCode}}'
```

**Common Exit Codes:**
- **125**: Docker daemon error
- **126**: Container command not executable
- **127**: Container command not found
- **130**: Container stopped by SIGINT (Ctrl+C)

#### Memory Issues
```bash
# Check container memory usage
docker stats mvidarr-app --no-stream

# Increase memory limit in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
    reservations:
      memory: 512M
```

## 🌐 Network and Connectivity Issues

### Can't Access Web Interface

#### Check Container Network
```bash
# Check if container is running
docker ps | grep mvidarr

# Check port mapping
docker port mvidarr-app

# Test internal connectivity
docker exec mvidarr-app curl -f http://localhost:5001/health
```

#### Firewall Issues
```bash
# Check firewall status (Ubuntu)
sudo ufw status

# Allow port through firewall
sudo ufw allow 5001

# For CentOS/RHEL
sudo firewall-cmd --permanent --add-port=5001/tcp
sudo firewall-cmd --reload
```

#### Docker Network Problems
```bash
# Inspect Docker networks
docker network ls

# Check container network settings
docker inspect mvidarr-app | grep -A 20 NetworkSettings

# Recreate network if needed
docker-compose down
docker network prune
docker-compose up -d
```

### API Connectivity Issues

#### External API Access Problems
```bash
# Test connectivity from within container
docker exec mvidarr-app ping -c 3 api.imvdb.com
docker exec mvidarr-app curl -I https://api.imvdb.com

# Check DNS resolution
docker exec mvidarr-app nslookup api.imvdb.com

# Test YouTube API connectivity
docker exec mvidarr-app curl -I https://www.googleapis.com/youtube/v3/
```

#### Proxy/Corporate Network Issues
```bash
# Configure proxy in docker-compose.yml
environment:
  - HTTP_PROXY=http://proxy.company.com:8080
  - HTTPS_PROXY=http://proxy.company.com:8080
  - NO_PROXY=localhost,127.0.0.1,docker-internal

# Or configure Docker daemon proxy
# Edit /etc/systemd/system/docker.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=http://proxy.company.com:8080"
Environment="HTTPS_PROXY=http://proxy.company.com:8080"
```

## 💾 Storage and Volume Issues

### Volume Mount Problems

#### Permission Denied Errors
```bash
# Check volume mount points
docker inspect mvidarr-app | grep -A 10 Mounts

# Fix ownership of mounted directories
sudo chown -R $(id -u):$(id -g) /path/to/volumes

# Set proper permissions
sudo chmod -R 755 /path/to/config
sudo chmod -R 755 /path/to/videos
```

#### Volume Not Mounting
```bash
# Verify paths exist on host
ls -la /path/to/host/directory

# Check docker-compose.yml volume syntax
volumes:
  - "/absolute/path/on/host:/path/in/container"
  - "./relative/path:/path/in/container"
  - "named_volume:/path/in/container"
```

### Disk Space Issues

#### Container Out of Space
```bash
# Check Docker disk usage
docker system df

# Clean up unused resources
docker system prune -a

# Remove unused volumes
docker volume prune

# Check available space in containers
docker exec mvidarr-app df -h
```

#### Log Files Growing Too Large
```bash
# Check container log size
du -sh $(docker inspect --format='{{.LogPath}}' mvidarr-app)

# Configure log rotation in docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

# Or configure globally in /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

## 🔧 Performance Issues

### Slow Performance

#### Resource Constraints
```bash
# Monitor real-time resource usage
docker stats mvidarr-app

# Check system resources
htop
free -h
df -h

# Increase resource limits
# In docker-compose.yml:
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 4G
```

#### I/O Performance Issues
```bash
# Check I/O statistics
iostat -x 1 5

# Test disk performance
docker exec mvidarr-app dd if=/dev/zero of=/tmp/test bs=1M count=1000

# Use faster storage for volumes
# Consider SSD storage for database and config
volumes:
  - "/fast/ssd/path:/app/database"
  - "/regular/storage:/app/videos"
```

### Database Performance Problems

#### Database Locks
```bash
# Check for database lock files
docker exec mvidarr-app ls -la /app/database/

# Stop container and remove lock files if safe
docker-compose stop
sudo rm /path/to/database/*.db-wal /path/to/database/*.db-shm
docker-compose start
```

#### Database Corruption
```bash
# Check database integrity
docker exec mvidarr-app sqlite3 /app/database/mvidarr.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
docker-compose stop
cp /path/to/backup/mvidarr.db /path/to/current/mvidarr.db
docker-compose start
```

## 🔐 Security and Access Issues

### SSL/TLS Issues

#### Certificate Problems
```bash
# Check certificate validity
openssl x509 -in /path/to/certificate.crt -text -noout

# Test SSL connection
openssl s_client -connect yourdomain.com:443 -verify_return_error
```

#### Reverse Proxy Issues
Common nginx configuration for MVidarr:
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Authentication Issues

#### Login Problems
```bash
# Check authentication logs
docker logs mvidarr-app | grep -i auth

# Reset admin password (if supported)
docker exec -it mvidarr-app python -c "from src.utils.auth import reset_admin_password; reset_admin_password()"

# Verify user database
docker exec mvidarr-app sqlite3 /app/database/mvidarr.db ".tables" | grep -i user
```

## 🛠️ Advanced Troubleshooting

### Container Debugging

#### Interactive Shell Access
```bash
# Access container shell
docker exec -it mvidarr-app /bin/bash

# Or if bash not available
docker exec -it mvidarr-app /bin/sh

# Run commands directly
docker exec mvidarr-app ps aux
docker exec mvidarr-app netstat -tulpn
```

#### Process Investigation
```bash
# Check running processes in container
docker exec mvidarr-app ps aux

# Check system calls (Linux only)
docker exec mvidarr-app strace -p <PID>

# Monitor file access
docker exec mvidarr-app lsof -p <PID>
```

### Docker Daemon Issues

#### Docker Daemon Won't Start
```bash
# Check daemon status
sudo systemctl status docker

# View daemon logs
sudo journalctl -u docker.service

# Restart Docker daemon
sudo systemctl restart docker

# Check for corrupted Docker files
sudo rm -rf /var/lib/docker/network/*
sudo systemctl restart docker
```

#### Docker Storage Issues
```bash
# Check Docker root directory
docker info | grep "Docker Root Dir"

# Clean up Docker data
sudo systemctl stop docker
sudo rm -rf /var/lib/docker
sudo systemctl start docker

# Recreate containers
docker-compose up -d
```

## 🆘 Emergency Recovery Procedures

### Complete Container Reset
```bash
# Stop and remove everything
docker-compose down -v

# Remove all MVidarr-related containers
docker rm $(docker ps -a -q -f ancestor=mvidarr)

# Remove MVidarr images
docker rmi mvidarr:latest

# Clean system
docker system prune -a

# Rebuild and restart
docker-compose up --build -d
```

### Data Recovery
```bash
# Backup current state before recovery
docker exec mvidarr-app tar czf /tmp/backup.tar.gz /app/database /app/config

# Copy backup out of container
docker cp mvidarr-app:/tmp/backup.tar.gz ./emergency-backup.tar.gz

# Restore from known good backup
docker cp ./good-backup.tar.gz mvidarr-app:/tmp/
docker exec mvidarr-app tar xzf /tmp/good-backup.tar.gz -C /
```

## 📋 Diagnostic Checklist

### Quick Health Check
- [ ] Container is running (`docker ps`)
- [ ] Logs show no errors (`docker logs mvidarr-app`)
- [ ] Web interface accessible (`curl http://localhost:5001`)
- [ ] Database is accessible
- [ ] Sufficient disk space
- [ ] Network connectivity to external APIs

### Performance Check
- [ ] CPU usage < 80%
- [ ] Memory usage < 80%
- [ ] Disk I/O reasonable
- [ ] Response times acceptable
- [ ] No resource leaks

### Security Check
- [ ] Only necessary ports exposed
- [ ] Volumes have proper permissions
- [ ] No sensitive data in logs
- [ ] Authentication working
- [ ] SSL/TLS configured properly

## 🔗 Additional Resources

- **Official Docker Documentation**: https://docs.docker.com/
- **Docker Compose Reference**: https://docs.docker.com/compose/
- **MVidarr Installation Guide**: See `installation.md`
- **System Monitoring**: See `MONITORING.md`
- **General Troubleshooting**: See `TROUBLESHOOTING.md`

## 📞 Getting Help

When reporting Docker issues:

1. **Include Environment Info**:
   ```bash
   docker --version
   docker-compose --version
   uname -a
   ```

2. **Gather Logs**:
   ```bash
   docker logs mvidarr-app > docker-logs.txt
   docker-compose logs > compose-logs.txt
   ```

3. **System Information**:
   ```bash
   docker info > docker-info.txt
   docker system df > docker-df.txt
   ```

4. **Configuration Files**:
   - docker-compose.yml
   - Any custom Docker configurations
   - Network and storage setup details

This troubleshooting guide should resolve most Docker-related issues with MVidarr deployments. For issues not covered here, consider consulting the broader MVidarr documentation or community resources.