#!/bin/bash
# Fix logs directory permissions in Docker container
# This ensures mvidarr user can write logs even with volume mounts

LOGS_DIR="/app/data/logs"

if [ -d "$LOGS_DIR" ]; then
    echo "Fixing permissions for $LOGS_DIR"
    chown -R mvidarr:mvidarr "$LOGS_DIR" 2>/dev/null || true
    chmod -R 755 "$LOGS_DIR" 2>/dev/null || true
    echo "Permissions fixed"
else
    echo "Creating $LOGS_DIR"
    mkdir -p "$LOGS_DIR"
    chown -R mvidarr:mvidarr "$LOGS_DIR"
    chmod -R 755 "$LOGS_DIR"
fi
