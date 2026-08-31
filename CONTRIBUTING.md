# Contributing to MVidarr

## Welcome Contributors! 🎉

Thank you for your interest in contributing to MVidarr! This document provides guidelines for contributing to the project, including development setup, coding standards, and submission procedures.

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contributing Guidelines](#contributing-guidelines)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Issue Reporting](#issue-reporting)
- [Pull Request Process](#pull-request-process)
- [Community Guidelines](#community-guidelines)

## 🚀 Getting Started

### Types of Contributions

We welcome various types of contributions:

- **🐛 Bug Reports**: Help us identify and fix issues
- **✨ Feature Requests**: Suggest new functionality
- **💻 Code Contributions**: Bug fixes, features, improvements
- **📚 Documentation**: Improve or create documentation
- **🎨 UI/UX Improvements**: Enhance user interface and experience
- **🧪 Testing**: Add or improve test coverage
- **🔧 DevOps**: Improve build, deployment, and infrastructure

### Before You Start

1. **Check Existing Issues**: Search [GitHub Issues](https://github.com/prefect421/mvidarr/issues) to avoid duplicates
2. **Read Documentation**: Familiarize yourself with the project architecture
3. **Join Discussions**: Engage with the community for major changes
4. **Follow Guidelines**: Ensure your contribution follows project standards

## 🔧 Development Setup

### Prerequisites

- **Python 3.12+** - Required for backend development
- **Git** - Version control
- **Docker** (optional) - For containerized development
- **MariaDB 11.4+** or **MySQL 8.0+** - Database (required; MVidarr does not support SQLite)

### Environment Setup

#### 1. Clone the Repository
```bash
git clone https://github.com/prefect421/mvidarr.git
cd mvidarr
```

#### 2. Create Development Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

#### 3. Configure Development Environment
```bash
# Copy environment template
cp .env.example .env

# Edit configuration for development
# Set DEBUG=true
# Configure database connection
# Add test API keys if available
```

#### 4. Verify Setup
```bash
# Run basic tests
python -m pytest tests/ -v

# Start development server - tables are created automatically on first startup
python fastapi_app.py

# Verify access at http://localhost:5000
```

Pending schema migrations (in `migrations/`) also run automatically on startup — there's no separate command needed after pulling someone else's schema change. See `docs/DATABASE_MIGRATIONS.md` if you need to add a new migration or check status via the `/api/migrations/status` endpoint.

### Development Tools Setup

#### Code Formatting (Required)
```bash
# Install development tools (pinned to match CI - see requirements-dev.txt)
pipx install black==26.3.1
pipx install isort==9.0.0
pipx install flake8==6.1.0

# Format code before committing
black src/
isort --profile black src/
flake8 src/
```

#### Pre-commit Hooks (Recommended)
```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## 📝 Contributing Guidelines

### Branch Strategy

#### Branch Naming Convention
- **Feature branches**: `feature/description-of-feature`
- **Bug fixes**: `bugfix/description-of-fix`
- **Documentation**: `docs/description-of-change`
- **Hotfixes**: `hotfix/critical-issue-fix`

#### Workflow
1. **Fork the repository** (for external contributors)
2. **Create feature branch** from `dev` branch
3. **Make changes** following coding standards
4. **Test thoroughly** using provided test suite
5. **Submit pull request** to `dev` branch

#### Example Workflow
```bash
# Create and switch to feature branch
git checkout dev
git pull origin dev
git checkout -b feature/add-spotify-integration

# Make your changes
# ... develop feature ...

# Format and test code
black src/
isort --profile black src/
python -m pytest

# Commit changes
git add .
git commit -m "Add Spotify playlist integration

- Implement OAuth flow for Spotify authentication
- Add playlist synchronization functionality
- Update settings UI for Spotify configuration
- Add comprehensive tests for new features"

# Push and create PR
git push origin feature/add-spotify-integration
```

### Commit Message Guidelines

#### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

#### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Formatting changes (no code changes)
- **refactor**: Code refactoring
- **test**: Adding or updating tests
- **chore**: Maintenance tasks

#### Examples
```bash
# Good commit messages
feat(api): add bulk video download endpoint
fix(ui): resolve modal dialog click interference
docs(setup): update installation instructions for Docker
refactor(services): extract common API client functionality
test(videos): add integration tests for video discovery

# Poor commit messages
fix stuff
update files
changes
```

## 💻 Code Standards

### Python Code Style

#### Formatting Requirements
- **Black**: Code formatting (version 26.3.1 — pinned in `requirements-dev.txt`, must match exactly or CI's `black --check` will disagree with your local run)
- **isort**: Import sorting with `--profile black`
- **Line length**: 88 characters (Black default)
- **String quotes**: Double quotes preferred

#### Code Quality
```bash
# Run all quality checks
black --check src/
isort --profile black --check-only src/
flake8 src/
mypy src/ --ignore-missing-imports
```

#### Code Organization
```python
# File structure example
"""
Module docstring describing purpose and usage.
"""

# Standard library imports
import os
import sys
from pathlib import Path

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Column, Integer, String

# Local imports
from src.database.models import Artist, Video
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

# Constants
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3

# Module-level logger
logger = get_logger(__name__)


class ExampleService:
    """Service class with proper docstring."""
    
    def __init__(self):
        """Initialize service with required dependencies."""
        self.settings = SettingsService()
    
    def process_data(self, data: dict) -> dict:
        """
        Process input data and return results.
        
        Args:
            data: Input data dictionary
            
        Returns:
            Processed data dictionary
            
        Raises:
            ValueError: If data format is invalid
        """
        # Implementation here
        pass
```

### Frontend Code Style

#### JavaScript Standards
- **ES6+**: Modern JavaScript features
- **Consistent formatting**: 2-space indentation
- **Error handling**: Proper try/catch blocks
- **Documentation**: JSDoc comments for functions

#### CSS Standards
- **Modular CSS**: Separate files for different components
- **CSS Variables**: Use for theming and consistency
- **Mobile-first**: Responsive design approach
- **Accessibility**: WCAG 2.1 compliance

### Database Standards

#### Model Design
```python
class Artist(Base):
    """Artist model with proper relationships and constraints."""
    
    __tablename__ = 'artists'
    
    # Primary key
    id = Column(Integer, primary_key=True)
    
    # Required fields
    name = Column(String(255), nullable=False, unique=True, index=True)
    
    # Optional fields with defaults
    bio = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign keys and relationships
    videos = relationship("Video", back_populates="artist", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Artist(id={self.id}, name='{self.name}')>"
```

#### Migration Standards
- **Incremental**: Each migration should be reversible
- **Documented**: Clear migration descriptions
- **Tested**: Verify migrations work on sample data

## 🧪 Testing

### Test Categories

#### Unit Tests
```python
# Test individual functions and methods
def test_artist_creation():
    """Test artist model creation and validation."""
    artist = Artist(name="Test Artist")
    assert artist.name == "Test Artist"
    assert artist.bio == ""  # Default value
```

#### Integration Tests
```python
# Test component interactions
def test_video_discovery_flow():
    """Test complete video discovery workflow."""
    # Setup test artist
    # Mock API responses
    # Execute discovery
    # Verify results
```

#### API Tests
```python
# Test API endpoints using FastAPI's TestClient
def test_artists_list_endpoint(client):
    """Test artists listing API endpoint."""
    response = client.get('/api/artists')
    assert response.status_code == 200
    assert 'artists' in response.json()  # note: a method call, not a property
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=src

# Run specific test file
python -m pytest tests/test_artists.py

# Run with verbose output
python -m pytest -v

# Run only failed tests
python -m pytest --lf
```

### Test Guidelines
- **Test coverage**: Aim for >80% code coverage
- **Test isolation**: Each test should be independent
- **Descriptive names**: Test function names should describe what they test
- **Mock external services**: Don't rely on external APIs in tests
- **Data fixtures**: Use fixtures for test data setup

## 📚 Documentation

### Documentation Standards

#### Code Documentation
```python
def discover_videos_for_artist(self, artist_id: int) -> List[Video]:
    """
    Discover new videos for a specific artist.
    
    This method searches external services (IMVDB, YouTube) to find
    music videos associated with the given artist. It filters out
    duplicates and videos that already exist in the database.
    
    Args:
        artist_id: Database ID of the artist
        
    Returns:
        List of newly discovered Video objects
        
    Raises:
        ArtistNotFoundError: If artist_id doesn't exist
        APIError: If external service requests fail
        
    Example:
        >>> service = VideoDiscoveryService()
        >>> videos = service.discover_videos_for_artist(123)
        >>> len(videos)
        5
    """
```

#### API Documentation
- Use OpenAPI/Swagger specifications
- Include request/response examples
- Document error responses
- Provide usage examples

#### User Documentation
- **Clear instructions**: Step-by-step procedures
- **Screenshots**: Visual guides for UI features
- **Examples**: Real-world usage scenarios
- **Troubleshooting**: Common issues and solutions

### Documentation Updates

When making changes that affect users or developers:

1. **Update relevant documentation files**
2. **Add examples for new features**
3. **Update API documentation if applicable**
4. **Include migration guides for breaking changes**

## 🐛 Issue Reporting

### Bug Reports

#### Before Reporting
1. **Search existing issues** for duplicates
2. **Test in latest version** to ensure issue still exists
3. **Gather system information** and logs
4. **Create minimal reproduction steps**

#### Bug Report Template
```markdown
**Describe the Bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '...'
3. Scroll down to '...'
4. See error

**Expected Behavior**
What you expected to happen.

**Screenshots**
If applicable, add screenshots.

**Environment**
- OS: [e.g. Ubuntu 20.04]
- MVidarr Version: [e.g. 1.0.1]
- Python Version: [e.g. 3.12.7]
- Browser: [e.g. Chrome 95.0]

**Additional Context**
Any other context about the problem.

**Logs**
```
Paste relevant log entries here
```
```

### Feature Requests

#### Feature Request Template
```markdown
**Is your feature request related to a problem?**
A clear description of the problem.

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Alternative solutions or features considered.

**Additional context**
Any other context about the feature request.

**Implementation suggestions**
If you have ideas about implementation.
```

## 🔄 Pull Request Process

### Before Submitting

1. **Ensure tests pass**: Run full test suite
2. **Update documentation**: Include relevant docs updates
3. **Follow commit guidelines**: Proper commit messages
4. **Check code quality**: Run linting and formatting tools
5. **Verify functionality**: Test your changes thoroughly

### PR Description Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed
- [ ] All existing tests pass

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Code is commented where necessary
- [ ] Documentation updated
- [ ] No new warnings introduced

## Screenshots (if applicable)
Include screenshots for UI changes.

## Additional Notes
Any additional information for reviewers.
```

### Review Process

1. **Automated Checks**: CI/CD pipeline runs tests and quality checks
2. **Code Review**: Maintainers review code for quality and design
3. **Testing**: Changes tested in development environment
4. **Approval**: Approved changes merged to appropriate branch

### Review Criteria

- **Functionality**: Does it work as intended?
- **Code Quality**: Is it well-written and maintainable?
- **Performance**: Does it impact system performance?
- **Security**: Are there any security implications?
- **Documentation**: Is it properly documented?
- **Tests**: Are there adequate tests?

## 🤝 Community Guidelines

### Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. Please:

- **Be respectful**: Treat all community members with respect
- **Be inclusive**: Welcome newcomers and help them get started  
- **Be constructive**: Provide helpful feedback and suggestions
- **Be patient**: Remember that everyone is learning
- **Be professional**: Maintain professional standards in all interactions

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **Pull Requests**: Code contributions and discussions
- **Discussions**: General questions and community chat
- **Documentation**: In-line comments and documentation updates

### Getting Help

- **Documentation**: Check existing documentation first
- **Issues**: Search existing issues for similar problems
- **Discussions**: Ask questions in GitHub Discussions
- **Code Review**: Learn from feedback on pull requests

## 🏆 Recognition

### Contributors

All contributors are recognized in:
- **README.md**: Contributors section
- **Release Notes**: Feature/fix attribution
- **Git History**: Permanent record of contributions

### Contribution Types

We value all types of contributions:
- **Code**: Features, fixes, improvements
- **Documentation**: Writing, editing, translations
- **Testing**: Bug reports, test cases, QA
- **Design**: UI/UX improvements, graphics
- **Community**: Helping others, organizing events

## 📈 Development Roadmap

### Current Priorities

1. **Performance Optimization**: Database and UI performance improvements
2. **External Integrations**: More music service integrations
3. **User Experience**: UI/UX enhancements
4. **Testing**: Increased test coverage
5. **Documentation**: Comprehensive documentation updates

### Future Goals

- **Plugin System**: Extensible architecture for community plugins
- **Mobile App**: Dedicated mobile application
- **Advanced Analytics**: Library analytics and insights
- **Cloud Integration**: Cloud storage and sync options

## 📞 Contact

### Maintainers

- **Project Lead**: [@prefect421](https://github.com/prefect421)

### Support Channels

- **GitHub Issues**: [Report bugs or request features](https://github.com/prefect421/mvidarr/issues)
- **GitHub Discussions**: [Community discussions](https://github.com/prefect421/mvidarr/discussions)
- **Documentation**: [Project documentation](https://prefect421.github.io/mvidarr)

---

Thank you for contributing to MVidarr! Your contributions help make this project better for everyone. 🎵🎬✨