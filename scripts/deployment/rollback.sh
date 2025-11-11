#!/usr/bin/env bash
# ===================================================================
# MVidarr Rollback Script
# ===================================================================
# Quickly rollback to the previous version if deployment fails
#
# Usage:
#   ./scripts/deployment/rollback.sh
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

check_rollback_info() {
    if [ ! -f "$PROJECT_ROOT/.last_deployment" ]; then
        log_error "No deployment information found. Cannot rollback."
        log_info "Rollback is only available after a deployment using deploy.sh"
        exit 1
    fi

    # Source deployment info
    source "$PROJECT_ROOT/.last_deployment"

    if [ "$PREVIOUS_IMAGE" == "unknown" ]; then
        log_error "Previous image information not available"
        exit 1
    fi

    log_info "Found deployment from: $DEPLOYED_AT"
    log_info "Previous image: $PREVIOUS_IMAGE"
}

confirm_rollback() {
    echo ""
    log_warning "This will rollback MVidarr to the previous version"
    echo -n "Are you sure you want to continue? (yes/no): "
    read -r CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        log_info "Rollback cancelled"
        exit 0
    fi
}

restore_previous_image() {
    log_info "Restoring previous Docker image..."

    # Update docker-compose to use previous image
    # This requires the image still exists locally
    if ! docker image inspect "$PREVIOUS_IMAGE" > /dev/null 2>&1; then
        log_error "Previous image not found in local Docker cache"
        log_warning "You may need to manually specify a version with: --tag VERSION"
        exit 1
    fi

    cd "$PROJECT_ROOT"

    # Use docker compose or docker-compose depending on availability
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi

    # Tag the previous image as latest (temporarily)
    docker tag "$PREVIOUS_IMAGE" "ghcr.io/prefect421/mvidarr:rollback"

    # Update compose file to use rollback tag (temporary)
    export MVIDARR_IMAGE="ghcr.io/prefect421/mvidarr:rollback"

    log_success "Previous image prepared"
}

rollback_containers() {
    log_info "Rolling back containers..."

    cd "$PROJECT_ROOT"

    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi

    # Stop current container
    $COMPOSE_CMD -f "$COMPOSE_FILE" stop mvidarr

    # Manually run the previous image
    docker run -d \
        --name mvidarr-app-rollback \
        --network mvidarr_mvidarr-network \
        -p ${MVIDARR_PORT:-5000}:5000 \
        --env-file "$PROJECT_ROOT/.env" \
        -e DB_HOST=mariadb \
        -e REDIS_HOST=redis \
        $(docker inspect mvidarr-app --format='{{range .Mounts}}--mount source={{.Source}},target={{.Destination}} {{end}}' 2>/dev/null || echo "") \
        "$PREVIOUS_IMAGE" || {
            log_error "Failed to start previous container"
            log_info "Attempting to restart current container..."
            $COMPOSE_CMD -f "$COMPOSE_FILE" start mvidarr
            exit 1
        }

    # Remove old container
    docker rm -f mvidarr-app 2>/dev/null || true

    # Rename rollback container
    docker rename mvidarr-app-rollback mvidarr-app

    log_success "Containers rolled back"
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
    log_warning "Check logs with: docker logs mvidarr-app"
    return 1
}

show_status() {
    log_info "Rollback Status:"

    docker ps -f name=mvidarr

    echo ""
    log_info "Access MVidarr at: http://localhost:${MVIDARR_PORT:-5000}"
    log_info "View logs: docker logs -f mvidarr-app"
}

# Main rollback process
main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║              MVidarr Rollback Utility                    ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""

    check_rollback_info
    confirm_rollback
    restore_previous_image
    rollback_containers

    if wait_for_health; then
        echo ""
        echo "╔═══════════════════════════════════════════════════════════╗"
        echo "║             Rollback Completed Successfully              ║"
        echo "╚═══════════════════════════════════════════════════════════╝"
        echo ""
        show_status
        log_info "To restore normal operation, redeploy: ./scripts/deployment/deploy.sh"
        exit 0
    else
        log_error "Rollback completed but health check failed"
        log_warning "Manual intervention may be required"
        show_status
        exit 1
    fi
}

# Run main function
main
