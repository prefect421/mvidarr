#!/bin/bash
# MVidarr Self-Hosted Deployment Script
# Simple deployment automation for self-hosting enthusiasts

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_DIR}/.env"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.selfhosted.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
ENABLE_MONITORING=true
ENABLE_BACKUP=true
ENABLE_PROXY=false
ENABLE_AUTO_UPDATE=false
QUICK_SETUP=false
UPDATE_MODE=false

# Helper functions
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

header() {
    echo -e "${CYAN}"
    echo "============================================="
    echo "$1"
    echo "============================================="
    echo -e "${NC}"
}

usage() {
    cat << EOF
MVidarr Self-Hosted Deployment Script

Usage: $0 [OPTIONS]

OPTIONS:
    -q, --quick            Quick setup with defaults
    -u, --update           Update existing deployment
    --no-monitoring        Disable monitoring service
    --no-backup            Disable backup service
    --enable-proxy         Enable nginx proxy (for SSL/domains)
    --enable-auto-update   Enable automatic updates
    -h, --help             Show this help

EXAMPLES:
    $0                     # Interactive setup
    $0 -q                  # Quick setup with defaults
    $0 -u                  # Update existing deployment
    $0 --enable-proxy      # Setup with nginx proxy for SSL

EOF
}

generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

check_prerequisites() {
    header "Checking Prerequisites"
    
    local missing_tools=()
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    else
        info "✓ Docker found: $(docker --version | cut -d' ' -f3 | cut -d',' -f1)"
        
        # Check if Docker is running
        if ! docker info &> /dev/null; then
            error "Docker is not running. Please start Docker and try again."
        fi
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        missing_tools+=("docker-compose")
    else
        if command -v docker-compose &> /dev/null; then
            info "✓ Docker Compose found: $(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)"
        else
            info "✓ Docker Compose (plugin) found: $(docker compose version --short)"
        fi
    fi
    
    # Check available space
    local available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$available_space" -lt 5 ]; then
        warn "Available disk space is ${available_space}GB. Recommended: 10GB+"
    else
        info "✓ Available disk space: ${available_space}GB"
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        error "Missing required tools: ${missing_tools[*]}"
    fi
    
    log "Prerequisites check passed"
}

setup_directories() {
    header "Setting Up Directories"
    
    local directories=(
        "data/media"
        "data/thumbnails"
        "data/logs"
        "data/backups"
        "data/db-backups"
        "data/ssl"
        "data/monitor"
    )
    
    for dir in "${directories[@]}"; do
        local full_path="${PROJECT_DIR}/${dir}"
        if [ ! -d "$full_path" ]; then
            mkdir -p "$full_path"
            log "Created directory: $dir"
        else
            info "Directory exists: $dir"
        fi
    done
    
    # Set proper permissions
    chmod 755 "${PROJECT_DIR}/data"
    find "${PROJECT_DIR}/data" -type d -exec chmod 755 {} \;
    
    log "Directory setup completed"
}

create_environment_file() {
    header "Creating Environment Configuration"
    
    if [ -f "$ENV_FILE" ] && [ "$UPDATE_MODE" = false ]; then
        local backup_file="${ENV_FILE}.backup.$(date +%s)"
        cp "$ENV_FILE" "$backup_file"
        warn "Existing .env file backed up to: $(basename $backup_file)"
    fi
    
    if [ "$QUICK_SETUP" = true ] && [ -f "$ENV_FILE" ]; then
        info "Quick setup: keeping existing .env file"
        return
    fi
    
    # Generate secure passwords
    local mysql_root_password=$(generate_password)
    local mysql_password=$(generate_password)
    local redis_password=$(generate_password)
    
    # Interactive configuration (unless quick setup)
    local alert_email=""
    local discord_webhook=""
    local smtp_server=""
    local smtp_port="587"
    local smtp_username=""
    local smtp_password=""
    
    if [ "$QUICK_SETUP" = false ]; then
        echo -e "${CYAN}"
        echo "Configure optional settings (press Enter to skip):"
        echo -e "${NC}"
        
        read -p "Alert email address: " alert_email
        read -p "Discord webhook URL: " discord_webhook
        
        if [ -n "$alert_email" ]; then
            read -p "SMTP server (default: smtp.gmail.com): " smtp_server
            smtp_server=${smtp_server:-smtp.gmail.com}
            read -p "SMTP port (default: 587): " smtp_port
            smtp_port=${smtp_port:-587}
            read -p "SMTP username: " smtp_username
            read -s -p "SMTP password: " smtp_password
            echo
        fi
    fi
    
    # Create .env file
    cat > "$ENV_FILE" << EOF
# MVidarr Self-Hosted Production Configuration
# Generated on $(date)

# Database Configuration
MYSQL_ROOT_PASSWORD=${mysql_root_password}
MYSQL_PASSWORD=${mysql_password}

# Redis Configuration
REDIS_PASSWORD=${redis_password}

# Backup Configuration
BACKUP_SCHEDULE=0 2 * * *
BACKUP_RETENTION_DAYS=7

# Monitoring & Alerts
ALERT_EMAIL=${alert_email}
DISCORD_WEBHOOK=${discord_webhook}

# SMTP Settings
SMTP_SERVER=${smtp_server}
SMTP_PORT=${smtp_port}
SMTP_USERNAME=${smtp_username}
SMTP_PASSWORD=${smtp_password}

# Application Settings
LOG_LEVEL=INFO
WORKERS=4
MONITORING_ENABLED=${ENABLE_MONITORING}
BACKUP_ENABLED=${ENABLE_BACKUP}

# Domain/SSL Settings
DOMAIN=mvidarr.yourdomain.com
SSL_EMAIL=${alert_email}

# Update Settings
AUTO_UPDATE_ENABLED=${ENABLE_AUTO_UPDATE}
EOF

    chmod 600 "$ENV_FILE"
    log "Environment file created: .env"
    
    if [ -n "$alert_email" ]; then
        info "Email alerts configured for: $alert_email"
    fi
    
    if [ -n "$discord_webhook" ]; then
        info "Discord alerts configured"
    fi
}

build_or_pull_images() {
    header "Preparing Container Images"
    
    cd "$PROJECT_DIR"
    
    # Use docker compose if available, otherwise docker-compose
    local compose_cmd="docker-compose"
    if docker compose version &> /dev/null; then
        compose_cmd="docker compose"
    fi
    
    # Build custom images
    log "Building MVidarr application image..."
    if ! $compose_cmd -f "$COMPOSE_FILE" build mvidarr; then
        error "Failed to build MVidarr application image"
    fi
    
    if [ "$ENABLE_MONITORING" = true ]; then
        log "Building monitoring image..."
        if ! $compose_cmd -f "$COMPOSE_FILE" build mvidarr-monitor; then
            error "Failed to build monitoring image"
        fi
    fi
    
    if [ "$ENABLE_BACKUP" = true ]; then
        log "Building backup image..."
        if ! $compose_cmd -f "$COMPOSE_FILE" build mvidarr-backup; then
            error "Failed to build backup image"
        fi
    fi
    
    # Pull pre-built images
    log "Pulling pre-built images..."
    if ! $compose_cmd -f "$COMPOSE_FILE" pull mvidarr-db mvidarr-redis; then
        warn "Some pre-built images failed to pull, but continuing..."
    fi
    
    log "Image preparation completed"
}

start_services() {
    header "Starting Services"
    
    cd "$PROJECT_DIR"
    
    local compose_cmd="docker-compose"
    if docker compose version &> /dev/null; then
        compose_cmd="docker compose"
    fi
    
    # Prepare profiles
    local profiles=""
    if [ "$ENABLE_MONITORING" = true ]; then
        profiles="${profiles} --profile monitor"
    fi
    
    if [ "$ENABLE_BACKUP" = true ]; then
        profiles="${profiles} --profile backup"
    fi
    
    if [ "$ENABLE_PROXY" = true ]; then
        profiles="${profiles} --profile proxy"
    fi
    
    if [ "$ENABLE_AUTO_UPDATE" = true ]; then
        profiles="${profiles} --profile updater"
    fi
    
    # Start core services first
    log "Starting core services (database, cache, application)..."
    if ! $compose_cmd -f "$COMPOSE_FILE" up -d mvidarr mvidarr-db mvidarr-redis; then
        error "Failed to start core services"
    fi
    
    # Wait for services to be ready
    log "Waiting for services to be ready..."
    sleep 30
    
    # Start optional services
    if [ -n "$profiles" ]; then
        log "Starting optional services..."
        if ! $compose_cmd -f "$COMPOSE_FILE" $profiles up -d; then
            warn "Some optional services failed to start"
        fi
    fi
    
    log "Services started successfully"
}

verify_deployment() {
    header "Verifying Deployment"
    
    cd "$PROJECT_DIR"
    
    local compose_cmd="docker-compose"
    if docker compose version &> /dev/null; then
        compose_cmd="docker compose"
    fi
    
    # Check container status
    log "Checking container status..."
    $compose_cmd -f "$COMPOSE_FILE" ps
    
    # Test application health
    log "Testing application health..."
    local max_attempts=12
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sf http://localhost:5000/health > /dev/null 2>&1; then
            log "✓ Application health check passed"
            break
        else
            info "Health check attempt $attempt/$max_attempts..."
            sleep 10
            ((attempt++))
        fi
    done
    
    if [ $attempt -gt $max_attempts ]; then
        error "Application failed health check after $max_attempts attempts"
    fi
    
    # Test monitoring dashboard
    if [ "$ENABLE_MONITORING" = true ]; then
        log "Testing monitoring dashboard..."
        if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
            log "✓ Monitoring dashboard accessible"
        else
            warn "Monitoring dashboard not accessible"
        fi
    fi
    
    log "Deployment verification completed"
}

show_deployment_info() {
    header "Deployment Information"
    
    echo -e "${GREEN}🎉 MVidarr deployment completed successfully!${NC}"
    echo
    echo -e "${CYAN}Access Information:${NC}"
    echo "  📱 Main Application: http://localhost:5000"
    
    if [ "$ENABLE_MONITORING" = true ]; then
        echo "  📊 System Monitor: http://localhost:8080"
    fi
    
    if [ "$ENABLE_PROXY" = true ]; then
        echo "  🌐 Proxy: http://localhost:80 (configure SSL separately)"
    fi
    
    echo
    echo -e "${CYAN}Management Commands:${NC}"
    echo "  📋 View status:    docker-compose -f docker-compose.selfhosted.yml ps"
    echo "  📄 View logs:      docker-compose -f docker-compose.selfhosted.yml logs -f"
    echo "  🔄 Restart:        docker-compose -f docker-compose.selfhosted.yml restart"
    echo "  🛑 Stop:           docker-compose -f docker-compose.selfhosted.yml down"
    echo "  💾 Backup:         docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./backup.sh"
    echo "  📤 Restore:        docker-compose -f docker-compose.selfhosted.yml exec mvidarr-backup ./restore.sh -l"
    
    echo
    echo -e "${CYAN}Next Steps:${NC}"
    echo "  1. Open http://localhost:5000 in your browser"
    echo "  2. Complete the initial setup wizard"
    echo "  3. Configure your media directories"
    
    if [ "$ENABLE_MONITORING" = true ]; then
        echo "  4. Check system monitoring at http://localhost:8080"
    fi
    
    if [ "$ENABLE_BACKUP" = true ]; then
        echo "  5. Verify backup system is working"
    fi
    
    echo
    echo -e "${YELLOW}Important Files:${NC}"
    echo "  📁 Media storage:    ./data/media/"
    echo "  🖼️  Thumbnails:       ./data/thumbnails/"
    echo "  📋 Logs:            ./data/logs/"
    echo "  💾 Backups:         ./data/backups/"
    echo "  ⚙️  Configuration:    ./.env"
    
    echo
    echo -e "${GREEN}Enjoy using MVidarr! 🎬${NC}"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -q|--quick)
            QUICK_SETUP=true
            shift
            ;;
        -u|--update)
            UPDATE_MODE=true
            shift
            ;;
        --no-monitoring)
            ENABLE_MONITORING=false
            shift
            ;;
        --no-backup)
            ENABLE_BACKUP=false
            shift
            ;;
        --enable-proxy)
            ENABLE_PROXY=true
            shift
            ;;
        --enable-auto-update)
            ENABLE_AUTO_UPDATE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Main execution
main() {
    header "🎬 MVidarr Self-Hosted Deployment"
    
    if [ "$UPDATE_MODE" = true ]; then
        log "Running in update mode"
    elif [ "$QUICK_SETUP" = true ]; then
        log "Running quick setup with defaults"
    else
        log "Running interactive setup"
    fi
    
    check_prerequisites
    setup_directories
    
    if [ "$UPDATE_MODE" = false ]; then
        create_environment_file
    fi
    
    build_or_pull_images
    start_services
    verify_deployment
    show_deployment_info
}

# Run main function
main "$@"