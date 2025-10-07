FROM python:3.11-alpine

# Install required packages
RUN apk add --no-cache \
    curl \
    docker-cli \
    && pip install --no-cache-dir \
    requests \
    docker \
    schedule \
    psutil

# Create app user
RUN adduser -D -s /bin/sh monitor

# Set working directory
WORKDIR /app

# Copy monitor script
COPY docker/monitor/monitor.py /app/monitor.py
COPY docker/monitor/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Change ownership
RUN chown -R monitor:monitor /app

# Switch to non-root user
USER monitor

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)"

# Run monitor
CMD ["python", "monitor.py"]