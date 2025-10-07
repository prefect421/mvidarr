FROM alpine:3.18

# Install required packages
RUN apk add --no-cache \
    bash \
    curl \
    mysql-client \
    docker-cli \
    tar \
    gzip \
    coreutils \
    python3 \
    py3-pip \
    && pip3 install --no-cache-dir schedule

# Create backup user
RUN adduser -D -s /bin/bash backup

# Set working directory
WORKDIR /app

# Copy backup scripts
COPY docker/backup/backup.sh /app/backup.sh
COPY docker/backup/restore.sh /app/restore.sh
COPY docker/backup/scheduler.py /app/scheduler.py

# Make scripts executable
RUN chmod +x /app/backup.sh /app/restore.sh

# Change ownership
RUN chown -R backup:backup /app

# Switch to non-root user
USER backup

# Health check
HEALTHCHECK --interval=300s --timeout=30s --start-period=60s --retries=3 \
    CMD test -f /app/backups/last_backup.txt && [ $(($(date +%s) - $(cat /app/backups/last_backup.txt))) -lt 86400 ] || exit 1

# Run scheduler
CMD ["python3", "scheduler.py"]