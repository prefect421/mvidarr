#!/bin/bash
# MVidarr Service Management Script
# Manages all MVidarr services with proper dependencies

set -e

SERVICES=(
    "mvidarr"
    "mvidarr-celery-worker"
    "mvidarr-celery-beat"
)

OPTIONAL_SERVICES=(
    "mvidarr-flask"
)

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  MVidarr Service Manager${NC}"
    echo -e "${BLUE}  Phase 3 Complete - v0.9.9-dev${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_service_status() {
    local service=$1
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}●${NC} $service: ${GREEN}active (running)${NC}"
        return 0
    elif systemctl is-failed --quiet "$service"; then
        echo -e "${RED}●${NC} $service: ${RED}failed${NC}"
        return 1
    else
        echo -e "${YELLOW}●${NC} $service: ${YELLOW}inactive${NC}"
        return 2
    fi
}

status_all() {
    print_header
    echo "Service Status:"
    echo ""

    for service in "${SERVICES[@]}"; do
        check_service_status "$service"
    done

    echo ""
    echo "Optional Services:"
    for service in "${OPTIONAL_SERVICES[@]}"; do
        check_service_status "$service" || true
    done

    echo ""
    print_info "Use 'journalctl -u mvidarr -f' to view logs"
}

start_all() {
    print_header
    print_info "Starting MVidarr services in order..."
    echo ""

    # Start main application first
    print_info "Starting main application..."
    sudo systemctl start mvidarr
    if [ $? -eq 0 ]; then
        print_success "mvidarr.service started"
    else
        print_error "Failed to start mvidarr.service"
        exit 1
    fi

    # Wait for main app to be ready
    sleep 5

    # Start worker
    print_info "Starting Celery worker..."
    sudo systemctl start mvidarr-celery-worker
    if [ $? -eq 0 ]; then
        print_success "mvidarr-celery-worker.service started"
    else
        print_warning "Failed to start mvidarr-celery-worker.service"
    fi

    # Wait for worker to be ready
    sleep 3

    # Start beat scheduler
    print_info "Starting Celery beat..."
    sudo systemctl start mvidarr-celery-beat
    if [ $? -eq 0 ]; then
        print_success "mvidarr-celery-beat.service started"
    else
        print_warning "Failed to start mvidarr-celery-beat.service"
    fi

    echo ""
    print_success "All services started!"
    echo ""
    status_all
}

stop_all() {
    print_header
    print_info "Stopping MVidarr services in reverse order..."
    echo ""

    # Stop in reverse order
    for service in $(echo "${SERVICES[@]}" | tac -s' '); do
        print_info "Stopping $service..."
        sudo systemctl stop "$service"
        if [ $? -eq 0 ]; then
            print_success "$service stopped"
        else
            print_warning "Failed to stop $service"
        fi
    done

    echo ""
    print_success "All services stopped!"
}

restart_all() {
    print_header
    print_info "Restarting MVidarr services..."
    echo ""

    stop_all
    sleep 2
    start_all
}

enable_all() {
    print_header
    print_info "Enabling MVidarr services for auto-start..."
    echo ""

    for service in "${SERVICES[@]}"; do
        sudo systemctl enable "$service"
        if [ $? -eq 0 ]; then
            print_success "$service enabled"
        else
            print_error "Failed to enable $service"
        fi
    done

    echo ""
    print_success "All services enabled for auto-start!"
}

disable_all() {
    print_header
    print_info "Disabling MVidarr services auto-start..."
    echo ""

    for service in "${SERVICES[@]}"; do
        sudo systemctl disable "$service"
        if [ $? -eq 0 ]; then
            print_success "$service disabled"
        else
            print_error "Failed to disable $service"
        fi
    done

    echo ""
    print_success "All services disabled!"
}

reload_config() {
    print_header
    print_info "Reloading systemd configuration..."
    sudo systemctl daemon-reload
    print_success "Systemd configuration reloaded!"
    echo ""
    print_info "Restarting services to apply changes..."
    restart_all
}

show_logs() {
    local service=${1:-mvidarr}
    print_header
    print_info "Showing logs for $service (Ctrl+C to exit)..."
    echo ""
    journalctl -u "$service" -f
}

show_help() {
    print_header
    echo "Usage: $0 [command] [service]"
    echo ""
    echo "Commands:"
    echo "  status              Show status of all services"
    echo "  start               Start all services in proper order"
    echo "  stop                Stop all services"
    echo "  restart             Restart all services"
    echo "  enable              Enable auto-start for all services"
    echo "  disable             Disable auto-start for all services"
    echo "  reload              Reload systemd config and restart"
    echo "  logs [service]      Show logs for service (default: mvidarr)"
    echo "  help                Show this help message"
    echo ""
    echo "Services:"
    for service in "${SERVICES[@]}"; do
        echo "  - $service"
    done
    echo ""
    echo "Examples:"
    echo "  $0 status           # Show all service status"
    echo "  $0 start            # Start all services"
    echo "  $0 logs             # Show main app logs"
    echo "  $0 logs mvidarr-celery-worker  # Show worker logs"
}

# Main execution
case "${1:-}" in
    status)
        status_all
        ;;
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    enable)
        enable_all
        ;;
    disable)
        disable_all
        ;;
    reload)
        reload_config
        ;;
    logs)
        show_logs "${2:-mvidarr}"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: ${1:-}"
        echo ""
        show_help
        exit 1
        ;;
esac
