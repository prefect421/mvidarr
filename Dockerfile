# Dockerfile for MVidarr FastAPI Application
# Version: 0.9.9 - Production-Ready Release
# Supports background job processing with Celery + Redis + FFmpeg

FROM python:3.12-slim

# Install system dependencies including supervisord for process management
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ffprobe \
    curl \
    procps \
    supervisor \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create mvidarr user for running processes
RUN useradd -m -u 1000 -s /bin/bash mvidarr

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/downloads /app/data/musicvideos /app/data/logs \
    && chown -R mvidarr:mvidarr /app/data /app/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Default command - run supervisord to manage FastAPI + Celery
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]