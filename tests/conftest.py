"""
MVidarr Test Configuration and Fixtures
=====================================

Core pytest configuration and shared fixtures for the MVidarr test suite.
This file provides:
- Test database setup and teardown
- Authentication fixtures
- Mock service fixtures  
- Test configuration management
- Shared test utilities

Author: MVidarr Testing Infrastructure 0.9.6
Date: August 2025
"""

import os
import shutil
import sqlite3

# Import MVidarr application components
import sys
import tempfile
from typing import Any, Dict, Generator
from unittest.mock import Mock, patch

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Conditional imports - only import if modules exist
try:
    from config.config import Config

    _has_config = True
except ImportError:
    _has_config = False
    Config = None

try:
    from database.connection import DatabaseManager

    _has_db = True
except ImportError:
    _has_db = False
    DatabaseManager = None

try:
    from services.auth_service import AuthService

    _has_auth = True
except ImportError:
    _has_auth = False
    AuthService = None


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """
    Session-wide test configuration.
    Creates isolated test environment settings.
    """
    return {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key-for-testing-only",
        "DATABASE_PATH": ":memory:",  # In-memory SQLite for tests
        "UPLOAD_FOLDER": tempfile.mkdtemp(),
        "THUMBNAILS_FOLDER": tempfile.mkdtemp(),
        "LOG_LEVEL": "ERROR",  # Suppress logs during testing
    }


@pytest.fixture(scope="function")
def test_db():
    """
    Function-scoped test database fixture.
    Creates fresh database for each test with automatic cleanup.
    """
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    try:
        # Initialize basic SQLite database (since we don't have MySQL schema)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artists (
                id INTEGER PRIMARY KEY,
                name TEXT,
                sort_name TEXT,
                folder_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY,
                title TEXT,
                artist_id INTEGER,
                file_path TEXT,
                thumbnail_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists (id)
            )
        """
        )
        conn.commit()
        conn.close()

        yield db_path

    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture(scope="function")
def app(test_config, test_db):
    """
    Flask application fixture with test configuration.
    Creates isolated app instance for each test.
    """
    # Skip if we can't create the app
    if not _has_config:
        pytest.skip("Config module not available")

    # Update config with test database path
    test_config["DATABASE_PATH"] = test_db

    # Try to import and create app
    try:
        # Mock the app creation for now since we may not have all dependencies
        app = Flask(__name__)
        app.config.update(test_config)

        with app.app_context():
            yield app

    except ImportError:
        pytest.skip("Flask app creation dependencies not available")


@pytest.fixture(scope="function")
def client(app):
    """
    Flask test client fixture.
    Provides test client for HTTP requests.
    """
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """
    Flask test CLI runner fixture.
    Provides CLI command testing capabilities.
    """
    return app.test_cli_runner()


@pytest.fixture(scope="function")
def authenticated_user(app, test_db):
    """
    Authenticated user fixture.
    Creates test user and provides authentication context.
    """
    user_data = {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "password_hash": "test-hash",
        "is_admin": False,
        "created_at": "2025-08-12T00:00:00Z",
    }

    # Insert test user into database
    conn = sqlite3.connect(test_db)
    conn.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            user_data["id"],
            user_data["username"],
            user_data["email"],
            user_data["password_hash"],
            user_data["is_admin"],
            user_data["created_at"],
        ),
    )
    conn.commit()
    conn.close()

    return user_data


@pytest.fixture(scope="function")
def admin_user(app, test_db):
    """
    Admin user fixture.
    Creates test admin user with elevated privileges.
    """
    admin_data = {
        "id": 2,
        "username": "admin",
        "email": "admin@example.com",
        "password_hash": "admin-hash",
        "is_admin": True,
        "created_at": "2025-08-12T00:00:00Z",
    }

    # Insert test admin into database
    conn = sqlite3.connect(test_db)
    conn.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            admin_data["id"],
            admin_data["username"],
            admin_data["email"],
            admin_data["password_hash"],
            admin_data["is_admin"],
            admin_data["created_at"],
        ),
    )
    conn.commit()
    conn.close()

    return admin_data


@pytest.fixture(scope="function")
def sample_artist_data():
    """
    Sample artist test data fixture.
    Provides consistent artist data for testing.
    """
    return {
        "id": 1,
        "name": "Test Artist",
        "sort_name": "Artist, Test",
        "folder_path": "/test/artist/folder",
        "imvdb_id": 12345,
        "spotify_id": "spotify:artist:test123",
        "lastfm_url": "https://last.fm/music/Test+Artist",
        "created_at": "2025-08-12T00:00:00Z",
        "updated_at": "2025-08-12T00:00:00Z",
    }


@pytest.fixture(scope="function")
def sample_video_data():
    """
    Sample video test data fixture.
    Provides consistent video data for testing.
    """
    return {
        "id": 1,
        "title": "Test Video",
        "artist_id": 1,
        "file_path": "/test/video/file.mp4",
        "thumbnail_path": "/test/video/thumbnail.jpg",
        "duration": 240,
        "file_size": 50000000,
        "video_codec": "h264",
        "audio_codec": "aac",
        "resolution": "1920x1080",
        "youtube_id": "test_youtube_id",
        "imvdb_id": 67890,
        "created_at": "2025-08-12T00:00:00Z",
        "updated_at": "2025-08-12T00:00:00Z",
    }


@pytest.fixture(scope="function")
def mock_youtube_service():
    """
    Mock YouTube service fixture.
    Provides mocked YouTube API responses.
    """
    mock = Mock()
    mock.search_videos.return_value = [
        {
            "id": "test_video_1",
            "title": "Test Video 1",
            "channel": "Test Channel",
            "duration": "4:00",
            "view_count": 1000000,
        }
    ]
    mock.get_video_info.return_value = {
        "title": "Test Video",
        "uploader": "Test Channel",
        "duration": 240,
        "view_count": 1000000,
        "upload_date": "20250812",
    }
    return mock


@pytest.fixture(scope="function")
def mock_imvdb_service():
    """
    Mock IMVDb service fixture.
    Provides mocked IMVDb API responses.
    """
    mock = Mock()
    mock.search_artist.return_value = [
        {
            "id": 12345,
            "name": "Test Artist",
            "url": "https://imvdb.com/artist/12345",
            "video_count": 10,
        }
    ]
    mock.get_artist_videos.return_value = [
        {
            "id": 67890,
            "title": "Test Video",
            "artist": "Test Artist",
            "year": 2025,
            "directors": ["Test Director"],
        }
    ]
    return mock


@pytest.fixture(scope="function")
def mock_file_system():
    """
    Mock file system fixture.
    Provides temporary directory structure for file operations.
    """
    temp_dir = tempfile.mkdtemp()

    # Create test directory structure
    os.makedirs(os.path.join(temp_dir, "videos"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "thumbnails"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "artists"), exist_ok=True)

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


# Test utilities
class TestUtils:
    """
    Shared test utility functions.
    """

    @staticmethod
    def create_test_file(path: str, content: bytes = b"test content") -> None:
        """Create test file with specified content."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    @staticmethod
    def assert_dict_contains(actual: Dict, expected: Dict) -> None:
        """Assert that actual dict contains all key-value pairs from expected dict."""
        for key, value in expected.items():
            assert key in actual, f"Key '{key}' not found in actual dict"
            assert (
                actual[key] == value
            ), f"Value for key '{key}' does not match: expected {value}, got {actual[key]}"


@pytest.fixture(scope="function")
def test_utils():
    """Test utilities fixture."""
    return TestUtils


# Pytest configuration
def pytest_configure(config):
    """
    Pytest configuration hook.
    Sets up test environment and markers.
    """
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "functional: mark test as functional test")
    config.addinivalue_line("markers", "api: mark test as API test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """
    Pytest collection hook.
    Automatically mark tests based on their location.
    """
    for item in items:
        # Auto-mark tests based on directory structure
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "functional" in str(item.fspath):
            item.add_marker(pytest.mark.functional)
        elif "api" in str(item.fspath):
            item.add_marker(pytest.mark.api)
