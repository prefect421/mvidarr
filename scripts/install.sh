#!/bin/bash

# MVidarr v0.9.9 - Complete Installation Script
# Production-ready installation with FastAPI, Celery, Redis, and MariaDB
# This script handles the complete setup of MVidarr

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
MVIDARR_DIR="$(pwd)"
PYTHON_MIN_VERSION="3.8"
MARIADB_VERSION="10.5"

# Function to print colored output
print_colored() {
    color=$1
    message=$2
    echo -e "${color}${message}${NC}"
}

print_header() {
    echo ""
    print_colored $CYAN "=================================================="
    print_colored $CYAN "$1"
    print_colored $CYAN "=================================================="
}

print_step() {
    print_colored $BLUE "🔧 $1"
}

print_success() {
    print_colored $GREEN "✅ $1"
}

print_warning() {
    print_colored $YELLOW "⚠️  $1"
}

print_error() {
    print_colored $RED "❌ $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python_version() {
    if command_exists python3; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"; then
            print_success "Python $PYTHON_VERSION found"
            PYTHON_CMD="python3"
            return 0
        else
            print_error "Python $PYTHON_VERSION found, but version $PYTHON_MIN_VERSION+ required"
            return 1
        fi
    elif command_exists python; then
        PYTHON_VERSION=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"; then
            print_success "Python $PYTHON_VERSION found"
            PYTHON_CMD="python"
            return 0
        else
            print_error "Python $PYTHON_VERSION found, but version $PYTHON_MIN_VERSION+ required"
            return 1
        fi
    else
        print_error "Python not found"
        return 1
    fi
}

# Function to install pip if not available
install_pip() {
    print_step "Installing pip..."
    
    # Try different methods to install pip
    if command_exists curl; then
        curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
        if [ $? -eq 0 ]; then
            $PYTHON_CMD get-pip.py
            if [ $? -eq 0 ]; then
                rm -f get-pip.py
                print_success "pip installed successfully using get-pip.py"
                return 0
            fi
            rm -f get-pip.py
        fi
    fi
    
    # Try ensurepip
    if $PYTHON_CMD -m ensurepip --upgrade >/dev/null 2>&1; then
        print_success "pip installed successfully using ensurepip"
        return 0
    fi
    
    # Try OS package manager
    case $OS in
        "ubuntu")
            if command_exists apt-get; then
                sudo apt update && sudo apt install -y python3-pip
                if [ $? -eq 0 ]; then
                    print_success "pip installed successfully using apt"
                    return 0
                fi
            fi
            ;;
        "centos"|"fedora")
            if command_exists dnf; then
                sudo dnf install -y python3-pip
            elif command_exists yum; then
                sudo yum install -y python3-pip
            fi
            if [ $? -eq 0 ]; then
                print_success "pip installed successfully using package manager"
                return 0
            fi
            ;;
        "macos")
            if command_exists brew; then
                # pip usually comes with Python on macOS via brew
                print_warning "pip should be included with Python installation"
            fi
            ;;
    esac
    
    print_error "Failed to install pip automatically"
    return 1
}

# Function to install Python dependencies
install_python_dependencies() {
    print_step "Installing Python dependencies..."
    
    # Check if pip is available, install if missing
    if ! command_exists pip3 && ! command_exists pip; then
        print_warning "pip not found. Attempting to install pip..."
        if ! install_pip; then
            print_error "Failed to install pip. Please install pip manually."
            exit 1
        fi
    fi
    
    PIP_CMD="pip3"
    if ! command_exists pip3; then
        PIP_CMD="pip"
    fi
    
    # Check if we're in an externally-managed environment
    EXTERNALLY_MANAGED=false
    if $PIP_CMD install --help | grep -q "break-system-packages" 2>/dev/null; then
        # Test if we hit the externally-managed error
        $PIP_CMD install --dry-run setuptools 2>&1 | grep -q "externally-managed-environment" && EXTERNALLY_MANAGED=true
    fi
    
    # Determine installation method
    if [ "$EXTERNALLY_MANAGED" = true ]; then
        print_warning "Detected externally-managed Python environment"
        print_step "Choose installation method:"
        echo "  1. Create virtual environment (Recommended)"
        echo "  2. Install system-wide with --break-system-packages (Not recommended)"
        echo "  3. Use system package manager (Limited packages)"
        read -p "Enter choice (1-3) [1]: " install_choice
        install_choice=${install_choice:-1}
        
        case $install_choice in
            1)
                install_with_venv
                ;;
            2)
                install_with_break_system
                ;;
            3)
                install_with_system_packages
                ;;
            *)
                print_warning "Invalid choice, using virtual environment"
                install_with_venv
                ;;
        esac
    else
        # Standard pip installation
        install_standard_pip
    fi
}

# Function to install with virtual environment
install_with_venv() {
    print_step "Creating virtual environment..."
    
    # First, try to create virtual environment without installing anything
    if $PYTHON_CMD -m venv mvidarr_venv 2>/dev/null; then
        print_success "Virtual environment created successfully"
    else
        print_warning "Failed to create virtual environment. Checking for python3-venv..."
        
        # Check if we can install python3-venv
        print_step "Virtual environment creation failed. This usually means python3-venv is not installed."
        echo "Options:"
        echo "  1. Install python3-venv with sudo (requires admin access)"
        echo "  2. Try alternative virtual environment method (python -m venv)"
        echo "  3. Use --user installation (install to user directory)"
        echo "  4. Switch to --break-system-packages method"
        read -p "Enter choice (1-4) [3]: " venv_choice
        venv_choice=${venv_choice:-3}
        
        case $venv_choice in
            1)
                install_venv_with_sudo
                ;;
            2)
                try_alternative_venv
                ;;
            3)
                install_with_user_flag
                return
                ;;
            4)
                print_step "Switching to --break-system-packages method"
                install_with_break_system
                return
                ;;
            *)
                print_warning "Invalid choice, using --user installation"
                install_with_user_flag
                return
                ;;
        esac
    fi
    
    # If we reach here, venv was created successfully
    setup_virtual_environment
}

# Function to install python3-venv with sudo
install_venv_with_sudo() {
    print_step "Attempting to install python3-venv with sudo..."
    
    case $OS in
        "ubuntu")
            if sudo apt update && sudo apt install -y python3-venv; then
                print_success "python3-venv installed successfully"
            else
                print_error "Failed to install python3-venv via apt"
                fallback_venv_options
                return
            fi
            ;;
        "centos"|"fedora")
            if command_exists dnf; then
                if sudo dnf install -y python3-venv; then
                    print_success "python3-venv installed successfully"
                else
                    print_error "Failed to install python3-venv via dnf"
                    fallback_venv_options
                    return
                fi
            else
                if sudo yum install -y python3-venv; then
                    print_success "python3-venv installed successfully"
                else
                    print_error "Failed to install python3-venv via yum"
                    fallback_venv_options
                    return
                fi
            fi
            ;;
        *)
            print_error "Automatic python3-venv installation not supported for this OS"
            fallback_venv_options
            return
            ;;
    esac
    
    # Try creating venv again after installation
    if $PYTHON_CMD -m venv mvidarr_venv; then
        print_success "Virtual environment created successfully after installing python3-venv"
        setup_virtual_environment
    else
        print_error "Still failed to create virtual environment even after installing python3-venv"
        fallback_venv_options
    fi
}

# Function to try alternative venv methods
try_alternative_venv() {
    print_step "Trying alternative virtual environment methods..."
    
    # Try with python instead of python3
    if command_exists python && python -m venv mvidarr_venv 2>/dev/null; then
        print_success "Virtual environment created using 'python -m venv'"
        setup_virtual_environment
        return
    fi
    
    # Try virtualenv if available
    if command_exists virtualenv; then
        if virtualenv mvidarr_venv 2>/dev/null; then
            print_success "Virtual environment created using 'virtualenv'"
            setup_virtual_environment
            return
        fi
    fi
    
    # Try installing virtualenv with --user
    print_step "Trying to install virtualenv with --user..."
    if $PIP_CMD install --user virtualenv 2>/dev/null; then
        # Add user bin to PATH temporarily
        export PATH="$HOME/.local/bin:$PATH"
        if command_exists virtualenv && virtualenv mvidarr_venv 2>/dev/null; then
            print_success "Virtual environment created using user-installed virtualenv"
            setup_virtual_environment
            return
        fi
    fi
    
    print_error "All virtual environment methods failed"
    fallback_venv_options
}

# Function to handle venv fallback options
fallback_venv_options() {
    print_warning "Virtual environment creation failed. Available alternatives:"
    echo "  1. Use --user installation (install to ~/.local/)"
    echo "  2. Use --break-system-packages (not recommended)"
    echo "  3. Exit and install python3-venv manually"
    read -p "Enter choice (1-3) [1]: " fallback_choice
    fallback_choice=${fallback_choice:-1}
    
    case $fallback_choice in
        1)
            install_with_user_flag
            ;;
        2)
            install_with_break_system
            ;;
        3)
            print_step "To install python3-venv manually:"
            case $OS in
                "ubuntu")
                    echo "  sudo apt update && sudo apt install python3-venv"
                    ;;
                "centos"|"fedora")
                    if command_exists dnf; then
                        echo "  sudo dnf install python3-venv"
                    else
                        echo "  sudo yum install python3-venv"
                    fi
                    ;;
                *)
                    echo "  Install python3-venv using your system's package manager"
                    ;;
            esac
            echo "Then run the installer again."
            exit 1
            ;;
    esac
}

# Function to install with --user flag
install_with_user_flag() {
    print_step "Installing dependencies to user directory (~/.local/)..."
    print_warning "Note: This installs packages to your user directory, not system-wide"
    
    # Ensure ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
        print_step "Added ~/.local/bin to PATH for this session"
        
        # Add to shell profile for persistence
        add_local_bin_to_path
    fi
    
    install_packages_with_pip "$PIP_CMD --user"
    
    print_success "Dependencies installed to user directory"
    print_warning "Make sure ~/.local/bin is in your PATH to run the application"
    
    # Create startup script that ensures PATH is set
    create_user_startup_script
}

# Function to add ~/.local/bin to PATH permanently
add_local_bin_to_path() {
    local shell_profile=""
    
    # Detect shell and profile file
    if [[ "$SHELL" == *"bash"* ]]; then
        if [[ -f "$HOME/.bashrc" ]]; then
            shell_profile="$HOME/.bashrc"
        elif [[ -f "$HOME/.bash_profile" ]]; then
            shell_profile="$HOME/.bash_profile"
        fi
    elif [[ "$SHELL" == *"zsh"* ]]; then
        shell_profile="$HOME/.zshrc"
    fi
    
    if [[ -n "$shell_profile" && -f "$shell_profile" ]]; then
        # Check if PATH export already exists
        if ! grep -q "HOME/.local/bin" "$shell_profile"; then
            echo '# Added by MVidarr installer' >> "$shell_profile"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_profile"
            print_step "Added ~/.local/bin to PATH in $shell_profile"
            print_step "Run 'source $shell_profile' or restart your terminal to apply"
        fi
    else
        print_warning "Could not automatically add ~/.local/bin to your shell profile"
        print_step "Manually add this line to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
    fi
}

# Function to create user installation startup script
create_user_startup_script() {
    cat > start_mvidarr.sh << 'EOF'
#!/bin/bash
# MVidarr Enhanced - Start with User Installation
# Ensures ~/.local/bin is in PATH

cd "$(dirname "$0")"

# Add ~/.local/bin to PATH if not already there
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# Start the application
python3 app.py
EOF
    chmod +x start_mvidarr.sh
    
    print_success "Created start_mvidarr.sh script for user installation"
}

# Function to setup virtual environment (common code)
setup_virtual_environment() {
    # Activate virtual environment
    source mvidarr_venv/bin/activate
    
    # Update pip in virtual environment
    pip install --upgrade pip
    
    # Install dependencies in virtual environment
    install_packages_with_pip "pip"
    
    print_success "Virtual environment created and configured"
    print_step "To activate the virtual environment in the future, run:"
    echo "    source $MVIDARR_DIR/mvidarr_venv/bin/activate"
    
    # Create activation script
    cat > start_with_venv.sh << 'EOF'
#!/bin/bash
# MVidarr Enhanced - Start with Virtual Environment
cd "$(dirname "$0")"
source mvidarr_venv/bin/activate
python app.py
EOF
    chmod +x start_with_venv.sh
    
    print_success "Created start_with_venv.sh script for easy startup"
    
    # Update PYTHON_CMD for the rest of the installation
    PYTHON_CMD="python"  # Inside venv, python points to the right version
}

# Function to install with --break-system-packages
install_with_break_system() {
    print_warning "Installing system-wide with --break-system-packages"
    print_warning "This may interfere with system packages. Proceed with caution!"
    read -p "Are you sure you want to continue? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        print_step "Falling back to virtual environment method"
        install_with_venv
        return
    fi
    
    install_packages_with_pip "$PIP_CMD --break-system-packages"
}

# Function to install with system package manager
install_with_system_packages() {
    print_step "Installing dependencies using system package manager..."
    
    case $OS in
        "ubuntu")
            sudo apt update
            sudo apt install -y python3-flask python3-requests python3-bcrypt python3-dotenv
            # Optional packages that might not be available
            sudo apt install -y python3-mysql.connector || print_warning "mysql-connector not available via apt"
            ;;
        "centos"|"fedora")
            if command_exists dnf; then
                sudo dnf install -y python3-flask python3-requests python3-bcrypt
            else
                sudo yum install -y python3-flask python3-requests
            fi
            ;;
        *)
            print_error "System package installation not supported for this OS"
            print_step "Falling back to virtual environment method"
            install_with_venv
            return
            ;;
    esac
    
    print_warning "Some packages may not be available via system package manager"
    print_warning "Consider using virtual environment for full functionality"
}

# Function to install packages with pip
install_packages_with_pip() {
    local pip_command="$1"
    
    # Install core dependencies
    print_step "Installing core dependencies..."
    $pip_command install flask==2.3.3 requests==2.31.0
    
    # Install recommended dependencies
    print_step "Installing recommended dependencies..."
    $pip_command install mysql-connector-python==8.1.0 bcrypt==4.0.1 "flask-cors>=6.0.0" python-dotenv==1.0.0
    
    # Install optional dependencies
    print_step "Installing optional dependencies..."
    $pip_command install schedule==1.2.0 yt-dlp==2023.7.6
}

# Function for standard pip installation (legacy systems)
install_standard_pip() {
    install_packages_with_pip "$PIP_CMD"
    print_success "Python dependencies installed"
}

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command_exists apt-get; then
            OS="ubuntu"
        elif command_exists yum; then
            OS="centos"
        elif command_exists dnf; then
            OS="fedora"
        else
            OS="linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        OS="unknown"
    fi
    
    print_step "Detected OS: $OS"
}

# Function to install MariaDB
install_mariadb() {
    print_step "Installing MariaDB..."
    
    case $OS in
        "ubuntu")
            sudo apt update
            sudo apt install -y mariadb-server mariadb-client
            sudo systemctl start mariadb
            sudo systemctl enable mariadb
            ;;
        "centos"|"fedora")
            if command_exists dnf; then
                sudo dnf install -y mariadb-server mariadb
            else
                sudo yum install -y mariadb-server mariadb
            fi
            sudo systemctl start mariadb
            sudo systemctl enable mariadb
            ;;
        "macos")
            if command_exists brew; then
                brew install mariadb
                brew services start mariadb
            else
                print_error "Homebrew not found. Please install MariaDB manually."
                return 1
            fi
            ;;
        *)
            print_warning "Unsupported OS for automatic MariaDB installation"
            print_warning "Please install MariaDB manually"
            return 1
            ;;
    esac
    
    print_success "MariaDB installed and started"
}

# Function to setup MariaDB database
setup_mariadb() {
    print_step "Setting up MariaDB database..."
    
    # Check if MariaDB is running
    if ! systemctl is-active --quiet mariadb 2>/dev/null && ! brew services list | grep mariadb | grep started >/dev/null 2>&1; then
        print_error "MariaDB is not running. Please start MariaDB service."
        return 1
    fi
    
    # Create database and user
    mysql -u root -p << EOF
CREATE DATABASE IF NOT EXISTS mvidarr_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'mvidarr'@'localhost' IDENTIFIED BY 'mvidarr123';
GRANT ALL PRIVILEGES ON mvidarr_db.* TO 'mvidarr'@'localhost';
FLUSH PRIVILEGES;
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Database and user created successfully"
    else
        print_warning "Database setup may have failed. You can set it up manually later."
    fi
}

# Function to create environment file
create_environment_file() {
    print_step "Creating environment configuration..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.template" ]; then
            cp .env.template .env
            print_success "Environment file created from template"
        else
            cat > .env << EOF
# MVidarr Enhanced Configuration

# MariaDB Configuration
MARIADB_HOST=localhost
MARIADB_PORT=3306
MARIADB_USER=mvidarr
MARIADB_PASSWORD=mvidarr123
MARIADB_DATABASE=mvidarr_db

# Application Settings
APP_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || echo "change-this-secret-key")
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=5000

# MeTube Configuration
METUBE_URL=http://localhost:8081

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/mvidarr.log
EOF
            print_success "Environment file created with defaults"
        fi
    else
        print_warning "Environment file already exists, skipping"
    fi
}

# Function to create directory structure
create_directories() {
    print_step "Creating directory structure..."
    
    mkdir -p logs
    mkdir -p downloads/{music_videos,audio,thumbnails}
    mkdir -p data/backups
    
    print_success "Directory structure created"
}

# Function to set permissions
set_permissions() {
    print_step "Setting file permissions..."
    
    chmod +x app.py
    chmod +x scripts/*.sh 2>/dev/null || true
    chmod 600 .env 2>/dev/null || true
    
    # Make service management script executable
    chmod +x scripts/manage_service.sh 2>/dev/null || true
    
    print_success "Permissions set"
}

# Function to test installation
test_installation() {
    print_step "Testing installation..."
    
    # Test Python dependencies
    $PYTHON_CMD -c "import flask, requests; print('✅ Core dependencies OK')" || {
        print_error "Core dependencies test failed"
        return 1
    }
    
    # Test optional dependencies
    $PYTHON_CMD -c "import mysql.connector, bcrypt; print('✅ Database dependencies OK')" || {
        print_warning "Optional dependencies missing - some features may be limited"
    }
    
    # Test database connection
    if command_exists mysql; then
        mysql -u mvidarr -pmvidarr123 -e "SELECT 1;" mvidarr_db >/dev/null 2>&1 && {
            print_success "Database connection test passed"
        } || {
            print_warning "Database connection test failed - check MariaDB setup"
        }
    fi
    
    print_success "Installation test completed"
}

# Function to create systemd service (Linux only)
create_systemd_service() {
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "centos" ]] || [[ "$OS" == "fedora" ]] || [[ "$OS" == "linux" ]]; then
        print_step "Creating systemd service for auto-start..."
        
        # Determine the correct Python command and working directory
        if [ -d "mvidarr_venv" ]; then
            VENV_PYTHON="$MVIDARR_DIR/mvidarr_venv/bin/python"
            EXEC_START="$VENV_PYTHON $MVIDARR_DIR/app.py"
            SERVICE_PATH="$PATH"
            print_step "Detected virtual environment, configuring service to use it"
        elif [ -f "start_mvidarr.sh" ]; then
            EXEC_START="$PYTHON_CMD $MVIDARR_DIR/app.py"
            SERVICE_PATH="$HOME/.local/bin:$PATH"
            print_step "Detected user installation, configuring service with ~/.local/bin in PATH"
        else
            EXEC_START="$PYTHON_CMD $MVIDARR_DIR/app.py"
            SERVICE_PATH="$PATH"
        fi
        
        # Create service file
        cat > /tmp/mvidarr.service << EOF
[Unit]
Description=MVidarr Enhanced - Music Video Downloader
After=network.target mariadb.service
Wants=mariadb.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER
Group=$(id -gn)
WorkingDirectory=$MVIDARR_DIR
Environment=PATH=$SERVICE_PATH
Environment=PYTHONPATH=$MVIDARR_DIR/src
ExecStart=$EXEC_START
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
TimeoutStopSec=30
KillMode=mixed

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mvidarr

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$MVIDARR_DIR

[Install]
WantedBy=multi-user.target
EOF
        
        # Install service
        if [ "$EUID" -eq 0 ]; then
            mv /tmp/mvidarr.service /etc/systemd/system/
            systemctl daemon-reload
            systemctl enable mvidarr
            print_success "Systemd service created and enabled for auto-start"
            
            # Ask if user wants to start now
            print_step "Do you want to start MVidarr service now? (y/N)"
            read -r start_now
            if [[ $start_now =~ ^[Yy]$ ]]; then
                systemctl start mvidarr
                sleep 2
                if systemctl is-active --quiet mvidarr; then
                    print_success "MVidarr service started successfully"
                    print_success "Service status: $(systemctl is-active mvidarr)"
                    print_success "Access the application at: http://localhost:5000"
                else
                    print_warning "Service failed to start. Check logs with: journalctl -u mvidarr -f"
                fi
            fi
        else
            print_warning "Creating systemd service requires root privileges."
            print_step "Run these commands as root to enable auto-start:"
            echo "  sudo mv /tmp/mvidarr.service /etc/systemd/system/"
            echo "  sudo systemctl daemon-reload"
            echo "  sudo systemctl enable mvidarr"
            echo "  sudo systemctl start mvidarr"
            echo ""
            print_step "Or re-run this installer with sudo for automatic setup"
        fi
    fi
}

# Function to create macOS LaunchAgent
create_macos_launchagent() {
    if [[ "$OS" == "macos" ]]; then
        print_step "Creating macOS LaunchAgent for auto-start..."
        
        # Create LaunchAgent directory
        mkdir -p ~/Library/LaunchAgents
        
        # Determine the correct Python command
        if [ -d "mvidarr_venv" ]; then
            PYTHON_PATH="$MVIDARR_DIR/mvidarr_venv/bin/python"
            print_step "Detected virtual environment, configuring LaunchAgent to use it"
        else
            PYTHON_PATH="$PYTHON_CMD"
        fi
        
        # Create plist file
        cat > ~/Library/LaunchAgents/com.mvidarr.enhanced.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mvidarr.enhanced</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$MVIDARR_DIR/app.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$MVIDARR_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PATH</string>
        <key>PYTHONPATH</key>
        <string>$MVIDARR_DIR/src</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$MVIDARR_DIR/logs/mvidarr-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$MVIDARR_DIR/logs/mvidarr-stderr.log</string>
</dict>
</plist>
EOF
        
        # Load the service
        launchctl load ~/Library/LaunchAgents/com.mvidarr.enhanced.plist
        
        if [ $? -eq 0 ]; then
            print_success "macOS LaunchAgent created and loaded for auto-start"
            
            # Ask if user wants to start now
            print_step "Do you want to start MVidarr now? (y/N)"
            read -r start_now
            if [[ $start_now =~ ^[Yy]$ ]]; then
                launchctl start com.mvidarr.enhanced
                sleep 2
                print_success "MVidarr service started"
                print_success "Access the application at: http://localhost:5000"
            fi
        else
            print_warning "Failed to load LaunchAgent"
        fi
        
        echo ""
        print_step "LaunchAgent Management Commands:"
        echo "  Start:   launchctl start com.mvidarr.enhanced"
        echo "  Stop:    launchctl stop com.mvidarr.enhanced"
        echo "  Restart: launchctl stop com.mvidarr.enhanced && launchctl start com.mvidarr.enhanced"
        echo "  Remove:  launchctl unload ~/Library/LaunchAgents/com.mvidarr.enhanced.plist"
    fi
}

# Function to display final instructions
show_final_instructions() {
    print_header "🎉 Installation Complete!"
    
    echo ""
    print_colored $GREEN "MVidarr Enhanced v2.0 has been installed successfully!"
    echo ""
    
    print_colored $CYAN "📋 Next Steps:"
    echo ""
    
    print_colored $YELLOW "1. 🔧 Configuration:"
    echo "   - Edit .env file to customize settings"
    echo "   - Update MariaDB password if needed"
    echo "   - Configure YouTube API key for search functionality"
    echo ""
    
    print_colored $YELLOW "2. 🚀 Start the application:"
    if [ -d "mvidarr_venv" ]; then
        echo "   Using virtual environment:"
        echo "   ./start_with_venv.sh"
        echo "   OR manually:"
        echo "   source mvidarr_venv/bin/activate && python app.py"
    elif [ -f "start_mvidarr.sh" ]; then
        echo "   Using user installation:"
        echo "   ./start_mvidarr.sh"
        echo "   OR manually (ensure ~/.local/bin is in PATH):"
        echo "   python3 app.py"
    else
        echo "   $PYTHON_CMD app.py"
    fi
    echo ""
    
    print_colored $YELLOW "3. 🌐 Access the application:"
    echo "   Open: http://localhost:5000"
    echo "   Default login: Admin / Admin"
    echo "   ⚠️  Change the default password immediately!"
    echo ""
    
    print_colored $YELLOW "4. 🔧 System Service:"
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "centos" ]] || [[ "$OS" == "fedora" ]] || [[ "$OS" == "linux" ]]; then
        echo "   sudo systemctl start mvidarr    # Start service"
        echo "   sudo systemctl stop mvidarr     # Stop service"
        echo "   sudo systemctl status mvidarr   # Check status"
        echo "   sudo journalctl -u mvidarr -f   # View logs"
    elif [[ "$OS" == "macos" ]]; then
        echo "   launchctl start com.mvidarr.enhanced   # Start service"
        echo "   launchctl stop com.mvidarr.enhanced    # Stop service"
        echo "   tail -f logs/mvidarr-stdout.log        # View logs"
    fi
    
    print_colored $YELLOW "5. 📖 Documentation:"
    echo "   - MARIADB_SETUP.md - Database setup guide"
    echo "   - FIXES_APPLIED.md - Recent changes and fixes"
    echo "   - Configuration options in .env file"
    echo ""
    
    print_colored $PURPLE "🔗 Useful Commands:"
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "centos" ]] || [[ "$OS" == "fedora" ]] || [[ "$OS" == "linux" ]]; then
        echo "   Service control: ./scripts/manage_service.sh [start|stop|status|logs]"
        echo "   Test database: mysql -u mvidarr -pmvidarr123 mvidarr_db"
        echo "   Manual start: $PYTHON_CMD app.py"
        echo "   Service logs: sudo journalctl -u mvidarr -f"
        echo "   Check status: curl http://localhost:5000/api/health"
    elif [[ "$OS" == "macos" ]]; then
        echo "   Service control: ./scripts/manage_service.sh [start|stop|status|logs]"
        echo "   Test database: mysql -u mvidarr -pmvidarr123 mvidarr_db"
        echo "   Manual start: $PYTHON_CMD app.py"
        echo "   Service logs: tail -f logs/mvidarr-stdout.log"
        echo "   Check status: curl http://localhost:5000/api/health"
    else
        echo "   Test database: mysql -u mvidarr -pmvidarr123 mvidarr_db"
        echo "   Manual start: $PYTHON_CMD app.py"
        echo "   View logs: tail -f logs/mvidarr.log"
        echo "   Check status: curl http://localhost:5000/api/health"
    fi
    echo ""
    
    print_colored $GREEN "✨ Enjoy using MVidarr Enhanced!"
}

# Main installation function
main() {
    print_header "MVidarr Enhanced v2.0 - Installation Script"
    
    print_colored $CYAN "This script will install and configure MVidarr Enhanced"
    print_colored $CYAN "Press Ctrl+C to cancel, or press Enter to continue..."
    read -r
    
    # Detect OS
    detect_os
    
    # Check Python
    print_header "Checking Python Installation"
    if ! check_python_version; then
        print_error "Python $PYTHON_MIN_VERSION+ is required"
        exit 1
    fi
    
    # Install Python dependencies
    print_header "Installing Python Dependencies"
    install_python_dependencies
    
    # Setup MariaDB
    print_header "MariaDB Setup"
    print_step "Do you want to install MariaDB? (y/N)"
    read -r install_db
    if [[ $install_db =~ ^[Yy]$ ]]; then
        install_mariadb
        setup_mariadb
    else
        print_warning "Skipping MariaDB installation"
        print_warning "Application will run in mock database mode"
    fi
    
    # Create environment and directories
    print_header "Application Setup"
    create_environment_file
    create_directories
    set_permissions
    
    # Test installation
    print_header "Testing Installation"
    test_installation
    
    # Create systemd service
    print_header "System Integration & Auto-Start Setup"
    create_systemd_service
    create_macos_launchagent
    
    # Show final instructions
    show_final_instructions
}

# Error handling
trap 'print_error "Installation failed! Check the output above for details."' ERR

# Run main function
main "$@"
