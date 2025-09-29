#!/bin/bash

# MVidarr Enhanced Service Management Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
APP_FILE="$PROJECT_DIR/app_launcher.py"
PID_FILE="$PROJECT_DIR/data/mvidarr.pid"
LOG_FILE="$PROJECT_DIR/data/logs/mvidarr.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Install dependencies globally (fallback)
install_global_deps() {
    print_warning "Installing dependencies globally as fallback..."
    
    # Check if we can use pip with --break-system-packages
    if pip3 install --break-system-packages --user -r "$PROJECT_DIR/requirements.txt" 2>/dev/null; then
        print_status "Dependencies installed globally with --break-system-packages"
        return 0
    elif pip3 install --user -r "$PROJECT_DIR/requirements.txt" 2>/dev/null; then
        print_status "Dependencies installed globally with --user"
        return 0
    else
        print_error "Failed to install dependencies globally"
        print_error "Please install dependencies manually:"
        print_error "pip3 install --break-system-packages -r requirements.txt"
        return 1
    fi
}

# Check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        print_warning "Virtual environment not found. Creating one..."
        
        # Try to create virtual environment with --system-site-packages if externally managed
        if python3 -m venv "$VENV_DIR" 2>/dev/null; then
            print_status "Virtual environment created successfully"
        else
            print_warning "Standard venv creation failed. Trying with --system-site-packages..."
            python3 -m venv --system-site-packages "$VENV_DIR"
            if [ $? -ne 0 ]; then
                print_error "Failed to create virtual environment. Trying alternative method..."
                # Try with --break-system-packages
                python3 -m venv "$VENV_DIR" --system-site-packages --clear
                if [ $? -ne 0 ]; then
                    print_error "Virtual environment creation failed. Installing globally..."
                    install_global_deps
                    return 1
                fi
            fi
        fi
        
        # Activate and install dependencies
        if [ -f "$VENV_DIR/bin/activate" ]; then
            source "$VENV_DIR/bin/activate"
            pip install -r "$PROJECT_DIR/requirements.txt"
            print_status "Virtual environment created and dependencies installed"
        else
            print_error "Virtual environment activation failed"
            return 1
        fi
    fi
}

# Get process ID if running
get_pid() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "$PID"
        else
            rm -f "$PID_FILE"
            echo ""
        fi
    else
        echo ""
    fi
}

# Clean up processes using port 5000
cleanup_port_processes() {
    print_status "Cleaning up processes on port 5000..."
    
    # Find processes using port 5000
    PIDS=$(lsof -ti:5000 2>/dev/null || true)
    
    if [ -n "$PIDS" ]; then
        print_warning "Found processes using port 5000: $PIDS"
        for pid in $PIDS; do
            # Check if it's a MVidarr process
            if ps -p "$pid" -o cmd= 2>/dev/null | grep -q "app_launcher.py\|app.py\|mvidarr\|python.*app"; then
                print_status "Killing MVidarr process: $pid"
                kill -TERM "$pid" 2>/dev/null || true
                sleep 2
                # Force kill if still running
                if kill -0 "$pid" 2>/dev/null; then
                    kill -9 "$pid" 2>/dev/null || true
                fi
            else
                print_warning "Non-MVidarr process using port 5000: $pid"
            fi
        done
        
        # Wait a moment for cleanup
        sleep 2
        
        # Check if port is now free
        if lsof -ti:5000 >/dev/null 2>&1; then
            print_warning "Port 5000 still in use after cleanup"
        else
            print_status "Port 5000 is now free"
        fi
    else
        print_status "Port 5000 is free"
    fi
}

# Start the service
start_service() {
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        print_warning "MVidarr is already running (PID: $PID)"
        return 1
    fi
    
    print_status "Starting MVidarr Enhanced..."
    
    # Pre-start cleanup to ensure port is free
    cleanup_port_processes
    
    # Create data directories with proper permissions
    mkdir -p "$PROJECT_DIR/data/logs"
    mkdir -p "$PROJECT_DIR/data/downloads"
    mkdir -p "$PROJECT_DIR/data/thumbnails"
    mkdir -p "$PROJECT_DIR/data/cache"
    mkdir -p "$PROJECT_DIR/data/backups"
    
    # Ensure proper ownership and permissions
    if [ "$(id -u)" != "$(stat -c %u "$PROJECT_DIR")" ]; then
        print_warning "Fixing directory ownership..."
    fi
    
    # Set correct permissions for data directories (755 = rwxr-xr-x)
    chmod 755 "$PROJECT_DIR/data"
    chmod 755 "$PROJECT_DIR/data"/*
    # Ensure thumbnails and other data directories are writable
    find "$PROJECT_DIR/data" -type d -exec chmod 755 {} \;
    
    # Check virtual environment
    check_venv
    
    # Activate virtual environment if it exists
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_status "Using virtual environment"
    else
        print_warning "Running without virtual environment"
    fi
    
    # Check if app_launcher.py exists
    if [ ! -f "$APP_FILE" ]; then
        print_error "Application file not found: $APP_FILE"
        return 1
    fi
    
    # Start the application
    cd "$PROJECT_DIR"
    nohup python3 app_launcher.py > "$LOG_FILE" 2>&1 &
    PID=$!
    
    # Save PID
    echo "$PID" > "$PID_FILE"
    
    # Wait a moment and check if it's still running
    sleep 3
    if kill -0 "$PID" 2>/dev/null; then
        # Additional check: verify it's listening on port 5000
        sleep 2
        if lsof -ti:5000 >/dev/null 2>&1; then
            print_status "MVidarr Enhanced started successfully (PID: $PID)"
            print_status "Application is listening on port 5000"
            print_status "Logs: $LOG_FILE"
            return 0
        else
            print_error "MVidarr started but not listening on port 5000"
            print_error "Check logs for startup errors: $LOG_FILE"
            return 1
        fi
    else
        print_error "Failed to start MVidarr Enhanced"
        print_error "Check logs for details: $LOG_FILE"
        if [ -f "$LOG_FILE" ]; then
            print_error "Last few log lines:"
            tail -10 "$LOG_FILE" | sed 's/^/  /'
        fi
        rm -f "$PID_FILE"
        return 1
    fi
}

# Stop the service
stop_service() {
    PID=$(get_pid)
    if [ -z "$PID" ]; then
        print_warning "MVidarr is not running"
        # Still try to clean up any processes using port 5000
        cleanup_port_processes
        return 1
    fi
    
    print_status "Stopping MVidarr Enhanced (PID: $PID)..."
    
    # Send SIGTERM
    kill "$PID" 2>/dev/null
    
    # Wait for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        print_warning "Force killing process..."
        kill -9 "$PID" 2>/dev/null
        sleep 1
    fi
    
    # Clean up any remaining processes on port 5000
    cleanup_port_processes
    
    # Remove PID file
    rm -f "$PID_FILE"
    
    print_status "MVidarr Enhanced stopped"
    return 0
}

# Restart Celery workers
restart_celery_workers() {
    print_status "Starting Celery workers..."
    
    # Activate virtual environment if available
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_status "Using virtual environment for Celery workers"
    else
        print_warning "Virtual environment not found, starting workers without it"
    fi
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Start Celery worker in background
    nohup celery -A src.jobs.celery_app worker --loglevel=info --concurrency=3 --hostname=worker@%h > "$PROJECT_DIR/data/logs/celery_worker.log" 2>&1 &
    local celery_pid=$!
    
    # Wait a moment and verify it started
    sleep 2
    if kill -0 "$celery_pid" 2>/dev/null; then
        print_status "Celery worker started successfully (PID: $celery_pid)"
        return 0
    else
        print_error "Failed to start Celery worker"
        return 1
    fi
}

# Restart the service
restart_service() {
    print_status "Restarting MVidarr Enhanced..."
    
    # Store current PID for better tracking
    CURRENT_PID=$(get_pid)
    if [ -n "$CURRENT_PID" ]; then
        print_status "Current service PID: $CURRENT_PID"
    fi
    
    # Stop Celery workers first to ensure they restart with new code
    print_status "Stopping Celery workers..."
    local celery_pids=$(pgrep -f "celery.*worker" 2>/dev/null || true)
    if [ -n "$celery_pids" ]; then
        print_status "Found Celery workers: $celery_pids"
        for pid in $celery_pids; do
            print_status "Stopping Celery worker PID: $pid"
            kill -TERM "$pid" 2>/dev/null || true
        done
        
        # Wait for graceful shutdown
        sleep 3
        
        # Force kill any remaining workers
        celery_pids=$(pgrep -f "celery.*worker" 2>/dev/null || true)
        if [ -n "$celery_pids" ]; then
            print_warning "Force killing remaining Celery workers: $celery_pids"
            for pid in $celery_pids; do
                kill -9 "$pid" 2>/dev/null || true
            done
        fi
        print_status "Celery workers stopped"
    else
        print_status "No Celery workers found to stop"
    fi
    
    # Stop the service first with enhanced verification
    local stop_attempts=0
    local max_stop_attempts=3
    
    while [ $stop_attempts -lt $max_stop_attempts ]; do
        stop_attempts=$((stop_attempts + 1))
        
        if stop_service; then
            print_status "Service stopped successfully on attempt $stop_attempts"
            break
        else
            print_warning "Service stop attempt $stop_attempts failed"
            if [ $stop_attempts -lt $max_stop_attempts ]; then
                print_status "Retrying stop operation..."
                sleep 2
            else
                print_error "Service stop failed after $max_stop_attempts attempts, forcing kill..."
                force_kill
            fi
        fi
    done
    
    # Enhanced cleanup verification
    print_status "Verifying complete cleanup..."
    local cleanup_timeout=15
    local cleanup_elapsed=0
    
    while [ $cleanup_elapsed -lt $cleanup_timeout ]; do
        # Check if any MVidarr processes are still running
        local remaining_pids=$(pgrep -f "python.*app_launcher.py|python.*app.py|mvidarr" 2>/dev/null || true)
        local port_usage=$(lsof -ti:5000 2>/dev/null || true)
        
        if [ -z "$remaining_pids" ] && [ -z "$port_usage" ]; then
            print_status "Cleanup verification complete - no remaining processes or port usage"
            break
        fi
        
        if [ -n "$remaining_pids" ]; then
            print_warning "Waiting for processes to terminate: $remaining_pids"
        fi
        
        if [ -n "$port_usage" ]; then
            print_warning "Waiting for port 5000 to be freed: $port_usage"
        fi
        
        sleep 1
        cleanup_elapsed=$((cleanup_elapsed + 1))
    done
    
    # Final cleanup if timeout reached
    if [ $cleanup_elapsed -ge $cleanup_timeout ]; then
        print_warning "Cleanup timeout reached, performing final cleanup..."
        cleanup_port_processes
        force_kill
        sleep 2
    fi
    
    # Pre-start system checks
    print_status "Performing pre-start system checks..."
    
    # Check disk space
    local available_space=$(df "$PROJECT_DIR" | awk 'NR==2 {print $4}')
    if [ "$available_space" -lt 100000 ]; then  # Less than 100MB
        print_warning "Low disk space detected: ${available_space}KB available"
    fi
    
    # Check memory availability
    local available_memory=$(free | awk 'NR==2{print $7}')
    if [ "$available_memory" -lt 100000 ]; then  # Less than 100MB
        print_warning "Low memory detected: ${available_memory}KB available"
    fi
    
    # Verify application file integrity
    if [ ! -f "$APP_FILE" ] || [ ! -r "$APP_FILE" ]; then
        print_error "Application file is missing or unreadable: $APP_FILE"
        return 1
    fi
    
    # Start the service with enhanced monitoring
    print_status "Starting service with enhanced monitoring..."
    local start_attempts=0
    local max_start_attempts=3
    
    while [ $start_attempts -lt $max_start_attempts ]; do
        start_attempts=$((start_attempts + 1))
        
        if start_service; then
            print_status "Service started successfully on attempt $start_attempts"
            
            # Enhanced post-start verification
            print_status "Performing post-start verification..."
            sleep 5
            
            local new_pid=$(get_pid)
            if [ -n "$new_pid" ] && [ "$new_pid" != "$CURRENT_PID" ]; then
                print_status "New service PID: $new_pid"
                
                # Test service responsiveness
                if curl -s -f http://localhost:5000/api/health >/dev/null 2>&1; then
                    print_status "Service health check passed"
                    
                    # Restart Celery workers after successful service restart
                    print_status "Restarting Celery workers with updated code..."
                    restart_celery_workers
                    
                    print_status "Service restarted successfully"
                    return 0
                else
                    print_warning "Service started but health check failed"
                    print_status "Allowing additional startup time..."
                    sleep 10
                    
                    if curl -s -f http://localhost:5000/api/health >/dev/null 2>&1; then
                        print_status "Service health check passed after additional wait"
                        
                        # Restart Celery workers after successful service restart
                        print_status "Restarting Celery workers with updated code..."
                        restart_celery_workers
                        
                        print_status "Service restarted successfully"
                        return 0
                    else
                        print_error "Service health check failed after extended wait"
                        if [ $start_attempts -lt $max_start_attempts ]; then
                            print_status "Retrying service start..."
                            stop_service
                            sleep 3
                        fi
                    fi
                fi
            else
                print_error "New PID not detected or same as previous PID"
                if [ $start_attempts -lt $max_start_attempts ]; then
                    print_status "Retrying service start..."
                    sleep 3
                fi
            fi
        else
            print_error "Service start attempt $start_attempts failed"
            if [ $start_attempts -lt $max_start_attempts ]; then
                print_status "Retrying start operation..."
                sleep 3
            fi
        fi
    done
    
    print_error "Service restart failed after $max_start_attempts attempts"
    print_error "Check logs for details: $LOG_FILE"
    
    # Provide diagnostic information
    print_status "Diagnostic information:"
    show_diagnostics | head -20
    
    return 1
}

# Check service status
status_service() {
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        print_status "MVidarr Enhanced is running (PID: $PID)"
        
        # Check if service is responsive via health endpoint
        if command -v curl >/dev/null 2>&1; then
            print_status "Testing service responsiveness..."
            if curl -s -f --connect-timeout 5 --max-time 10 http://localhost:5000/api/health >/dev/null 2>&1; then
                print_status "Service health check: PASSED"
            else
                print_warning "Service health check: FAILED (service may be starting up)"
                # Try alternative port check
                if lsof -ti:5000 >/dev/null 2>&1; then
                    print_warning "Port 5000 is in use but service not responding to health checks"
                else
                    print_warning "Port 5000 is not in use - service may have crashed"
                fi
            fi
        else
            print_warning "curl not available - install with: sudo apt install curl"
        fi
        
        # Check if process is responsive
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Recent log entries:"
            tail -5 "$LOG_FILE"
        fi
        
        # Show process details
        echo ""
        print_status "Process details:"
        if ps -p "$PID" -o pid,ppid,cmd,etime 2>/dev/null; then
            echo ""
        else
            print_warning "Unable to get process details for PID $PID"
        fi
        
        return 0
    else
        print_warning "MVidarr Enhanced is not running"
        
        # Check if any processes are using the expected port
        if command -v lsof >/dev/null 2>&1; then
            PIDS=$(lsof -ti:5000 2>/dev/null || true)
            if [ -n "$PIDS" ]; then
                print_warning "Port 5000 is in use by other processes: $PIDS"
                for pid in $PIDS; do
                    CMD=$(ps -p "$pid" -o cmd= 2>/dev/null || echo "Unknown")
                    echo "  PID $pid: $CMD"
                done
            fi
        fi
        
        return 1
    fi
}

# View logs
view_logs() {
    if [ -f "$LOG_FILE" ]; then
        if [ "$1" = "follow" ]; then
            tail -f "$LOG_FILE"
        else
            tail -50 "$LOG_FILE"
        fi
    else
        print_error "Log file not found: $LOG_FILE"
        return 1
    fi
}

# Install dependencies
install_deps() {
    print_status "Installing dependencies..."
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        return 1
    fi
    
    # Create virtual environment if needed
    check_venv
    
    # Activate and install dependencies
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        pip install -r "$PROJECT_DIR/requirements.txt"
        print_status "Dependencies installed successfully in virtual environment"
    else
        print_warning "Virtual environment not available, installing globally"
        install_global_deps
    fi
}

# Initialize database
init_database() {
    print_status "Initializing database..."
    
    check_venv
    
    # Activate virtual environment if available
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    fi
    
    cd "$PROJECT_DIR"
    python3 -c "from src.database.init_db import initialize_database; initialize_database()"
    
    if [ $? -eq 0 ]; then
        print_status "Database initialized successfully"
    else
        print_error "Database initialization failed"
        return 1
    fi
}

# Show configuration status
show_config() {
    print_status "MVidarr Enhanced Configuration Status"
    echo ""
    
    # Check if .env exists
    if [ -f "$PROJECT_DIR/.env" ]; then
        print_status ".env file found"
        
        # Check key settings
        if grep -q "DB_PASSWORD=change_me_to_your_password" "$PROJECT_DIR/.env" 2>/dev/null; then
            print_warning "Database password needs to be configured"
        else
            print_status "Database password configured"
        fi
        
        if grep -q "SECRET_KEY=change_me_to_random_string_for_production" "$PROJECT_DIR/.env" 2>/dev/null; then
            print_warning "Secret key needs to be configured"
            print_warning "Generate one with: python3 scripts/generate_secret_key.py"
        else
            print_status "Secret key configured"
        fi
        
        # Show current port
        PORT=$(grep "^PORT=" "$PROJECT_DIR/.env" | cut -d= -f2)
        print_status "Application port: ${PORT:-5000}"
        
    else
        print_warning ".env file not found"
        print_warning "Run './scripts/manage_service.sh install' to create one"
    fi
    
    # Check database connectivity
    echo ""
    print_status "Database connectivity test:"
    if command -v mysql &> /dev/null; then
        print_status "MySQL client found"
    else
        print_warning "MySQL client not found - install with: sudo apt install mariadb-client"
    fi
}

# Force kill all MVidarr processes
force_kill() {
    print_warning "Force killing all MVidarr processes..."
    
    # Kill by PID file first
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        print_status "Killing process from PID file: $PID"
        kill -9 "$PID" 2>/dev/null || true
    fi
    
    # Kill all processes matching MVidarr patterns
    pkill -9 -f "python.*app_launcher.py" 2>/dev/null || true
    pkill -9 -f "python.*app.py" 2>/dev/null || true
    pkill -9 -f "mvidarr" 2>/dev/null || true
    
    # Clean up port processes
    cleanup_port_processes
    
    # Remove PID file
    rm -f "$PID_FILE"
    
    print_status "Force kill completed"
}

# Show diagnostic information
show_diagnostics() {
    print_status "MVidarr Enhanced Diagnostics"
    echo ""
    
    # Check process status
    print_status "Process Status:"
    PID=$(get_pid)
    if [ -n "$PID" ]; then
        echo "  PID file exists: $PID"
        if kill -0 "$PID" 2>/dev/null; then
            echo "  Process is running: YES"
        else
            echo "  Process is running: NO (stale PID file)"
        fi
    else
        echo "  PID file exists: NO"
    fi
    
    # Check port usage
    echo ""
    print_status "Port 5000 Status:"
    PIDS=$(lsof -ti:5000 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "  Port in use: YES"
        echo "  PIDs using port: $PIDS"
        for pid in $PIDS; do
            CMD=$(ps -p "$pid" -o cmd= 2>/dev/null || echo "Unknown")
            echo "    PID $pid: $CMD"
        done
    else
        echo "  Port in use: NO"
    fi
    
    # Check recent logs
    echo ""
    print_status "Recent Log Activity:"
    if [ -f "$LOG_FILE" ]; then
        echo "  Log file: $LOG_FILE"
        echo "  Last modified: $(stat -c %y "$LOG_FILE" 2>/dev/null || echo "Unknown")"
        echo "  Last 3 lines:"
        tail -3 "$LOG_FILE" 2>/dev/null | sed 's/^/    /' || echo "    Unable to read log file"
    else
        echo "  Log file: NOT FOUND"
    fi
    
    # Check dependencies
    echo ""
    print_status "Dependencies:"
    if command -v python3 >/dev/null 2>&1; then
        echo "  Python 3: $(python3 --version)"
    else
        echo "  Python 3: NOT FOUND"
    fi
    
    if command -v lsof >/dev/null 2>&1; then
        echo "  lsof: Available"
    else
        echo "  lsof: NOT FOUND (install with: sudo apt install lsof)"
    fi
}

# Check if systemd service is installed
is_systemd_service_installed() {
    if systemctl list-unit-files mvidarr.service >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Prefer systemd service if installed
prefer_systemd_service() {
    if is_systemd_service_installed; then
        case "$1" in
            start)
                print_status "Using systemd service..."
                sudo systemctl start mvidarr.service
                return $?
                ;;
            stop)
                print_status "Using systemd service..."
                sudo systemctl stop mvidarr.service
                return $?
                ;;
            restart)
                print_status "Using systemd service..."
                sudo systemctl restart mvidarr.service
                return $?
                ;;
            status)
                print_status "Using systemd service..."
                sudo systemctl status mvidarr.service
                return $?
                ;;
        esac
    fi
    return 1
}

# Show help
show_help() {
    echo "MVidarr Enhanced Service Management"
    echo "Usage: $0 {start|stop|restart|status|logs|install|init-db|config|force-kill|diagnostics|install-service|help}"
    echo ""
    echo "Commands:"
    echo "  start             Start the MVidarr service (prefers systemd if installed)"
    echo "  stop              Stop the MVidarr service (prefers systemd if installed)"
    echo "  restart           Restart the MVidarr service (prefers systemd if installed)"
    echo "  status            Show service status (prefers systemd if installed)"
    echo "  logs              Show recent log entries"
    echo "  logs-f            Follow log file (tail -f)"
    echo "  install           Install dependencies"
    echo "  init-db           Initialize database"
    echo "  config            Show configuration status"
    echo "  force-kill        Force kill all MVidarr processes"
    echo "  diagnostics       Show detailed diagnostic information"
    echo "  install-service   Install systemd service (requires sudo)"
    echo "  help              Show this help message"
    echo ""
    echo "Systemd Service Management:"
    echo "  sudo ./scripts/install_service.sh install   # Install systemd service"
    echo "  sudo systemctl start mvidarr                # Start service"
    echo "  sudo systemctl enable mvidarr               # Enable auto-start"
    echo "  sudo journalctl -u mvidarr -f               # View systemd logs"
    echo ""
    echo "Configuration:"
    echo "  Edit .env file to configure database and application settings"
    echo "  Generate secret key: python3 scripts/generate_secret_key.py"
    echo "  Setup database: ./scripts/setup_database.sh setup"
    echo ""
    if is_systemd_service_installed; then
        echo "✅ Systemd service is installed and available"
    else
        echo "ℹ️  Systemd service not installed (run: sudo ./scripts/install_service.sh install)"
    fi
}

# Install systemd service function
install_systemd_service() {
    print_status "Installing systemd service..."
    if [ -f "$PROJECT_DIR/scripts/install_service.sh" ]; then
        print_status "Running systemd service installer..."
        sudo "$PROJECT_DIR/scripts/install_service.sh" install
    else
        print_error "Service installer not found: $PROJECT_DIR/scripts/install_service.sh"
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        if prefer_systemd_service start; then
            exit $?
        else
            start_service
        fi
        ;;
    stop)
        if prefer_systemd_service stop; then
            exit $?
        else
            stop_service
        fi
        ;;
    restart)
        if prefer_systemd_service restart; then
            exit $?
        else
            restart_service
        fi
        ;;
    status)
        if prefer_systemd_service status; then
            exit $?
        else
            status_service
        fi
        ;;
    logs)
        if is_systemd_service_installed; then
            print_status "Using systemd logs..."
            sudo journalctl -u mvidarr.service -n 50
        else
            view_logs
        fi
        ;;
    logs-f)
        if is_systemd_service_installed; then
            print_status "Following systemd logs..."
            sudo journalctl -u mvidarr.service -f
        else
            view_logs follow
        fi
        ;;
    install)
        install_deps
        ;;
    init-db)
        init_database
        ;;
    config)
        show_config
        ;;
    force-kill)
        force_kill
        ;;
    diagnostics)
        show_diagnostics
        ;;
    install-service)
        install_systemd_service
        ;;
    help)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

exit $?