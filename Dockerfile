# Dockerfile for MVidarr FastAPI Application
# Version: 0.9.9 - Production-Ready Release
# Supports background job processing with Celery + Redis + FFmpeg

FROM python:3.14-slim

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

# Install Node.js from official binaries. Node >=22 is REQUIRED (not just
# recommended): yt-dlp's own JS challenge solver (NodeJsRuntime) hardcodes
# MIN_SUPPORTED_VERSION = (22, 0, 0) and refuses older runtimes outright,
# and the bgutil-ytdlp-pot-provider server below (package.json "engines")
# requires the same floor -- confirmed live on 2026-08-25 that v20.18.1
# is rejected by both ("node (unavailable)" / ERR_REQUIRE_ESM crash),
# while v22.23.2 (LTS "Jod") resolves full-quality formats end-to-end.
# SHA256 verified against https://nodejs.org/dist/v22.23.2/SHASUMS256.txt --
# when bumping this version, fetch the new SHASUMS256.txt and update the
# hash below; a mismatch fails the build rather than installing silently.
RUN curl -fsSL https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz -o /tmp/node.tar.xz \
    && echo "d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307  /tmp/node.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version && npm --version

# Build the bgutil-ytdlp-pot-provider PO token server (#452): generates the
# Proof-of-Origin tokens yt-dlp needs to bypass YouTube's SABR/bot-detection
# gating on age-restricted and otherwise-protected videos. The Python
# client plugin (bgutil-ytdlp-pot-provider) is already installed via
# requirements.txt -- it was the client half only; this is its companion
# HTTP server. Run by supervisord below, reachable at the plugin's default
# http://127.0.0.1:4416 with zero yt-dlp invocation changes needed. Pinned
# to the same 1.3.2 release as the installed Python plugin. SHA256 pinned
# below (GitHub's tag archive is otherwise a mutable ref, not an immutable
# release asset) -- recompute with `curl -fsSL <url> | sha256sum` when
# bumping the version; a mismatch fails the build.
RUN mkdir -p /app/vendor/bgutil-ytdlp-pot-provider \
    && curl -fsSL https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/1.3.2.tar.gz -o /tmp/pot-provider.tar.gz \
    && echo "3545ac7ffc0869498755cb3b4760a72fa2f176689d0890a6f5b898d163012ba2  /tmp/pot-provider.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/pot-provider.tar.gz -C /app/vendor/bgutil-ytdlp-pot-provider --strip-components=1 \
    && rm /tmp/pot-provider.tar.gz \
    && cd /app/vendor/bgutil-ytdlp-pot-provider/server \
    && npm ci --no-audit --no-fund \
    && npx tsc \
    && npm prune --omit=dev

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-fastapi.txt ./

# Install Python dependencies (both Flask/core and FastAPI)
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt -r requirements-fastapi.txt

# py-spy (#457): a live process got fully unresponsive with no stack
# trace to diagnose why -- this lets a running container's process be
# sampled in place (`py-spy dump --pid <pid>`) without killing it.
# Needs SYS_PTRACE (see docker-compose.dev.yml's cap_add) to attach to
# another process in the same container. Small, inert unless invoked --
# left in unconditionally rather than split into a dev-only image.
RUN pip install --no-cache-dir py-spy

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