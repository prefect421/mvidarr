# Dockerfile for MVidarr FastAPI Application
# Version: 0.9.9 - Production-Ready Release
# Supports background job processing with Celery + Redis + FFmpeg

FROM python:3.12-slim

# Install system dependencies including supervisord for process management
# xz-utils is REQUIRED for extracting Node.js .tar.xz files
RUN apt-get update && apt-get install -y \
    xz-utils \
    ffmpeg \
    curl \
    procps \
    supervisor \
    netcat-openbsd \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    ca-certificates \
    gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js from official binaries (required for yt-dlp JavaScript runtime)
RUN curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version && npm --version

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-fastapi.txt ./

# Install Python dependencies (both Flask/core and FastAPI)
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt -r requirements-fastapi.txt

# Copy application code
COPY . .

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy and setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create mvidarr user for running processes
RUN useradd -m -u 1000 -s /bin/bash mvidarr

# Create necessary directories and set proper permissions for entire app directory
RUN mkdir -p /app/logs /app/downloads /app/data/musicvideos /app/data/logs /app/data/cookies \
    && chown -R mvidarr:mvidarr /app \
    && find /app -type d -exec chmod 755 {} \; \
    && find /app -type f -exec chmod 644 {} \; \
    && chmod 755 /app/fastapi_app.py

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Use entrypoint script to handle setup and start supervisord
ENTRYPOINT ["/entrypoint.sh"]