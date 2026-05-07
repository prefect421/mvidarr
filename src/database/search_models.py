"""
Enhanced Search Models for MVidarr 0.9.7 - Issue #73
Database models for advanced search functionality including saved presets,
search analytics, and search result caching.
"""

import hashlib
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from src.database.connection import Base


class SearchPresetType(Enum):
    """Search preset type enumeration"""

    USER_DEFINED = "USER_DEFINED"  # User-created custom preset
    SYSTEM = "SYSTEM"  # System-provided preset
    SHARED = "SHARED"  # Shared between users


class SearchAnalyticsEvent(Enum):
    """Search analytics event types"""

    SEARCH_EXECUTED = "SEARCH_EXECUTED"
    PRESET_USED = "PRESET_USED"
    PRESET_CREATED = "PRESET_CREATED"
    PRESET_MODIFIED = "PRESET_MODIFIED"
    SEARCH_EXPORTED = "SEARCH_EXPORTED"
    AUTOCOMPLETE_USED = "AUTOCOMPLETE_USED"


class SearchPreset(Base):
    """Saved search presets for advanced filtering"""

    __tablename__ = "search_presets"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # NULL for system presets
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Search criteria stored as JSON
    search_criteria = Column(JSON, nullable=False)
    # Example: {
    #     "text_query": "rock music video",
    #     "status": ["DOWNLOADED", "WANTED"],
    #     "quality": ["1080p", "720p"],
    #     "year_range": {"min": 2010, "max": 2023},
    #     "duration_range": {"min": 180, "max": 600},
    #     "genres": ["rock", "alternative"],
    #     "has_thumbnail": true,
    #     "artist_filters": {
    #         "monitored": true,
    #         "source": ["imvdb", "manual"]
    #     },
    #     "sort_by": "created_at",
    #     "sort_order": "desc"
    # }

    preset_type = Column(
        SQLEnum(SearchPresetType), default=SearchPresetType.USER_DEFINED
    )
    is_public = Column(Boolean, default=False)  # Can other users see/use this preset
    is_favorite = Column(Boolean, default=False)  # User's favorite preset

    # Usage statistics
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="search_presets")

    # Indexes
    __table_args__ = (
        Index("idx_search_preset_user_id", "user_id"),
        Index("idx_search_preset_type", "preset_type"),
        Index("idx_search_preset_public", "is_public"),
        Index("idx_search_preset_favorite", "is_favorite"),
        Index("idx_search_preset_usage", "usage_count"),
        Index("idx_search_preset_last_used", "last_used_at"),
        {"extend_existing": True},
    )

    def increment_usage(self):
        """Increment usage count and update last used timestamp"""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()

    def to_dict(self):
        """Convert preset to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "search_criteria": self.search_criteria,
            "preset_type": self.preset_type.value,
            "is_public": self.is_public,
            "is_favorite": self.is_favorite,
            "usage_count": self.usage_count,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self):
        return f"<SearchPreset(name='{self.name}', user_id={self.user_id}, type='{self.preset_type.value}')>"


class SearchAnalytics(Base):
    """Search analytics and usage tracking"""

    __tablename__ = "search_analytics"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # NULL for anonymous
    session_id = Column(String(255), nullable=True)  # Session identifier

    # Event details
    event_type = Column(SQLEnum(SearchAnalyticsEvent), nullable=False)
    search_query = Column(Text, nullable=True)  # Raw search query
    search_criteria = Column(JSON, nullable=True)  # Structured search criteria
    preset_id = Column(Integer, ForeignKey("search_presets.id"), nullable=True)

    # Performance metrics
    response_time_ms = Column(
        Integer, nullable=True
    )  # Search response time in milliseconds
    result_count = Column(Integer, nullable=True)  # Number of results returned

    # Context information
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    referrer = Column(String(500), nullable=True)

    # Additional data
    event_metadata = Column(JSON, nullable=True)  # Additional event-specific data
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="search_analytics")
    preset = relationship("SearchPreset", backref="analytics_events")

    # Indexes
    __table_args__ = (
        Index("idx_search_analytics_user_id", "user_id"),
        Index("idx_search_analytics_event_type", "event_type"),
        Index("idx_search_analytics_preset_id", "preset_id"),
        Index("idx_search_analytics_timestamp", "timestamp"),
        Index("idx_search_analytics_response_time", "response_time_ms"),
        Index("idx_search_analytics_session", "session_id"),
        {"extend_existing": True},
    )

    def to_dict(self):
        """Convert analytics event to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "search_query": self.search_query,
            "search_criteria": self.search_criteria,
            "preset_id": self.preset_id,
            "response_time_ms": self.response_time_ms,
            "result_count": self.result_count,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "referrer": self.referrer,
            "event_metadata": self.event_metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f"<SearchAnalytics(event='{self.event_type.value}', user_id={self.user_id}, response_time={self.response_time_ms}ms)>"


class SearchResultCache(Base):
    """Cache for search results to improve performance"""

    __tablename__ = "search_result_cache"

    id = Column(Integer, primary_key=True)

    # Cache key (hash of search criteria)
    cache_key = Column(String(64), unique=True, nullable=False)  # SHA-256 hash

    # Search criteria that generated this cache entry
    search_criteria = Column(JSON, nullable=False)

    # Cached results
    result_data = Column(JSON, nullable=False)  # Serialized search results
    result_count = Column(Integer, nullable=False)

    # Cache metadata
    response_time_ms = Column(Integer, nullable=True)  # Time taken to generate results
    hit_count = Column(Integer, default=0)  # Number of times this cache was used

    # Expiry and validation
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # When cache expires
    last_accessed = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_search_cache_key", "cache_key"),
        Index("idx_search_cache_expires", "expires_at"),
        Index("idx_search_cache_created", "created_at"),
        Index("idx_search_cache_hit_count", "hit_count"),
        {"extend_existing": True},
    )

    @staticmethod
    def generate_cache_key(search_criteria):
        """Generate cache key from search criteria"""
        # Sort criteria for consistent key generation
        import json

        normalized_criteria = json.dumps(search_criteria, sort_keys=True)
        return hashlib.sha256(normalized_criteria.encode()).hexdigest()

    def is_valid(self):
        """Check if cache entry is still valid"""
        return datetime.utcnow() < self.expires_at

    def increment_hit_count(self):
        """Increment hit count and update last accessed"""
        self.hit_count += 1
        self.last_accessed = datetime.utcnow()

    def to_dict(self):
        """Convert cache entry to dictionary"""
        return {
            "id": self.id,
            "cache_key": self.cache_key,
            "search_criteria": self.search_criteria,
            "result_count": self.result_count,
            "response_time_ms": self.response_time_ms,
            "hit_count": self.hit_count,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "is_valid": self.is_valid(),
        }

    def __repr__(self):
        return f"<SearchResultCache(key='{self.cache_key[:8]}...', hits={self.hit_count}, valid={self.is_valid()})>"


class SearchSuggestion(Base):
    """Search suggestions and autocomplete data"""

    __tablename__ = "search_suggestions"

    id = Column(Integer, primary_key=True)

    # Suggestion details
    suggestion_text = Column(String(500), nullable=False)
    suggestion_type = Column(
        String(50), nullable=False
    )  # 'artist', 'title', 'genre', 'keyword'
    category = Column(String(50), nullable=True)  # Additional categorization

    # Usage and ranking
    usage_count = Column(Integer, default=0)
    success_rate = Column(
        Float, default=0.0
    )  # Percentage of times this suggestion led to results
    relevance_score = Column(Float, default=1.0)  # Algorithm-determined relevance

    # Context information
    source_type = Column(
        String(50), nullable=True
    )  # Where suggestion came from: 'user_query', 'system_generated', 'metadata'
    language = Column(String(10), default="en")  # Language code

    # Additional data
    suggestion_metadata = Column(JSON, nullable=True)  # Additional suggestion data
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_search_suggestion_text", "suggestion_text"),
        Index("idx_search_suggestion_type", "suggestion_type"),
        Index("idx_search_suggestion_usage", "usage_count"),
        Index("idx_search_suggestion_relevance", "relevance_score"),
        Index("idx_search_suggestion_category", "category"),
        Index(
            "idx_search_suggestion_composite",
            "suggestion_type",
            "usage_count",
            "relevance_score",
        ),
        {"extend_existing": True},
    )

    def increment_usage(self, had_results=True):
        """Update usage statistics"""
        self.usage_count += 1
        if had_results:
            # Update success rate using exponential moving average
            alpha = 0.1  # Learning rate
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 1.0
        else:
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 0.0
        self.last_used = datetime.utcnow()

    def to_dict(self):
        """Convert suggestion to dictionary"""
        return {
            "id": self.id,
            "suggestion_text": self.suggestion_text,
            "suggestion_type": self.suggestion_type,
            "category": self.category,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "relevance_score": self.relevance_score,
            "source_type": self.source_type,
            "language": self.language,
            "suggestion_metadata": self.suggestion_metadata,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }

    def __repr__(self):
        return f"<SearchSuggestion(text='{self.suggestion_text}', type='{self.suggestion_type}', usage={self.usage_count})>"
