"""
Advanced Search Service - Phase 3 Week 30
Music-specific search with advanced filters, faceted search, and smart suggestions
Consumer-focused search for music video collections
"""

import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import and_, desc, func, or_, text
from sqlalchemy.orm import Session, joinedload

from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.database.search_models import (
    SearchAnalytics,
    SearchAnalyticsEvent,
    SearchPreset,
    SearchResultCache,
    SearchSuggestion,
)
from src.services.search_optimization_service import SearchOptimizationService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.advanced_search")


class SearchQueryBuilder:
    """Advanced query builder for complex search operations"""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.base_query = None
        self.filters = []
        self.joins = set()
        self.order_clauses = []
        self.relevance_factors = []

    def reset(self):
        """Reset the query builder state"""
        self.base_query = None
        self.filters = []
        self.joins = set()
        self.order_clauses = []
        self.relevance_factors = []
        return self

    def base_video_query(self):
        """Set up base query for videos with artist join"""
        self.base_query = self.db.query(Video).options(joinedload(Video.artist))
        self.joins.add("artist")
        return self

    def add_text_search(
        self, query: str, fields: List[str] = None
    ) -> "SearchQueryBuilder":
        """Add full-text search across specified fields"""
        if not query or not query.strip():
            return self

        if fields is None:
            fields = ["title", "description", "search_keywords"]

        # Parse search query for advanced operators
        parsed_query = self._parse_search_query(query)

        # Build text search conditions
        text_conditions = []
        relevance_score = 0

        for term_info in parsed_query["terms"]:
            term = term_info["term"]
            operator = term_info["operator"]  # 'AND', 'OR', 'NOT'
            is_phrase = term_info["is_phrase"]

            # Create conditions for each field
            field_conditions = []

            if is_phrase:
                # Exact phrase search
                for field in fields:
                    if field == "title":
                        condition = Video.title.contains(term)
                        field_conditions.append(condition)
                        relevance_score += 3  # Title matches are highly relevant
                    elif field == "description":
                        condition = Video.description.contains(term)
                        field_conditions.append(condition)
                        relevance_score += 1
                    elif field == "search_keywords":
                        condition = Video.search_keywords.contains(term)
                        field_conditions.append(condition)
                        relevance_score += 2
            else:
                # Word-based search (case insensitive)
                for field in fields:
                    if field == "title":
                        condition = Video.title.ilike(f"%{term}%")
                        field_conditions.append(condition)
                        relevance_score += 2
                    elif field == "description":
                        condition = Video.description.ilike(f"%{term}%")
                        field_conditions.append(condition)
                        relevance_score += 1
                    elif field == "search_keywords":
                        condition = Video.search_keywords.ilike(f"%{term}%")
                        field_conditions.append(condition)
                        relevance_score += 2

            # Combine field conditions with OR
            combined_condition = or_(*field_conditions) if field_conditions else None

            if combined_condition is not None:
                if operator == "NOT":
                    text_conditions.append(~combined_condition)
                    relevance_score -= 1
                elif operator == "OR":
                    # OR conditions are handled at the term level
                    text_conditions.append(combined_condition)
                else:  # AND (default)
                    text_conditions.append(combined_condition)

        # Add artist name search
        if parsed_query["terms"]:
            artist_conditions = []
            for term_info in parsed_query["terms"]:
                if term_info["operator"] != "NOT":
                    term = term_info["term"]
                    artist_conditions.append(Artist.name.ilike(f"%{term}%"))
                    relevance_score += 3  # Artist name matches are highly relevant

            if artist_conditions:
                text_conditions.extend(artist_conditions)

        # Combine all text conditions
        if text_conditions:
            # Handle OR groups from parsed query
            if parsed_query["has_or_operators"]:
                # More complex logic needed for mixed AND/OR
                final_condition = and_(*text_conditions)
            else:
                final_condition = and_(*text_conditions)

            self.filters.append(final_condition)
            self.relevance_factors.append(relevance_score)

        return self

    def add_status_filter(
        self, statuses: Union[str, List[str]]
    ) -> "SearchQueryBuilder":
        """Filter by video status"""
        if not statuses:
            return self

        if isinstance(statuses, str):
            statuses = [statuses]

        # Convert string statuses to enum values
        status_enums = []
        for status in statuses:
            try:
                status_enum = VideoStatus(status.upper())
                status_enums.append(status_enum)
            except ValueError:
                logger.warning(f"Invalid video status: {status}")

        if status_enums:
            self.filters.append(Video.status.in_(status_enums))

        return self

    def add_quality_filter(
        self, qualities: Union[str, List[str]]
    ) -> "SearchQueryBuilder":
        """Filter by video quality"""
        if not qualities:
            return self

        if isinstance(qualities, str):
            qualities = [qualities]

        self.filters.append(Video.quality.in_(qualities))
        return self

    def add_year_range_filter(
        self, min_year: int = None, max_year: int = None
    ) -> "SearchQueryBuilder":
        """Filter by year range"""
        if min_year is not None:
            self.filters.append(Video.year >= min_year)
        if max_year is not None:
            self.filters.append(Video.year <= max_year)
        return self

    def add_duration_range_filter(
        self, min_duration: int = None, max_duration: int = None
    ) -> "SearchQueryBuilder":
        """Filter by duration range (in seconds)"""
        if min_duration is not None:
            self.filters.append(Video.duration >= min_duration)
        if max_duration is not None:
            self.filters.append(Video.duration <= max_duration)
        return self

    def add_genre_filter(self, genres: Union[str, List[str]]) -> "SearchQueryBuilder":
        """Filter by genres (JSON array search)"""
        if not genres:
            return self

        if isinstance(genres, str):
            genres = [genres]

        # For JSON array search, check if any of the specified genres exist
        genre_conditions = []
        for genre in genres:
            # SQLite/PostgreSQL compatible JSON search
            genre_conditions.append(Video.genres.contains(f'"{genre}"'))

        if genre_conditions:
            self.filters.append(or_(*genre_conditions))

        return self

    def add_thumbnail_filter(self, has_thumbnail: bool = None) -> "SearchQueryBuilder":
        """Filter by thumbnail presence"""
        if has_thumbnail is not None:
            if has_thumbnail:
                self.filters.append(
                    or_(
                        Video.thumbnail_url.isnot(None),
                        Video.thumbnail_path.isnot(None),
                    )
                )
            else:
                self.filters.append(
                    and_(Video.thumbnail_url.is_(None), Video.thumbnail_path.is_(None))
                )
        return self

    def add_source_filter(self, sources: Union[str, List[str]]) -> "SearchQueryBuilder":
        """Filter by video source"""
        if not sources:
            return self

        if isinstance(sources, str):
            sources = [sources]

        self.filters.append(Video.source.in_(sources))
        return self

    def add_artist_filter(
        self, artist_criteria: Dict[str, Any]
    ) -> "SearchQueryBuilder":
        """Filter by artist-specific criteria"""
        if not artist_criteria:
            return self

        # Ensure artist join is included
        if "artist" not in self.joins:
            self.base_query = self.base_query.join(Artist)
            self.joins.add("artist")

        if "monitored" in artist_criteria:
            self.filters.append(Artist.monitored == artist_criteria["monitored"])

        if "source" in artist_criteria:
            sources = artist_criteria["source"]
            if isinstance(sources, str):
                sources = [sources]
            self.filters.append(Artist.source.in_(sources))

        if "name" in artist_criteria:
            self.filters.append(Artist.name.ilike(f"%{artist_criteria['name']}%"))

        return self

    def add_date_range_filter(
        self,
        created_after: datetime = None,
        created_before: datetime = None,
        discovered_after: datetime = None,
        discovered_before: datetime = None,
    ) -> "SearchQueryBuilder":
        """Filter by date ranges"""
        if created_after:
            self.filters.append(Video.created_at >= created_after)
        if created_before:
            self.filters.append(Video.created_at <= created_before)
        if discovered_after:
            self.filters.append(Video.discovered_date >= discovered_after)
        if discovered_before:
            self.filters.append(Video.discovered_date <= discovered_before)
        return self

    def add_sorting(
        self,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        include_relevance: bool = True,
    ) -> "SearchQueryBuilder":
        """Add sorting to the query"""
        # Map sort fields to model attributes
        sort_field_map = {
            "created_at": Video.created_at,
            "updated_at": Video.updated_at,
            "title": Video.title,
            "year": Video.year,
            "duration": Video.duration,
            "view_count": Video.view_count,
            "artist_name": Artist.name,
            "discovered_date": Video.discovered_date,
        }

        if sort_by in sort_field_map:
            field = sort_field_map[sort_by]
            if sort_order.lower() == "desc":
                self.order_clauses.append(desc(field))
            else:
                self.order_clauses.append(field)

        # Add relevance scoring if text search was used and relevance is requested
        if include_relevance and self.relevance_factors:
            total_relevance = sum(self.relevance_factors)
            # Add relevance as primary sort if it's significant
            if total_relevance > 0:
                # For now, we'll use a simple relevance based on text match count
                # In a full implementation, this would be a calculated field
                pass

        return self

    def build(self) -> Tuple[Any, int]:
        """Build and execute the final query"""
        if not self.base_query:
            self.base_video_query()

        # Apply all filters
        query = self.base_query
        if self.filters:
            query = query.filter(and_(*self.filters))

        # Get total count before applying pagination
        total_count = query.count()

        # Apply sorting
        if self.order_clauses:
            query = query.order_by(*self.order_clauses)
        else:
            # Default sorting
            query = query.order_by(desc(Video.created_at))

        return query, total_count

    def _parse_search_query(self, query: str) -> Dict[str, Any]:
        """Parse search query for advanced operators"""
        parsed = {
            "terms": [],
            "has_or_operators": False,
            "has_not_operators": False,
        }

        # Simple parsing for quoted phrases and basic operators
        # This is a basic implementation - could be enhanced with proper search query parsing

        # Find quoted phrases first
        phrase_pattern = r'"([^"]+)"'
        phrases = re.findall(phrase_pattern, query)
        remaining_query = re.sub(phrase_pattern, "", query)

        # Add phrases as exact terms
        for phrase in phrases:
            parsed["terms"].append(
                {"term": phrase, "operator": "AND", "is_phrase": True}
            )

        # Split remaining query into words
        words = remaining_query.split()
        current_operator = "AND"

        for word in words:
            word = word.strip()
            if not word:
                continue

            if word.upper() == "AND":
                current_operator = "AND"
                continue
            elif word.upper() == "OR":
                current_operator = "OR"
                parsed["has_or_operators"] = True
                continue
            elif word.upper() == "NOT":
                current_operator = "NOT"
                parsed["has_not_operators"] = True
                continue

            # Regular word
            parsed["terms"].append(
                {"term": word, "operator": current_operator, "is_phrase": False}
            )

            # Reset to AND for next term
            current_operator = "AND"

        return parsed


class AdvancedSearchService:
    """Advanced search service with full-text search, presets, and analytics"""

    def __init__(self):
        self.cache_service = SearchOptimizationService()
        self.default_cache_ttl = 300  # 5 minutes

    def search_videos(
        self,
        search_criteria: Dict[str, Any],
        page: int = 1,
        per_page: int = 50,
        user_id: int = None,
        session_id: str = None,
    ) -> Dict[str, Any]:
        """
        Perform advanced video search with comprehensive filtering

        Args:
            search_criteria: Dictionary containing search parameters
            page: Page number for pagination
            per_page: Number of results per page
            user_id: User ID for analytics tracking
            session_id: Session ID for analytics tracking

        Returns:
            Dictionary containing search results and metadata
        """
        start_time = time.time()

        # Check cache first
        cache_key = self._generate_cache_key(search_criteria, page, per_page)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            self._track_search_event(
                user_id=user_id,
                session_id=session_id,
                event_type=SearchAnalyticsEvent.SEARCH_EXECUTED,
                search_criteria=search_criteria,
                response_time_ms=int((time.time() - start_time) * 1000),
                result_count=cached_result["total_results"],
                event_metadata={"cache_hit": True},
            )
            return cached_result

        try:
            with get_db() as db:
                # Build the search query
                query_builder = SearchQueryBuilder(db)
                query_builder.base_video_query()

                # Apply search criteria
                self._apply_search_criteria(query_builder, search_criteria)

                # Build and execute query
                query, total_count = query_builder.build()

                # Apply pagination
                offset = (page - 1) * per_page
                results = query.offset(offset).limit(per_page).all()

                # Convert results to dictionaries
                video_results = []
                for video in results:
                    video_dict = {
                        "id": video.id,
                        "title": video.title,
                        "artist_id": video.artist_id,
                        "artist_name": video.artist.name if video.artist else None,
                        "status": video.status.value,
                        "quality": video.quality,
                        "source": video.source,
                        "year": video.year,
                        "duration": video.duration,
                        "genres": video.genres,
                        "thumbnail_url": video.thumbnail_url,
                        "thumbnail_path": video.thumbnail_path,
                        "youtube_url": video.youtube_url,
                        "view_count": video.view_count,
                        "created_at": (
                            video.created_at.isoformat() if video.created_at else None
                        ),
                        "discovered_date": (
                            video.discovered_date.isoformat()
                            if video.discovered_date
                            else None
                        ),
                    }
                    video_results.append(video_dict)

                # Calculate pagination metadata
                total_pages = (total_count + per_page - 1) // per_page
                has_next = page < total_pages
                has_prev = page > 1

                response_time_ms = int((time.time() - start_time) * 1000)

                result = {
                    "videos": video_results,
                    "total_results": total_count,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": total_pages,
                    "has_next_page": has_next,
                    "has_previous_page": has_prev,
                    "response_time_ms": response_time_ms,
                    "search_criteria": search_criteria,
                    "cache_key": cache_key,
                }

                # Cache the result
                self._cache_result(cache_key, result, search_criteria)

                # Track analytics
                self._track_search_event(
                    user_id=user_id,
                    session_id=session_id,
                    event_type=SearchAnalyticsEvent.SEARCH_EXECUTED,
                    search_criteria=search_criteria,
                    response_time_ms=response_time_ms,
                    result_count=total_count,
                    event_metadata={"cache_hit": False},
                )

                return result

        except Exception as e:
            logger.error(f"Error in advanced search: {str(e)}")
            # Track error in analytics
            self._track_search_event(
                user_id=user_id,
                session_id=session_id,
                event_type=SearchAnalyticsEvent.SEARCH_EXECUTED,
                search_criteria=search_criteria,
                response_time_ms=int((time.time() - start_time) * 1000),
                result_count=0,
                event_metadata={"error": str(e)},
            )
            raise

    def _apply_search_criteria(
        self, query_builder: SearchQueryBuilder, criteria: Dict[str, Any]
    ):
        """Apply search criteria to the query builder"""

        # Text search
        if "text_query" in criteria and criteria["text_query"]:
            query_builder.add_text_search(
                criteria["text_query"],
                fields=criteria.get(
                    "search_fields", ["title", "description", "search_keywords"]
                ),
            )

        # Status filter
        if "status" in criteria:
            query_builder.add_status_filter(criteria["status"])

        # Quality filter
        if "quality" in criteria:
            query_builder.add_quality_filter(criteria["quality"])

        # Year range
        if "year_range" in criteria:
            year_range = criteria["year_range"]
            query_builder.add_year_range_filter(
                min_year=year_range.get("min"), max_year=year_range.get("max")
            )

        # Duration range
        if "duration_range" in criteria:
            duration_range = criteria["duration_range"]
            query_builder.add_duration_range_filter(
                min_duration=duration_range.get("min"),
                max_duration=duration_range.get("max"),
            )

        # Genre filter
        if "genres" in criteria:
            query_builder.add_genre_filter(criteria["genres"])

        # Thumbnail filter
        if "has_thumbnail" in criteria:
            query_builder.add_thumbnail_filter(criteria["has_thumbnail"])

        # Source filter
        if "source" in criteria:
            query_builder.add_source_filter(criteria["source"])

        # Artist filters
        if "artist_filters" in criteria:
            query_builder.add_artist_filter(criteria["artist_filters"])

        # Date range filters
        date_filters = {}
        if "created_after" in criteria:
            date_filters["created_after"] = datetime.fromisoformat(
                criteria["created_after"]
            )
        if "created_before" in criteria:
            date_filters["created_before"] = datetime.fromisoformat(
                criteria["created_before"]
            )
        if "discovered_after" in criteria:
            date_filters["discovered_after"] = datetime.fromisoformat(
                criteria["discovered_after"]
            )
        if "discovered_before" in criteria:
            date_filters["discovered_before"] = datetime.fromisoformat(
                criteria["discovered_before"]
            )

        if date_filters:
            query_builder.add_date_range_filter(**date_filters)

        # Sorting
        sort_by = criteria.get("sort_by", "created_at")
        sort_order = criteria.get("sort_order", "desc")
        include_relevance = criteria.get("include_relevance", True)
        query_builder.add_sorting(sort_by, sort_order, include_relevance)

    def _generate_cache_key(
        self, search_criteria: Dict[str, Any], page: int, per_page: int
    ) -> str:
        """Generate cache key for search results"""
        import json

        cache_data = {"criteria": search_criteria, "page": page, "per_page": per_page}
        return SearchResultCache.generate_cache_key(cache_data)

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached search result if available and valid"""
        try:
            with get_db() as db:
                cache_entry = (
                    db.query(SearchResultCache)
                    .filter(SearchResultCache.cache_key == cache_key)
                    .first()
                )

                if cache_entry and cache_entry.is_valid():
                    cache_entry.increment_hit_count()
                    db.commit()
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return cache_entry.result_data
                elif cache_entry:
                    # Remove expired cache entry
                    db.delete(cache_entry)
                    db.commit()
                    logger.debug(f"Removed expired cache entry: {cache_key}")
        except Exception as e:
            logger.error(f"Error getting cached result: {str(e)}")

        return None

    def _cache_result(
        self, cache_key: str, result: Dict[str, Any], search_criteria: Dict[str, Any]
    ):
        """Cache search result"""
        try:
            with get_db() as db:
                # Remove existing cache entry if it exists
                existing = (
                    db.query(SearchResultCache)
                    .filter(SearchResultCache.cache_key == cache_key)
                    .first()
                )
                if existing:
                    db.delete(existing)

                # Create new cache entry
                expires_at = datetime.utcnow() + timedelta(
                    seconds=self.default_cache_ttl
                )

                cache_entry = SearchResultCache(
                    cache_key=cache_key,
                    search_criteria=search_criteria,
                    result_data=result,
                    result_count=result["total_results"],
                    response_time_ms=result["response_time_ms"],
                    expires_at=expires_at,
                )

                db.add(cache_entry)
                db.commit()
                logger.debug(f"Cached result for key: {cache_key}")

        except Exception as e:
            logger.error(f"Error caching result: {str(e)}")

    def _track_search_event(
        self,
        user_id: int = None,
        session_id: str = None,
        event_type: SearchAnalyticsEvent = SearchAnalyticsEvent.SEARCH_EXECUTED,
        search_criteria: Dict[str, Any] = None,
        response_time_ms: int = None,
        result_count: int = None,
        event_metadata: Dict[str, Any] = None,
        preset_id: int = None,
    ):
        """Track search analytics event"""
        try:
            with get_db() as db:
                analytics_event = SearchAnalytics(
                    user_id=user_id,
                    session_id=session_id,
                    event_type=event_type,
                    search_query=(
                        search_criteria.get("text_query") if search_criteria else None
                    ),
                    search_criteria=search_criteria,
                    preset_id=preset_id,
                    response_time_ms=response_time_ms,
                    result_count=result_count,
                    event_metadata=event_metadata,
                )

                db.add(analytics_event)
                db.commit()

        except Exception as e:
            logger.error(f"Error tracking search analytics: {str(e)}")

    def get_search_suggestions(
        self, query: str, field: str = "title", limit: int = 10
    ) -> List[str]:
        """Get search suggestions for autocomplete"""
        try:
            with get_db() as db:
                if field == "title":
                    results = (
                        db.query(Video.title)
                        .filter(Video.title.ilike(f"%{query}%"))
                        .distinct()
                        .limit(limit)
                        .all()
                    )
                    return [result[0] for result in results if result[0]]
                
                elif field == "artist":
                    results = (
                        db.query(Artist.name)
                        .filter(Artist.name.ilike(f"%{query}%"))
                        .distinct()
                        .limit(limit)
                        .all()
                    )
                    return [result[0] for result in results if result[0]]
                
                elif field == "genre":
                    results = (
                        db.query(Video.genre)
                        .filter(Video.genre.ilike(f"%{query}%"))
                        .filter(Video.genre.isnot(None))
                        .distinct()
                        .limit(limit)
                        .all()
                    )
                    return [result[0] for result in results if result[0]]
                
                elif field == "description":
                    results = (
                        db.query(Video.description)
                        .filter(Video.description.ilike(f"%{query}%"))
                        .filter(Video.description.isnot(None))
                        .distinct()
                        .limit(limit)
                        .all()
                    )
                    return [result[0][:100] + "..." if len(result[0]) > 100 else result[0] 
                           for result in results if result[0]]
                
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting search suggestions: {str(e)}")
            return []


# Initialize service instance
advanced_search_service = AdvancedSearchService()
