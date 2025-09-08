#!/bin/bash
# MVidarr Backup Script for Self-Hosted Deployments

set -e

# Configuration
BACKUP_DIR="/app/backups"
DATA_DIR="/app/data"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="mvidarr_backup_${TIMESTAMP}"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Create backup directory
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

log "Starting MVidarr backup: ${BACKUP_NAME}"

# Backup database
log "Backing up database..."
if ! mysqldump -h mvidarr-database -u root -p${MYSQL_ROOT_PASSWORD} \
    --single-transaction \
    --routines \
    --triggers \
    --all-databases \
    > "${BACKUP_DIR}/${BACKUP_NAME}/database.sql"; then
    error "Database backup failed"
fi

log "Database backup completed"

# Backup media files
log "Backing up media files..."
if [ -d "${DATA_DIR}/media" ]; then
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/media.tar.gz" \
        -C "${DATA_DIR}" media/ || warn "Media backup had warnings"
else
    warn "Media directory not found, skipping"
fi

# Backup thumbnails
log "Backing up thumbnails..."
if [ -d "${DATA_DIR}/thumbnails" ]; then
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/thumbnails.tar.gz" \
        -C "${DATA_DIR}" thumbnails/ || warn "Thumbnails backup had warnings"
else
    warn "Thumbnails directory not found, skipping"
fi

# Backup configuration files
log "Backing up configuration..."
CONFIG_FILES=(
    "docker-compose.yml"
    "docker-compose.selfhosted.yml"
    ".env"
    "version.json"
)

mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}/config"
for config_file in "${CONFIG_FILES[@]}"; do
    if [ -f "${DATA_DIR}/${config_file}" ]; then
        cp "${DATA_DIR}/${config_file}" "${BACKUP_DIR}/${BACKUP_NAME}/config/" || warn "Failed to backup ${config_file}"
    fi
done

# Backup logs (last 7 days)
log "Backing up recent logs..."
if [ -d "${DATA_DIR}/logs" ]; then
    find "${DATA_DIR}/logs" -name "*.log" -mtime -7 | \
        tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/logs.tar.gz" \
        -T - || warn "Logs backup had warnings"
else
    warn "Logs directory not found, skipping"
fi

# Create backup manifest
log "Creating backup manifest..."
cat > "${BACKUP_DIR}/${BACKUP_NAME}/manifest.json" << EOF
{
    "backup_name": "${BACKUP_NAME}",
    "timestamp": "${TIMESTAMP}",
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)",
    "version": "$(cat ${DATA_DIR}/version.json 2>/dev/null | jq -r '.version' || echo 'unknown')",
    "backup_type": "full",
    "retention_days": ${RETENTION_DAYS},
    "components": {
        "database": "$([ -f "${BACKUP_DIR}/${BACKUP_NAME}/database.sql" ] && echo "included" || echo "missing")",
        "media": "$([ -f "${BACKUP_DIR}/${BACKUP_NAME}/media.tar.gz" ] && echo "included" || echo "missing")",
        "thumbnails": "$([ -f "${BACKUP_DIR}/${BACKUP_NAME}/thumbnails.tar.gz" ] && echo "included" || echo "missing")",
        "config": "included",
        "logs": "$([ -f "${BACKUP_DIR}/${BACKUP_NAME}/logs.tar.gz" ] && echo "included" || echo "missing")"
    },
    "size_mb": $(du -sm "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)
}
EOF

# Calculate checksums
log "Calculating checksums..."
find "${BACKUP_DIR}/${BACKUP_NAME}" -type f -exec sha256sum {} \; > "${BACKUP_DIR}/${BACKUP_NAME}/checksums.sha256"

# Create compressed backup
log "Compressing backup..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" "${BACKUP_NAME}"

# Remove uncompressed backup directory
rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

# Update last backup timestamp
echo "$(date +%s)" > "${BACKUP_DIR}/last_backup.txt"

# Backup size info
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
log "Backup completed: ${BACKUP_NAME}.tar.gz (${BACKUP_SIZE})"

# Cleanup old backups
log "Cleaning up old backups (keeping ${RETENTION_DAYS} days)..."
find "${BACKUP_DIR}" -name "mvidarr_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete || warn "Cleanup had warnings"

# List current backups
log "Current backups:"
ls -lh "${BACKUP_DIR}"/mvidarr_backup_*.tar.gz 2>/dev/null | head -5 || info "No backups found"

# Create backup report
cat > "${BACKUP_DIR}/backup_report.json" << EOF
{
    "last_backup": {
        "name": "${BACKUP_NAME}",
        "timestamp": "${TIMESTAMP}",
        "size": "${BACKUP_SIZE}",
        "status": "completed",
        "duration_seconds": $SECONDS
    },
    "retention_days": ${RETENTION_DAYS},
    "next_scheduled": "$(date -d '+1 day' +%Y-%m-%d)",
    "backup_count": $(ls -1 "${BACKUP_DIR}"/mvidarr_backup_*.tar.gz 2>/dev/null | wc -l)
}
EOF

log "Backup process completed successfully in ${SECONDS} seconds"

# Send notification if configured
if [ -n "${DISCORD_WEBHOOK}" ]; then
    curl -H "Content-Type: application/json" \
         -d "{\"embeds\":[{\"title\":\"✅ MVidarr Backup Completed\",\"description\":\"Backup ${BACKUP_NAME} completed successfully\\nSize: ${BACKUP_SIZE}\\nDuration: ${SECONDS}s\",\"color\":3066993}]}" \
         "${DISCORD_WEBHOOK}" &>/dev/null || warn "Discord notification failed"
fi