"""
MVidarr Test Suite
================

Comprehensive test suite for MVidarr application covering:
- Unit tests: Individual component testing
- Integration tests: Component interaction testing  
- Functional tests: End-to-end workflow testing
- API tests: REST endpoint testing

Test Structure:
- /unit/: Unit tests for individual modules
- /integration/: Integration tests for component interaction
- /functional/: Functional tests for user workflows
- /api/: API endpoint tests

Test Execution:
```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit
pytest -m integration  
pytest -m functional
pytest -m api

# Run with coverage
pytest --cov=src --cov-report=html

# Run slow tests
pytest -m slow

# Skip external service tests
pytest -m "not external"
```

Version: 0.9.6
Author: MVidarr Testing Infrastructure
Date: August 2025
"""

__version__ = "0.9.6"
__author__ = "MVidarr Testing Infrastructure"
