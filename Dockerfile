# Dockerfile for MVidarr FastAPI Application
# Supports Phase 2 background job processing with FFmpeg

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ffprobe \
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-fastapi.txt requirements-phase2.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-fastapi.txt && \
    pip install --no-cache-dir -r requirements-phase2.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/downloads /app/data/musicvideos

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden in docker-compose)
CMD ["python", "fastapi_app.py"]