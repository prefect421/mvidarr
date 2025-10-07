#!/bin/bash
# MVidarr Restore Script for Self-Hosted Deployments

set -e

# Configuration
BACKUP_DIR="/app/backups"
DATA_DIR="/app/data"

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

usage() {
    cat << EOF
Usage: $0 [OPTIONS] <backup_name>

OPTIONS:
    -d, --database-only     Restore only database
    -m, --media-only        Restore only media files
    -c, --config-only       Restore only configuration
    -f, --force            Skip confirmation prompts
    -l, --list             List available backups
    -h, --help             Show this help

EXAMPLES:
    $0 -l                                    # List backups
    $0 mvidarr_backup_20241201_120000        # Full restore
    $0 -d mvidarr_backup_20241201_120000     # Database only
    $0 -f mvidarr_backup_20241201_120000     # Skip confirmations
    
EOF
}

list_backups() {
    log "Available backups:"
    if ls "${BACKUP_DIR}"/mvidarr_backup_*.tar.gz >/dev/null 2>&1; then
        for backup in "${BACKUP_DIR}"/mvidarr_backup_*.tar.gz; do
            backup_name=$(basename "${backup}" .tar.gz)
            backup_size=$(du -sh "${backup}" | cut -f1)
            backup_date=$(echo "${backup_name}" | grep -o '[0-9]\{8\}_[0-9]\{6\}' | sed 's/_/ /')
            echo "  📦 ${backup_name} (${backup_size}) - ${backup_date}"
        done
    else
        warn "No backups found in ${BACKUP_DIR}"
    fi
}

verify_backup() {
    local backup_file="$1"
    local temp_dir="$2"
    
    log "Verifying backup integrity..."
    
    if [ ! -f "${backup_file}" ]; then
        error "Backup file not found: ${backup_file}"
    fi
    
    # Extract backup
    if ! tar -xzf "${backup_file}" -C "${temp_dir}"; then
        error "Failed to extract backup file"
    fi
    
    local backup_name=$(basename "${backup_file}" .tar.gz)
    local extract_dir="${temp_dir}/${backup_name}"
    
    # Verify checksums if available
    if [ -f "${extract_dir}/checksums.sha256" ]; then
        log "Verifying checksums..."
        if ! (cd "${extract_dir}" && sha256sum -c checksums.sha256 --quiet); then
            error "Backup integrity check failed"
        fi
        log "Backup integrity verified"
    else
        warn "No checksums found, skipping integrity check"
    fi
    
    # Check manifest
    if [ -f "${extract_dir}/manifest.json" ]; then
        log "Backup manifest:"
        cat "${extract_dir}/manifest.json" | python3 -m json.tool 2>/dev/null || cat "${extract_dir}/manifest.json"
    fi
    
    echo "${extract_dir}"
}

restore_database() {
    local extract_dir="$1"
    
    if [ ! -f "${extract_dir}/database.sql" ]; then
        warn "Database backup not found, skipping"
        return
    fi
    
    log "Restoring database..."
    
    # Stop application temporarily
    warn "Stopping MVidarr application for database restore..."
    docker stop mvidarr-app || warn "Failed to stop mvidarr-app"
    
    # Wait for connections to close
    sleep 5
    
    # Restore database
    if mysql -h mvidarr-database -u root -p${MYSQL_ROOT_PASSWORD} < "${extract_dir}/database.sql"; then
        log "Database restored successfully"
    else
        error "Database restore failed"
    fi
    
    # Restart application
    log "Restarting MVidarr application..."
    docker start mvidarr-app || error "Failed to restart mvidarr-app"
}

restore_media() {
    local extract_dir="$1"
    
    if [ -f "${extract_dir}/media.tar.gz" ]; then
        log "Restoring media files..."
        
        # Backup existing media
        if [ -d "${DATA_DIR}/media" ]; then
            mv "${DATA_DIR}/media" "${DATA_DIR}/media.backup.$(date +%s)" || warn "Failed to backup existing media"
        fi
        
        # Restore media
        if tar -xzf "${extract_dir}/media.tar.gz" -C "${DATA_DIR}"; then
            log "Media files restored successfully"
        else
            error "Media restore failed"
        fi
    else
        warn "Media backup not found, skipping"
    fi
    
    if [ -f "${extract_dir}/thumbnails.tar.gz" ]; then
        log "Restoring thumbnails..."
        
        # Backup existing thumbnails
        if [ -d "${DATA_DIR}/thumbnails" ]; then
            mv "${DATA_DIR}/thumbnails" "${DATA_DIR}/thumbnails.backup.$(date +%s)" || warn "Failed to backup existing thumbnails"
        fi
        
        # Restore thumbnails
        if tar -xzf "${extract_dir}/thumbnails.tar.gz" -C "${DATA_DIR}"; then
            log "Thumbnails restored successfully"
        else
            warn "Thumbnails restore failed"
        fi
    else
        warn "Thumbnails backup not found, skipping"
    fi
}

restore_config() {
    local extract_dir="$1"
    
    if [ -d "${extract_dir}/config" ]; then
        log "Restoring configuration..."
        
        # Restore configuration files
        for config_file in "${extract_dir}/config"/*; do
            if [ -f "${config_file}" ]; then
                filename=$(basename "${config_file}")
                if [ -f "${DATA_DIR}/${filename}" ]; then
                    cp "${DATA_DIR}/${filename}" "${DATA_DIR}/${filename}.backup.$(date +%s)" || warn "Failed to backup ${filename}"
                fi
                cp "${config_file}" "${DATA_DIR}/" && log "Restored ${filename}" || warn "Failed to restore ${filename}"
            fi
        done
    else
        warn "Configuration backup not found, skipping"
    fi
}

# Parse command line arguments
DATABASE_ONLY=false
MEDIA_ONLY=false
CONFIG_ONLY=false
FORCE=false
LIST_BACKUPS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--database-only)
            DATABASE_ONLY=true
            shift
            ;;
        -m|--media-only)
            MEDIA_ONLY=true
            shift
            ;;
        -c|--config-only)
            CONFIG_ONLY=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -l|--list)
            LIST_BACKUPS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            error "Unknown option: $1"
            ;;
        *)
            BACKUP_NAME="$1"
            shift
            ;;
    esac
done

# List backups and exit
if [ "$LIST_BACKUPS" = true ]; then
    list_backups
    exit 0
fi

# Check if backup name provided
if [ -z "$BACKUP_NAME" ]; then
    error "Backup name required. Use -l to list available backups."
fi

# Construct backup file path
BACKUP_FILE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

# Verify and extract backup
EXTRACT_DIR=$(verify_backup "${BACKUP_FILE}" "${TEMP_DIR}")

# Confirmation
if [ "$FORCE" != true ]; then
    warn "This will restore MVidarr from backup: ${BACKUP_NAME}"
    warn "Current data may be overwritten!"
    read -p "Do you want to continue? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Restore cancelled"
        exit 0
    fi
fi

log "Starting restore process..."

# Perform restore based on options
if [ "$DATABASE_ONLY" = true ]; then
    restore_database "${EXTRACT_DIR}"
elif [ "$MEDIA_ONLY" = true ]; then
    restore_media "${EXTRACT_DIR}"
elif [ "$CONFIG_ONLY" = true ]; then
    restore_config "${EXTRACT_DIR}"
else
    # Full restore
    restore_database "${EXTRACT_DIR}"
    restore_media "${EXTRACT_DIR}"
    restore_config "${EXTRACT_DIR}"
fi

log "Restore completed successfully!"

# Send notification if configured
if [ -n "${DISCORD_WEBHOOK}" ]; then
    curl -H "Content-Type: application/json" \
         -d "{\"embeds\":[{\"title\":\"✅ MVidarr Restore Completed\",\"description\":\"Restore from ${BACKUP_NAME} completed successfully\\nDuration: ${SECONDS}s\",\"color\":3066993}]}" \
         "${DISCORD_WEBHOOK}" &>/dev/null || warn "Discord notification failed"
fi

info "Please verify your MVidarr installation is working correctly"