# Developer Setup Guide

## Overview

This guide provides comprehensive setup instructions for developers contributing to MVidarr. It covers both local development environments and advanced development workflows used by the core team.

## Prerequisites

### System Requirements

#### Minimum Requirements
- **CPU**: 2+ cores, 2.0GHz+
- **RAM**: 4GB (8GB recommended for Docker development)
- **Storage**: 20GB available space (for code, dependencies, test data)
- **Network**: Stable internet connection for API services

#### Recommended Development Setup
- **CPU**: 4+ cores, 3.0GHz+
- **RAM**: 16GB+ (for smooth Docker builds and multiple services)
- **Storage**: 50GB+ available space
- **Network**: High-speed internet for faster builds and API testing

### Required Software

#### Core Development Tools
```bash
# Python 3.12+ (required)
python3 --version  # Should be 3.12 or higher

# Git (latest version recommended)
git --version

# Docker & Docker Compose (for containerized development)
docker --version
docker-compose --version

# Node.js & npm (for frontend tools, optional)
node --version
npm --version
```

#### Python Package Management
```bash
# pip (should come with Python 3.12+)
pip --version

# pipx for isolated tool installation (recommended)
pip install --user pipx
pipx ensurepath

# Install development tools via pipx
pipx install black==24.3.0
pipx install isort
pipx install flake8
pipx install mypy
```

#### Database (Choose One)
**Option 1: Docker MySQL (Recommended for Development)**
```bash
# Included in docker-compose.yml - no separate installation needed
docker-compose up mysql
```

**Option 2: Local MySQL**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install mysql-server mysql-client

# macOS
brew install mysql
brew services start mysql

# Create development database
mysql -u root -p
CREATE DATABASE mvidarr_enhanced;
CREATE USER 'mvidarr'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON mvidarr_enhanced.* TO 'mvidarr'@'localhost';
FLUSH PRIVILEGES;
```

## Development Environment Setup

### 1. Repository Setup

#### Clone Repository
```bash
# Clone the main repository
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr

# Set up development branch
git checkout dev

# Create your feature branch
git checkout -b feature/your-feature-name
```

#### Repository Structure Overview
```
mvidarr/
├── src/                    # Python application source code
│   ├── api/               # REST API endpoints
│   ├── core/              # Core business logic
│   ├── models/            # Database models
│   └── utils/             # Utility functions
├── frontend/              # Web interface (HTML, CSS, JS)
│   ├── CSS/              # Stylesheets
│   ├── JS/               # JavaScript files
│   └── templates/        # Jinja2 templates
├── migrations/            # Database migration scripts
├── tests/                 # Test suites
├── scripts/               # Utility scripts
├── docs/                  # Documentation
├── docker-config.yml.sample  # Docker configuration template
├── requirements-prod.txt      # Production dependencies
├── requirements-dev.txt       # Development dependencies
└── docker-compose.yml        # Multi-container setup
```

### 2. Python Environment Setup

#### Option A: Virtual Environment (Recommended for Local Development)
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Upgrade pip
pip install --upgrade pip

# Install development dependencies
pip install -r requirements-dev.txt

# Install production dependencies
pip install -r requirements-prod.txt

# Verify installation
python -c "import flask, pymysql, requests; print('Dependencies installed successfully')"
```

#### Option B: Docker Development (Isolated Environment)
```bash
# Copy configuration template
cp docker-config.yml.sample docker-config.yml

# Edit configuration for development
nano docker-config.yml

# Start development environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Access development container
docker-compose exec mvidarr bash
```

### 3. Database Setup

#### Development Database Configuration

**For Local MySQL:**
```bash
# Set environment variables
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=mvidarr_enhanced
export DB_USER=mvidarr
export DB_PASSWORD=secure_password

# Initialize database schema
python -c "from src.models.database import initialize_database; initialize_database()"
```

**For Docker MySQL:**
```yaml
# In docker-config.yml
database:
  host: mysql
  port: 3306
  name: mvidarr_enhanced
  username: mvidarr
  password: secure_password
```

#### Run Database Migrations
```bash
# Check migration status
python migrations/check_migrations.py

# Run pending migrations
python migrations/run_migrations.py

# Create new migration (if needed)
python migrations/create_migration.py "Add new feature column"
```

### 4. External Service Configuration

#### Required API Keys for Development
Create a `.env` file in the project root:

```env
# IMVDb API (Required for video metadata)
IMVDB_API_KEY=your_imvdb_api_key_here

# YouTube Data API (Required for video discovery)
YOUTUBE_API_KEY=your_youtube_api_key_here

# Optional APIs for enhanced features
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
LASTFM_API_KEY=your_lastfm_api_key
LASTFM_SHARED_SECRET=your_lastfm_shared_secret

# Development settings
FLASK_ENV=development
FLASK_DEBUG=true
LOG_LEVEL=DEBUG
```

#### Obtaining API Keys

**IMVDb API Key:**
1. Visit https://imvdb.com/developers/api
2. Register for a developer account
3. Create a new application
4. Copy the API key to your `.env` file

**YouTube Data API v3:**
1. Go to https://console.developers.google.com
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials (API key)
5. Add key to your `.env` file

**Spotify API (Optional):**
1. Visit https://developer.spotify.com/dashboard
2. Create a new application
3. Get Client ID and Client Secret
4. Add to your `.env` file

### 5. Frontend Development Setup

#### Static Assets
```bash
# Frontend assets are served directly by Flask
# No build process required for basic development

# For advanced frontend development (optional):
npm install -g browser-sync
browser-sync start --proxy "localhost:5000" --files "frontend/**/*"
```

#### CSS Development
```bash
# Main stylesheets
frontend/CSS/main.css      # Core application styles
frontend/CSS/themes.css    # Theme and color variations
frontend/CSS/mobile.css    # Mobile-specific styles

# CSS organization follows BEM methodology
# No preprocessing required - plain CSS with CSS variables
```

#### JavaScript Development
```bash
# Core JavaScript files
frontend/JS/main.js        # Application initialization
frontend/JS/api.js         # API interaction utilities
frontend/JS/components/    # Reusable UI components
frontend/JS/pages/         # Page-specific functionality

# No transpilation required - modern ES6+ JavaScript
# Uses native modules and browser APIs
```

## Development Workflow

### 1. Code Quality Standards

#### Automatic Code Formatting
```bash
# Format Python code (exact version for CI compatibility)
~/.local/bin/black src/ tests/ scripts/
~/.local/bin/isort --profile black src/ tests/ scripts/

# Check formatting without changes
~/.local/bin/black --check src/
~/.local/bin/isort --profile black --check-only src/

# Lint code for style issues
~/.local/bin/flake8 src/ --max-line-length=88 --extend-ignore=E203,W503
```

#### Type Checking (Optional but Recommended)
```bash
# Run MyPy type checking
~/.local/bin/mypy src/ --ignore-missing-imports --no-strict-optional
```

#### Pre-commit Hooks Setup
```bash
# Install pre-commit
pipx install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### 2. Testing Framework

#### Running Tests

**Comprehensive Test Suite:**
```bash
# Run all tests
python comprehensive_test.py

# Run specific test categories
python comprehensive_test.py --category api
python comprehensive_test.py --category frontend
python comprehensive_test.py --category database
```

**Unit Tests:**
```bash
# Run unit tests with pytest
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

**Integration Tests:**
```bash
# Run integration tests (requires running application)
pytest tests/integration/ -v

# Run API tests
pytest tests/api/ -v
```

#### Writing Tests

**Test Structure:**
```
tests/
├── unit/                  # Unit tests for individual functions
│   ├── test_models.py    # Database model tests
│   ├── test_api.py       # API endpoint unit tests
│   └── test_utils.py     # Utility function tests
├── integration/           # Integration tests
│   ├── test_workflows.py # End-to-end workflow tests
│   └── test_external_apis.py # External API integration
└── fixtures/             # Test data and fixtures
    ├── sample_data.json  # Sample API responses
    └── test_database.sql # Test database setup
```

**Example Unit Test:**
```python
# tests/unit/test_api.py
import pytest
from unittest.mock import patch, MagicMock
from src.api.artists import get_artist_by_id

class TestArtistAPI:
    def test_get_artist_by_id_success(self):
        # Mock database response
        with patch('src.models.artists.Artist.get_by_id') as mock_get:
            mock_artist = MagicMock()
            mock_artist.to_dict.return_value = {'id': 1, 'name': 'Test Artist'}
            mock_get.return_value = mock_artist
            
            result = get_artist_by_id(1)
            
            assert result['id'] == 1
            assert result['name'] == 'Test Artist'
            mock_get.assert_called_once_with(1)
    
    def test_get_artist_by_id_not_found(self):
        with patch('src.models.artists.Artist.get_by_id') as mock_get:
            mock_get.return_value = None
            
            result = get_artist_by_id(999)
            
            assert result is None
```

### 3. Development Server

#### Running the Development Server
```bash
# Standard development server
python app.py

# With auto-reload and debugging
FLASK_ENV=development FLASK_DEBUG=1 python app.py

# Custom port
PORT=5001 python app.py

# With specific configuration
CONFIG_FILE=/path/to/dev-config.yml python app.py
```

#### Development Server Features
- **Auto-reload**: Automatically restarts when code changes
- **Debug mode**: Detailed error pages with stack traces
- **Interactive debugger**: Debug exceptions in the browser
- **Template auto-reload**: Updates templates without restart

### 4. Debugging Tools

#### Application Debugging

**Built-in Flask Debugger:**
```python
# Enable in development
app.debug = True

# Use breakpoints in code
import pdb; pdb.set_trace()

# Or use modern debugging
import debugpy
debugpy.breakpoint()
```

**Logging Configuration:**
```python
# src/utils/logger.py
import logging

# Configure development logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Use in code
logger = logging.getLogger(__name__)
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

#### Database Debugging

**Query Logging:**
```python
# Enable SQL query logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

**Database Console:**
```bash
# Access database directly
mysql -u mvidarr -p mvidarr_enhanced

# Or through Docker
docker-compose exec mysql mysql -u mvidarr -p mvidarr_enhanced
```

#### API Debugging

**Interactive API Testing:**
```bash
# Use curl for API testing
curl -X GET http://localhost:5000/api/artists

# Use httpie for better formatting
pip install httpie
http GET localhost:5000/api/artists

# Use Postman or Insomnia for GUI testing
```

**Built-in API Documentation:**
- Swagger UI: http://localhost:5000/api/docs/swagger
- ReDoc: http://localhost:5000/api/docs/redoc
- OpenAPI Spec: http://localhost:5000/api/docs/openapi.json

### 5. Admin CLI Scripts

MVidarr includes CLI utility scripts for administrative maintenance operations. These scripts are designed for admin and developer use — no email infrastructure is required.

#### Password Reset Script

**Usage:**
```bash
# List all usernames (helpful if you forgot the username)
python scripts/reset_password.py --list

# Reset a user's password
python scripts/reset_password.py username NewSecurePassw0rd!
```

**Docker Usage:**
```bash
# List usernames in a running container
docker exec mvidarr python scripts/reset_password.py --list

# Reset password in a running container
docker exec mvidarr python scripts/reset_password.py admin NewSecurePassw0rd!
```

**Features:**
- Direct database password reset (no email delivery)
- Password strength validation (enforces minimum requirements)
- User-friendly error messages for unknown usernames or weak passwords
- Lightweight alternative to password recovery emails

#### Video Index Script

**Usage:**
```bash
# Scan for new videos without indexing
python scripts/index_videos.py --scan

# Index all videos with metadata
python scripts/index_videos.py --index-all

# Index specific file with preview
python scripts/index_videos.py --preview /app/data/musicvideos/Artist/Video.mp4

# View statistics
python scripts/index_videos.py --stats
```

**Docker Usage:**
```bash
# Index all videos in running container
docker exec mvidarr python scripts/index_videos.py --index-all

# View statistics from container
docker exec mvidarr python scripts/index_videos.py --stats
```

See `docs/INITIAL_VIDEO_LOAD_GUIDE.md` for comprehensive video indexing documentation.

## Advanced Development Setup

### 1. IDE Configuration

#### Visual Studio Code Setup
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.sortImports.path": "isort",
    "python.sortImports.args": ["--profile", "black"],
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    }
}
```

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "MVidarr Debug",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/app.py",
            "env": {
                "FLASK_ENV": "development",
                "FLASK_DEBUG": "1"
            },
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
```

#### PyCharm Setup
1. **Create Project**: Open existing directory
2. **Interpreter**: Select venv/bin/python
3. **Code Style**: Import black configuration
4. **Run Configuration**: 
   - Script: app.py
   - Environment: FLASK_ENV=development

### 2. Docker Development Environment

#### Development Docker Compose
```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  mvidarr:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - ./src:/app/src:ro
      - ./frontend:/app/frontend:ro
      - ./migrations:/app/migrations:ro
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
    ports:
      - "5000:5000"
      - "5678:5678"  # Debug port
```

```dockerfile
# Dockerfile.dev
FROM python:3.12-slim

# Install development dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ pkg-config default-libmysqlclient-dev \
    curl vim git

WORKDIR /app

# Install Python dependencies
COPY requirements-dev.txt requirements-prod.txt ./
RUN pip install -r requirements-dev.txt -r requirements-prod.txt

# Copy application code
COPY . .

# Enable debugger
RUN pip install debugpy

CMD ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", "--wait-for-client", "app.py"]
```

### 3. Performance Development Tools

#### Profiling Tools
```python
# Install profiling tools
pip install line-profiler memory-profiler

# Profile specific functions
@profile
def slow_function():
    # Your code here
    pass

# Run with profiler
kernprof -l -v script.py
```

#### Database Performance Monitoring
```python
# Install query profiling
pip install flask-sqlalchemy-profiler

# In development configuration
from flask_sqlalchemy_profiler import SQLAlchemyProfiler

app = Flask(__name__)
profiler = SQLAlchemyProfiler(app)
```

### 4. Frontend Development Tools

#### Live Reload Setup
```bash
# Install browser-sync
npm install -g browser-sync

# Start with proxy to Flask app
browser-sync start --proxy "localhost:5000" --files "frontend/**/*"

# Or use Flask's built-in reloader with templates
export TEMPLATES_AUTO_RELOAD=True
```

#### CSS Development
```bash
# Use CSS custom properties for theming
:root {
  --primary-color: #007bff;
  --secondary-color: #6c757d;
  --success-color: #28a745;
}

# Organized CSS structure
frontend/CSS/
├── base.css          # Reset and base styles
├── components.css    # UI components
├── layouts.css       # Layout structures
├── themes.css        # Color themes
└── utilities.css     # Utility classes
```

## Contribution Workflow

### 1. Feature Development Process

#### Starting a New Feature
```bash
# Ensure you're on dev branch
git checkout dev
git pull origin dev

# Create feature branch
git checkout -b feature/your-feature-name

# Set up development environment
source venv/bin/activate  # if using venv
pip install -r requirements-dev.txt

# Start development server
python app.py
```

#### Development Checklist
- [ ] **Code Quality**: Format with Black and isort
- [ ] **Type Hints**: Add type annotations where appropriate
- [ ] **Documentation**: Update docstrings and comments
- [ ] **Tests**: Write unit tests for new functionality
- [ ] **Integration**: Test with existing features
- [ ] **Performance**: Profile if performance-critical
- [ ] **Security**: Review for security implications

#### Testing Before Commit
```bash
# Format and lint code
~/.local/bin/black src/ tests/
~/.local/bin/isort --profile black src/ tests/
~/.local/bin/flake8 src/

# Run tests
python comprehensive_test.py
pytest tests/ -v

# Check types (optional)
~/.local/bin/mypy src/
```

### 2. Version Management

#### Update Version Metadata
```bash
# Before significant commits, update version info
./scripts/update_version.sh

# Manually update if needed
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")

cat > version.json << EOF
{
  "version": "0.9.3",
  "build_date": "$CURRENT_TIMESTAMP",
  "git_commit": "$CURRENT_COMMIT",
  "git_branch": "dev",
  "release_name": "Current Development"
}
EOF
```

### 3. Commit and Push Process

#### Commit Standards
```bash
# Use conventional commit format
git add .
git commit -m "feat(api): add video bulk operations endpoint

- Implement bulk video operations for multiple video management
- Add support for batch status updates
- Include comprehensive error handling and validation
- Add unit tests for new functionality

Closes #123"

# Push to feature branch
git push origin feature/your-feature-name
```

#### Pull Request Process
1. **Create PR** from feature branch to dev branch
2. **Fill PR Template** with description and testing notes
3. **Request Review** from maintainers
4. **Address Feedback** and update if needed
5. **Merge** after approval (squash merge preferred)

## Troubleshooting Development Issues

### Common Development Problems

#### Python Environment Issues
```bash
# Virtual environment not activating
python3 -m venv --clear venv
source venv/bin/activate

# Dependency conflicts
pip install --upgrade pip
pip install --force-reinstall -r requirements-dev.txt

# Import errors
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

#### Database Connection Issues
```bash
# Check database connectivity
mysql -u mvidarr -p -h localhost mvidarr_enhanced

# Reset database (destructive)
python -c "from src.models.database import reset_database; reset_database()"

# Check migrations
python migrations/check_migrations.py
```

#### Docker Development Issues
```bash
# Rebuild containers
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d

# Check logs
docker-compose logs -f mvidarr

# Access container shell
docker-compose exec mvidarr bash
```

#### Frontend Development Issues
```bash
# Clear browser cache completely
# Use browser dev tools → Network → Disable cache

# Check static file serving
curl -I http://localhost:5000/static/css/main.css

# Template not updating
export TEMPLATES_AUTO_RELOAD=True
```

### Getting Help

#### Internal Resources
1. **Code Documentation**: Comprehensive docstrings in source code
2. **API Documentation**: http://localhost:5000/api/docs/swagger
3. **Database Schema**: See models/ directory for table definitions
4. **System Health**: http://localhost:5000/api/health

#### External Support
1. **GitHub Issues**: Bug reports and feature requests
2. **GitHub Discussions**: Development questions and ideas
3. **Documentation**: Complete guides in docs/ directory

## Best Practices for Contributors

### Code Style Guidelines
1. **Follow PEP 8**: Use Black formatter for consistency
2. **Type Hints**: Add type annotations for function parameters and returns
3. **Docstrings**: Use Google-style docstrings for functions and classes
4. **Error Handling**: Use specific exception types and provide helpful messages
5. **Security**: Never commit API keys or sensitive data

### Testing Guidelines
1. **Unit Tests**: Test individual functions and classes
2. **Integration Tests**: Test feature workflows end-to-end
3. **Mock External APIs**: Don't make real API calls in tests
4. **Test Data**: Use fixtures and sample data for consistent testing
5. **Edge Cases**: Test error conditions and boundary values

### Documentation Standards
1. **Code Comments**: Explain why, not what
2. **README Updates**: Keep installation and usage instructions current
3. **API Changes**: Update OpenAPI spec when changing endpoints
4. **Breaking Changes**: Document in commit messages and pull requests

---

**Ready to contribute? Start with a simple feature or bug fix to familiarize yourself with the codebase, then work your way up to more complex features. Welcome to the MVidarr development team!**