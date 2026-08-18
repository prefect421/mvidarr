#!/usr/bin/env python3
"""
Migration: Add Advanced Search Tables for MVidarr 0.9.7 - Issue #73
Version: 008
Date: 2025-08-16
Description: Creates tables for saved search presets, search analytics,
search result caching, and search suggestions.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.migration_008")


def upgrade(connection):
    """Create advanced search tables"""
    try:
        # Use the connection provided by the migration system
        # DO NOT use get_db() as it will close the connection
        if True:  # Keep indentation for minimal changes
            logger.info("Starting migration 008: Adding advanced search tables")

            # Create search_presets table (MySQL/MariaDB syntax)
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS search_presets (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    user_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    search_criteria JSON NOT NULL,
                    preset_type VARCHAR(20) NOT NULL DEFAULT 'USER_DEFINED',
                    is_public BOOLEAN DEFAULT 0,
                    is_favorite BOOLEAN DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    last_used_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """))

            # Create indexes for search_presets
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_user_id ON search_presets(user_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_type ON search_presets(preset_type)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_public ON search_presets(is_public)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_favorite ON search_presets(is_favorite)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_usage ON search_presets(usage_count)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_preset_last_used ON search_presets(last_used_at)"
                )
            )

            logger.info("Created search_presets table with indexes")

            # Create search_analytics table (MySQL/MariaDB syntax)
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS search_analytics (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    user_id INTEGER,
                    session_id VARCHAR(255),
                    event_type VARCHAR(50) NOT NULL,
                    search_query TEXT,
                    search_criteria JSON,
                    preset_id INTEGER,
                    response_time_ms INTEGER,
                    result_count INTEGER,
                    user_agent TEXT,
                    ip_address VARCHAR(45),
                    referrer VARCHAR(500),
                    event_metadata JSON,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (preset_id) REFERENCES search_presets(id) ON DELETE SET NULL
                )
            """))

            # Create indexes for search_analytics
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_user_id ON search_analytics(user_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_event_type ON search_analytics(event_type)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_preset_id ON search_analytics(preset_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_timestamp ON search_analytics(timestamp)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_response_time ON search_analytics(response_time_ms)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_analytics_session ON search_analytics(session_id)"
                )
            )

            logger.info("Created search_analytics table with indexes")

            # Create search_result_cache table (MySQL/MariaDB syntax)
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS search_result_cache (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    cache_key VARCHAR(64) UNIQUE NOT NULL,
                    search_criteria JSON NOT NULL,
                    result_data JSON NOT NULL,
                    result_count INTEGER NOT NULL,
                    response_time_ms INTEGER,
                    hit_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """))

            # Create indexes for search_result_cache
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_cache_key ON search_result_cache(cache_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_cache_expires ON search_result_cache(expires_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_cache_created ON search_result_cache(created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_cache_hit_count ON search_result_cache(hit_count)"
                )
            )

            logger.info("Created search_result_cache table with indexes")

            # Create search_suggestions table (MySQL/MariaDB syntax)
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS search_suggestions (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    suggestion_text VARCHAR(500) NOT NULL,
                    suggestion_type VARCHAR(50) NOT NULL,
                    category VARCHAR(50),
                    usage_count INTEGER DEFAULT 0,
                    success_rate FLOAT DEFAULT 0.0,
                    relevance_score FLOAT DEFAULT 1.0,
                    source_type VARCHAR(50),
                    language VARCHAR(10) DEFAULT 'en',
                    suggestion_metadata JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME
                )
            """))

            # Create indexes for search_suggestions
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_text ON search_suggestions(suggestion_text)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_type ON search_suggestions(suggestion_type)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_usage ON search_suggestions(usage_count)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_relevance ON search_suggestions(relevance_score)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_category ON search_suggestions(category)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_search_suggestion_composite ON search_suggestions(suggestion_type, usage_count, relevance_score)"
                )
            )

            logger.info("Created search_suggestions table with indexes")

            # Add enhanced search indexes to existing video and artist tables
            try:
                # Full-text search indexes for videos
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_title_fts ON videos(title)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_description_fts ON videos(description)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_search_keywords ON videos(search_keywords)"
                    )
                )

                # Composite indexes for common search patterns
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_search_composite ON videos(status, title, artist_id)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_quality_year ON videos(quality, year)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_duration_status ON videos(duration, status)"
                    )
                )
                # Note: MySQL/MariaDB doesn't support partial indexes with WHERE clause
                # Creating standard index instead
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_video_status_genres ON videos(status)"
                    )
                )

                # Artist search indexes
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_artist_name_fts ON artists(name)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_artist_search_composite ON artists(monitored, name, source)"
                    )
                )

                logger.info("Created enhanced search indexes on existing tables")

            except Exception as e:
                logger.warning(f"Some indexes may already exist: {e}")

            # Insert default system search presets
            system_presets = [
                {
                    "name": "Recently Added",
                    "description": "Videos added in the last 7 days",
                    "criteria": '{"created_after": "", "sort_by": "created_at", "sort_order": "desc"}',
                },
                {
                    "name": "High Quality Videos",
                    "description": "Videos in 1080p or higher quality",
                    "criteria": '{"quality": ["1080p", "1440p", "2160p", "4K"], "sort_by": "quality", "sort_order": "desc"}',
                },
                {
                    "name": "Downloaded Videos",
                    "description": "All downloaded videos",
                    "criteria": '{"status": ["DOWNLOADED"], "sort_by": "created_at", "sort_order": "desc"}',
                },
                {
                    "name": "Wanted Videos",
                    "description": "Videos marked as wanted but not yet downloaded",
                    "criteria": '{"status": ["WANTED"], "sort_by": "created_at", "sort_order": "desc"}',
                },
                {
                    "name": "Videos with Thumbnails",
                    "description": "Videos that have thumbnail images",
                    "criteria": '{"has_thumbnail": true, "sort_by": "created_at", "sort_order": "desc"}',
                },
                {
                    "name": "Long Format Videos",
                    "description": "Videos longer than 5 minutes",
                    "criteria": '{"duration_range": {"min": 300}, "sort_by": "duration", "sort_order": "desc"}',
                },
            ]

            for preset in system_presets:
                # Check if preset already exists
                existing = connection.execute(
                    text("""
                    SELECT id FROM search_presets 
                    WHERE name = :name AND preset_type = 'SYSTEM'
                """),
                    {"name": preset["name"]},
                ).fetchone()

                if not existing:
                    connection.execute(
                        text("""
                        INSERT INTO search_presets (
                            user_id, name, description, search_criteria, 
                            preset_type, is_public
                        ) VALUES (
                            NULL, :name, :description, :criteria, 
                            'SYSTEM', 1
                        )
                    """),
                        {
                            "name": preset["name"],
                            "description": preset["description"],
                            "criteria": preset["criteria"],
                        },
                    )

            logger.info("Created system search presets")

            # Populate search suggestions from existing data (MySQL/MariaDB syntax)
            try:
                # Add artist names as suggestions (MySQL uses INSERT IGNORE not INSERT OR IGNORE)
                connection.execute(text("""
                    INSERT IGNORE INTO search_suggestions (
                        suggestion_text, suggestion_type, category,
                        source_type, relevance_score
                    )
                    SELECT DISTINCT
                        name, 'artist', 'Artist Name',
                        'existing_data', 2.0
                    FROM artists
                    WHERE name IS NOT NULL AND TRIM(name) != ''
                """))

                # Add video titles as suggestions (limit to avoid too many)
                connection.execute(text("""
                    INSERT IGNORE INTO search_suggestions (
                        suggestion_text, suggestion_type, category,
                        source_type, relevance_score
                    )
                    SELECT DISTINCT
                        title, 'title', 'Video Title',
                        'existing_data', 1.5
                    FROM videos
                    WHERE title IS NOT NULL AND TRIM(title) != ''
                    AND CHAR_LENGTH(title) > 3
                    LIMIT 1000
                """))

                logger.info("Populated initial search suggestions from existing data")

            except Exception as e:
                logger.warning(f"Error populating search suggestions: {e}")

            # DO NOT commit here - migration system handles the commit
            logger.info(
                "Migration 008 completed successfully: Advanced search tables created"
            )

    except Exception as e:
        logger.error(f"Migration 008 failed: {e}")
        raise


def downgrade(connection):
    """Remove advanced search tables"""
    try:
        # Use the connection provided by the migration system
        if True:  # Keep indentation for minimal changes
            logger.info("Starting downgrade of migration 008")

            # Drop tables in reverse order of dependencies
            connection.execute(text("DROP TABLE IF EXISTS search_suggestions"))
            connection.execute(text("DROP TABLE IF EXISTS search_result_cache"))
            connection.execute(text("DROP TABLE IF EXISTS search_analytics"))
            connection.execute(text("DROP TABLE IF EXISTS search_presets"))

            # Remove enhanced indexes
            connection.execute(text("DROP INDEX IF EXISTS idx_video_title_fts"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_description_fts"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_search_keywords"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_search_composite"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_quality_year"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_duration_status"))
            connection.execute(text("DROP INDEX IF EXISTS idx_video_genres_status"))
            connection.execute(text("DROP INDEX IF EXISTS idx_artist_name_fts"))
            connection.execute(text("DROP INDEX IF EXISTS idx_artist_search_composite"))

            # DO NOT commit here - migration system handles the commit
            logger.info("Migration 008 downgrade completed successfully")

    except Exception as e:
        logger.error(f"Migration 008 downgrade failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Advanced Search Tables Migration")
    parser.add_argument(
        "--downgrade", action="store_true", help="Run downgrade instead of upgrade"
    )

    args = parser.parse_args()

    if args.downgrade:
        downgrade()
    else:
        upgrade()
