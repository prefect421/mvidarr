#!/usr/bin/env bash
# ===================================================================
# MVidarr Simple Deployment Script
# ===================================================================
# Updates MVidarr to the latest version with automatic backup
#
# Usage:
#   ./scripts/deployment/deploy.sh [options]
#
# Options:
#   --no-backup    Skip automatic backup before deployment
#   --tag TAG      Deploy specific version tag (default: latest)
#   --help         Show this help message
# ===================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.simple.yml}"
BACKUP_ENABLED=true
IMAGE_TAG="latest"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-backup)
            BACKUP_ENABLED=false
            shift
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --help)
            grep "^#" "$0" | grep -v "!/usr/bin/env" | sed 's/^# //' | sed 's/^#//'
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    if [ ! -f "$PROJECT_ROOT/$COMPOSE_FILE" ]; then
        log_error "Docker Compose file not found: $COMPOSE_FILE"
        exit 1
    fi

    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_error ".env file not found. Copy .env.simple.example to .env and configure it."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

create_backup() {
    if [ "$BACKUP_ENABLED" = false ]; then
        log_warning "Backup skipped (--no-backup flag used)"
        return 0
    fi

    log_info "Creating backup before deployment..."

    # Try to use MVidarr's backup API
    if curl -s -f http://localhost:${MVIDARR_PORT:-5000}/api/backups/create \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{"backup_type":"full"}' > /dev/null 2>&1; then
        log_success "Backup created via API"
    else
        log_warning "Could not create backup via API (server may be down). Continuing..."
    fi
}

save_current_version() {
    log_info "Saving current version information..."

    # Get current image ID
    CURRENT_IMAGE=$(docker inspect mvidarr-app --format='{{.Image}}' 2>/dev/null || echo "unknown")

    # Save to rollback info file
    cat > "$PROJECT_ROOT/.last_deployment" <<EOF
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PREVIOUS_IMAGE=$CURRENT_IMAGE
IMAGE_TAG=$IMAGE_TAG
EOF

    log_success "Version information saved"
}

pull_latest_image() {
    log_info "Pulling MVidarr image: ghcr.io/prefect421/mvidarr:$IMAGE_TAG..."

    cd "$PROJECT_ROOT"
    docker pull "ghcr.io/prefect421/mvidarr:$IMAGE_TAG"

    log_success "Image pulled successfully"
}

deploy_containers() {
    log_info "Deploying updated containers..."

    cd "$PROJECT_ROOT"

    # Use docker compose or docker-compose depending on availability
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi

    # Recreate containers with new image
    $COMPOSE_CMD -f "$COMPOSE_FILE" up -d --force-recreate mvidarr

    log_success "Containers deployed"
}

wait_for_health() {
    log_info "Waiting for MVidarr to be healthy..."

    local MAX_ATTEMPTS=30
    local ATTEMPT=1
    local HEALTH_URL="http://localhost:${MVIDARR_PORT:-5000}/api/health"

    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        if curl -s -f "$HEALTH_URL" > /dev/null 2>&1; then
            log_success "MVidarr is healthy!"
            return 0
        fi

        echo -ne "\r${BLUE}[INFO]${NC} Health check attempt $ATTEMPT/$MAX_ATTEMPTS..."
        sleep 2
        ((ATTEMPT++))
    done

    echo "" # New line after progress
    log_error "MVidarr failed to become healthy after $MAX_ATTEMPTS attempts"
    log_warning "Check logs with: docker-compose -f $COMPOSE_FILE logs -f mvidarr"
    return 1
}

show_status() {
    log_info "Deployment Status:"

    cd "$PROJECT_ROOT"

    if docker compose version &> /dev/null; then
        docker compose -f "$COMPOSE_FILE" ps
    else
        docker-compose -f "$COMPOSE_FILE" ps
    fi

    echo ""
    log_info "Access MVidarr at: http://localhost:${MVIDARR_PORT:-5000}"
    log_info "View logs: docker-compose -f $COMPOSE_FILE logs -f"
    log_info "Health dashboard: http://localhost:${MVIDARR_PORT:-5000}/api/health/dashboard"
}

cleanup_old_images() {
    log_info "Cleaning up old Docker images..."

    # Remove dangling images
    docker image prune -f > /dev/null 2>&1 || true

    log_success "Cleanup complete"
}

# Main deployment process
main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║         MVidarr Deployment - Version $IMAGE_TAG                    ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""

    check_prerequisites
    save_current_version
    create_backup
    pull_latest_image
    deploy_containers

    if wait_for_health; then
        cleanup_old_images
        echo ""
        echo "╔═══════════════════════════════════════════════════════════╗"
        echo "║              Deployment Completed Successfully           ║"
        echo "╚═══════════════════════════════════════════════════════════╝"
        echo ""
        show_status
        exit 0
    else
        log_error "Deployment completed but health check failed"
        log_warning "You may need to rollback: ./scripts/deployment/rollback.sh"
        show_status
        exit 1
    fi
}

# Run main function
main
