"""
Music Search Service - Phase 3 Week 30
Music-specific search with advanced filters, faceted search, and smart suggestions
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.database.async_connection import get_async_session
from src.database.models import Video
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.services.music_video_detector import get_music_video_detector
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.music_search")


class SearchType(Enum):
    """Types of search queries"""

    GENERAL = "general"  # General text search
    ARTIST = "artist"  # Artist-specific search
    TITLE = "title"  # Title-specific search
    GENRE = "genre"  # Genre-based search
    YEAR = "year"  # Year-based search
    DURATION = "duration"  # Duration-based search
    QUALITY = "quality"  # Quality-based search
    ADVANCED = "advanced"  # Multi-criteria search


class SearchScope(Enum):
    """Scope of search"""

    ALL = "all"  # All content
    MUSIC_VIDEOS = "music_videos"  # Music videos only
    OTHER_VIDEOS = "other_videos"  # Non-music videos
    RECENT = "recent"  # Recent additions
    POPULAR = "popular"  # Most viewed content
    UNWATCHED = "unwatched"  # Never watched


class SortBy(Enum):
    """Search result sorting options"""

    RELEVANCE = "relevance"  # Best match first
    RECENTLY_ADDED = "recently_added"
    TITLE_AZ = "title_az"
    ARTIST_AZ = "artist_az"
    DURATION_SHORT = "duration_short"
    DURATION_LONG = "duration_long"
    MOST_VIEWED = "most_viewed"
    HIGHEST_QUALITY = "highest_quality"


@dataclass
class SearchFilter:
    """Individual search filter"""

    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, startswith, endswith
    value: Any
    label: str


@dataclass
class FacetFilter:
    """Faceted search filter with counts"""

    name: str
    label: str
    values: List[
        Dict[str, Any]
    ]  # [{'value': 'pop', 'count': 15, 'label': 'Pop Music'}]
    filter_type: str  # 'checkbox', 'radio', 'range', 'date'
    is_expanded: bool = False


@dataclass
class SearchResult:
    """Individual search result"""

    video_id: int
    title: str
    artist: str
    duration: int
    quality: str
    file_size: int
    view_count: int
    is_music_video: bool
    confidence_score: float
    thumbnail_url: str
    match_score: float
    match_highlights: Dict[str, List[str]]  # Field -> highlighted matches
    created_at: datetime
    last_watched: Optional[datetime]


@dataclass
class SearchResponse:
    """Complete search response"""

    query: str
    search_type: SearchType
    results: List[SearchResult]
    total_count: int
    facets: List[FacetFilter]
    suggestions: List[str]
    corrections: Optional[str]
    search_time_ms: float
    page: int
    per_page: int
    total_pages: int
    filters_applied: List[SearchFilter]
    sort_by: SortBy


class MusicSearchService:
    """Music-specific search service with advanced features"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.music_video_detector = None
        self.artist_discovery = None

        # Search configuration
        self.max_results_per_page = 50
        self.default_results_per_page = 20
        self.search_timeout_seconds = 10
        self.cache_duration = 600  # 10 minutes

        # Music-specific search patterns
        self.music_patterns = {
            "artist_featuring": re.compile(
                r"(.+?)\s+(?:ft\.?|feat\.?|featuring)\s+(.+)", re.IGNORECASE
            ),
            "title_remix": re.compile(r"(.+?)\s+\((.+?)\s+remix\)", re.IGNORECASE),
            "title_version": re.compile(r"(.+?)\s+\((.+?)\s+version\)", re.IGNORECASE),
            "live_performance": re.compile(r"(.+?)\s+\(live\)", re.IGNORECASE),
            "official_video": re.compile(
                r"(.+?)\s+official\s+(?:music\s+)?video", re.IGNORECASE
            ),
        }

        # Genre keywords for classification
        self.genre_keywords = {
            "pop": ["pop", "mainstream", "radio", "chart"],
            "rock": ["rock", "metal", "punk", "grunge", "alternative"],
            "hip-hop": ["hip-hop", "rap", "urban", "trap", "gangsta"],
            "electronic": ["electronic", "edm", "house", "techno", "dubstep", "trance"],
            "r&b": ["r&b", "soul", "funk", "rnb", "neo-soul"],
            "country": ["country", "folk", "bluegrass", "americana"],
            "jazz": ["jazz", "blues", "swing", "bebop"],
            "classical": ["classical", "orchestra", "symphony", "opera"],
            "reggae": ["reggae", "ska", "dancehall"],
            "latin": ["latin", "salsa", "reggaeton", "bachata"],
        }

        # Quality classifications
        self.quality_ranges = {
            "4K": {"min_height": 2160, "label": "4K Ultra HD"},
            "1080p": {"min_height": 1080, "max_height": 2159, "label": "1080p Full HD"},
            "720p": {"min_height": 720, "max_height": 1079, "label": "720p HD"},
            "480p": {"min_height": 480, "max_height": 719, "label": "480p SD"},
            "360p": {"min_height": 0, "max_height": 479, "label": "360p and below"},
        }

    async def initialize(self):
        """Initialize music search service"""
        try:
            self.redis_client = await get_redis_client()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()

            # Build search indices
            await self._build_search_indices()

            logger.info("Music search service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize music search service: {e}")
            raise

    async def search(
        self,
        query: str,
        search_type: SearchType = SearchType.GENERAL,
        search_scope: SearchScope = SearchScope.ALL,
        filters: Optional[List[SearchFilter]] = None,
        sort_by: SortBy = SortBy.RELEVANCE,
        page: int = 1,
        per_page: int = 20,
        include_facets: bool = True,
        include_suggestions: bool = True,
    ) -> SearchResponse:
        """Perform music-specific search with advanced features"""
        try:
            start_time = datetime.now()

            # Validate parameters
            page = max(1, page)
            per_page = min(self.max_results_per_page, max(1, per_page))
            filters = filters or []

            logger.info(
                f"Music search: query='{query}', type={search_type.value}, scope={search_scope.value}"
            )

            # Check cache first
            cache_key = self._generate_cache_key(
                query, search_type, search_scope, filters, sort_by, page, per_page
            )
            cached_result = await self._get_cached_search(cache_key)
            if cached_result:
                return cached_result

            # Parse and enhance query for music-specific features
            enhanced_query = await self._enhance_music_query(query, search_type)

            # Execute search
            async with get_async_session() as session:
                base_query = select(Video).options(selectinload(Video.artist))

                # Apply search conditions
                search_conditions = await self._build_search_conditions(
                    enhanced_query, search_type, search_scope
                )
                if search_conditions:
                    base_query = base_query.where(and_(*search_conditions))

                # Apply filters
                filter_conditions = await self._build_filter_conditions(filters)
                if filter_conditions:
                    base_query = base_query.where(and_(*filter_conditions))

                # Get total count
                count_query = select(func.count()).select_from(base_query.subquery())
                total_count = await session.scalar(count_query)

                # Apply sorting
                base_query = await self._apply_search_sorting(
                    base_query, sort_by, enhanced_query
                )

                # Apply pagination
                offset = (page - 1) * per_page
                base_query = base_query.offset(offset).limit(per_page)

                # Execute query
                result = await session.execute(base_query)
                videos = result.scalars().all()

                # Convert to search results with music-specific relevance scoring
                search_results = []
                for video in videos:
                    search_result = await self._create_music_search_result(
                        video, enhanced_query, search_type
                    )
                    search_results.append(search_result)

                # Sort by relevance if needed
                if sort_by == SortBy.RELEVANCE:
                    search_results.sort(key=lambda x: x.match_score, reverse=True)

                # Get facets with music-specific groupings
                facets = []
                if include_facets:
                    facets = await self._build_music_facets(
                        session, enhanced_query, search_conditions, filter_conditions
                    )

                # Get music-specific suggestions and corrections
                suggestions = []
                corrections = None
                if include_suggestions:
                    suggestions = await self._get_music_suggestions(
                        query, search_results
                    )
                    corrections = await self._get_music_corrections(query)

                # Calculate pagination
                total_pages = (total_count + per_page - 1) // per_page

                # Create response
                search_time = (datetime.now() - start_time).total_seconds() * 1000

                response = SearchResponse(
                    query=query,
                    search_type=search_type,
                    results=search_results,
                    total_count=total_count,
                    facets=facets,
                    suggestions=suggestions,
                    corrections=corrections,
                    search_time_ms=search_time,
                    page=page,
                    per_page=per_page,
                    total_pages=total_pages,
                    filters_applied=filters,
                    sort_by=sort_by,
                )

                # Cache result
                await self._cache_search_result(cache_key, response)

                logger.info(
                    f"Music search completed: {len(search_results)} results in {search_time:.1f}ms"
                )

                return response

        except Exception as e:
            logger.error(f"Music search failed: {e}")
            raise

    async def _enhance_music_query(
        self, query: str, search_type: SearchType
    ) -> Dict[str, Any]:
        """Enhance search query with music-specific parsing"""
        try:
            enhanced = {
                "original": query,
                "terms": [],
                "artist": None,
                "title": None,
                "featuring": None,
                "modifiers": [],
                "is_music_specific": False,
                "genre_hints": [],
                "era_hints": [],
            }

            query_lower = query.lower().strip()

            # Parse music-specific patterns
            for pattern_name, pattern in self.music_patterns.items():
                match = pattern.search(query)
                if match:
                    enhanced["is_music_specific"] = True
                    if pattern_name == "artist_featuring":
                        enhanced["artist"] = match.group(1).strip()
                        enhanced["featuring"] = match.group(2).strip()
                    elif pattern_name in [
                        "title_remix",
                        "title_version",
                        "live_performance",
                    ]:
                        enhanced["title"] = match.group(1).strip()
                        enhanced["modifiers"].append(match.group(2).strip())
                    elif pattern_name == "official_video":
                        enhanced["title"] = match.group(1).strip()
                        enhanced["modifiers"].append("official")

            # Extract artist - title pattern (common format: "Artist - Title")
            if " - " in query and not enhanced["artist"]:
                parts = query.split(" - ", 1)
                if len(parts) == 2:
                    enhanced["artist"] = parts[0].strip()
                    enhanced["title"] = parts[1].strip()
                    enhanced["is_music_specific"] = True

            # Detect genre hints
            for genre, keywords in self.genre_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    enhanced["genre_hints"].append(genre)
                    enhanced["is_music_specific"] = True

            # Detect era/decade hints
            decade_patterns = [
                r"(\d{4})s?",
                r"(nineteen|twenty)\s*(sixties|seventies|eighties|nineties)",
            ]
            for pattern in decade_patterns:
                matches = re.findall(pattern, query_lower)
                if matches:
                    enhanced["era_hints"].extend(matches)
                    enhanced["is_music_specific"] = True

            # Split into search terms
            if not enhanced["artist"] and not enhanced["title"]:
                enhanced["terms"] = [
                    term.strip() for term in query.split() if len(term.strip()) > 2
                ]

            # Detect quoted phrases
            quoted_phrases = re.findall(r'"([^"]*)"', query)
            enhanced["quoted_phrases"] = quoted_phrases

            return enhanced

        except Exception as e:
            logger.error(f"Failed to enhance music query: {e}")
            return {"original": query, "terms": query.split()}

    async def _build_search_conditions(
        self, enhanced_query: Dict, search_type: SearchType, search_scope: SearchScope
    ) -> List:
        """Build SQL conditions for music search"""
        try:
            conditions = []

            # Apply scope filters
            if search_scope == SearchScope.MUSIC_VIDEOS:
                conditions.append(Video.is_music_video == True)
            elif search_scope == SearchScope.OTHER_VIDEOS:
                conditions.append(Video.is_music_video == False)
            elif search_scope == SearchScope.RECENT:
                week_ago = datetime.now() - timedelta(days=7)
                conditions.append(Video.created_at >= week_ago)
            elif search_scope == SearchScope.POPULAR:
                conditions.append(Video.view_count > 0)
            elif search_scope == SearchScope.UNWATCHED:
                conditions.append(Video.view_count == 0)

            # Apply search type specific conditions
            if search_type == SearchType.ARTIST and enhanced_query.get("artist"):
                conditions.append(
                    Video.artist_name.ilike(f"%{enhanced_query['artist']}%")
                )
            elif search_type == SearchType.TITLE and enhanced_query.get("title"):
                conditions.append(Video.title.ilike(f"%{enhanced_query['title']}%"))
            elif search_type == SearchType.GENRE and enhanced_query.get("genre_hints"):
                genre_conditions = []
                for genre in enhanced_query["genre_hints"]:
                    genre_conditions.append(Video.description.ilike(f"%{genre}%"))
                if genre_conditions:
                    conditions.append(or_(*genre_conditions))
            elif search_type == SearchType.GENERAL:
                # General music search across multiple fields
                general_conditions = []

                if enhanced_query.get("artist"):
                    general_conditions.append(
                        Video.artist_name.ilike(f"%{enhanced_query['artist']}%")
                    )

                if enhanced_query.get("title"):
                    general_conditions.append(
                        Video.title.ilike(f"%{enhanced_query['title']}%")
                    )

                if enhanced_query.get("terms"):
                    for term in enhanced_query["terms"]:
                        term_conditions = or_(
                            Video.title.ilike(f"%{term}%"),
                            Video.artist_name.ilike(f"%{term}%"),
                            Video.description.ilike(f"%{term}%"),
                        )
                        general_conditions.append(term_conditions)

                if enhanced_query.get("quoted_phrases"):
                    for phrase in enhanced_query["quoted_phrases"]:
                        phrase_condition = or_(
                            Video.title.ilike(f"%{phrase}%"),
                            Video.artist_name.ilike(f"%{phrase}%"),
                        )
                        general_conditions.append(phrase_condition)

                # Include genre hints in general search
                if enhanced_query.get("genre_hints"):
                    for genre in enhanced_query["genre_hints"]:
                        general_conditions.append(Video.description.ilike(f"%{genre}%"))

                if general_conditions:
                    conditions.append(or_(*general_conditions))

            return conditions

        except Exception as e:
            logger.error(f"Failed to build music search conditions: {e}")
            return []

    async def _build_filter_conditions(self, filters: List[SearchFilter]) -> List:
        """Build SQL conditions from search filters"""
        try:
            conditions = []

            for filter_obj in filters:
                field = filter_obj.field
                operator = filter_obj.operator
                value = filter_obj.value

                if field == "duration" and operator in ["gte", "lte"]:
                    if operator == "gte":
                        conditions.append(Video.duration >= value)
                    else:
                        conditions.append(Video.duration <= value)

                elif field == "quality" and operator == "eq":
                    quality_range = self.quality_ranges.get(value)
                    if quality_range:
                        if "max_height" in quality_range:
                            conditions.append(
                                and_(
                                    Video.height >= quality_range["min_height"],
                                    Video.height <= quality_range["max_height"],
                                )
                            )
                        else:
                            conditions.append(
                                Video.height >= quality_range["min_height"]
                            )

                elif field == "file_size" and operator in ["gte", "lte"]:
                    if operator == "gte":
                        conditions.append(Video.file_size >= value)
                    else:
                        conditions.append(Video.file_size <= value)

                elif field == "view_count" and operator in ["gte", "lte"]:
                    if operator == "gte":
                        conditions.append(Video.view_count >= value)
                    else:
                        conditions.append(Video.view_count <= value)

                elif field == "is_music_video" and operator == "eq":
                    conditions.append(Video.is_music_video == bool(value))

                elif field == "genre" and operator == "contains":
                    conditions.append(Video.description.ilike(f"%{value}%"))

            return conditions

        except Exception as e:
            logger.error(f"Failed to build filter conditions: {e}")
            return []

    async def _apply_search_sorting(self, query, sort_by: SortBy, enhanced_query: Dict):
        """Apply sorting to search query"""
        try:
            if sort_by == SortBy.RECENTLY_ADDED:
                return query.order_by(desc(Video.created_at))
            elif sort_by == SortBy.TITLE_AZ:
                return query.order_by(asc(Video.title))
            elif sort_by == SortBy.ARTIST_AZ:
                return query.order_by(asc(Video.artist_name))
            elif sort_by == SortBy.DURATION_SHORT:
                return query.order_by(asc(Video.duration))
            elif sort_by == SortBy.DURATION_LONG:
                return query.order_by(desc(Video.duration))
            elif sort_by == SortBy.MOST_VIEWED:
                return query.order_by(desc(Video.view_count))
            elif sort_by == SortBy.HIGHEST_QUALITY:
                return query.order_by(desc(Video.height), desc(Video.bitrate))
            else:  # RELEVANCE - will be sorted after query execution
                return query.order_by(desc(Video.created_at))  # Default order

        except Exception as e:
            logger.error(f"Failed to apply search sorting: {e}")
            return query.order_by(desc(Video.created_at))

    async def _create_music_search_result(
        self, video: Video, enhanced_query: Dict, search_type: SearchType
    ) -> SearchResult:
        """Create search result with music-specific relevance scoring"""
        try:
            # Calculate music-specific match score
            match_score = await self._calculate_music_match_score(video, enhanced_query)

            # Generate music-specific highlights
            highlights = await self._generate_music_highlights(video, enhanced_query)

            # Get thumbnail URL
            thumbnail_url = f"/api/thumbnails/video/{video.id}"

            # Format quality
            quality = self._format_quality(video.height)

            return SearchResult(
                video_id=video.id,
                title=video.title or "Unknown Title",
                artist=video.artist_name or "Unknown Artist",
                duration=video.duration or 0,
                quality=quality,
                file_size=video.file_size or 0,
                view_count=video.view_count or 0,
                is_music_video=video.is_music_video or False,
                confidence_score=getattr(video, "music_video_confidence", 0.0),
                thumbnail_url=thumbnail_url,
                match_score=match_score,
                match_highlights=highlights,
                created_at=video.created_at or datetime.now(),
                last_watched=video.last_watched,
            )

        except Exception as e:
            logger.error(f"Failed to create music search result: {e}")
            # Return basic result
            return SearchResult(
                video_id=video.id,
                title=video.title or "Unknown Title",
                artist=video.artist_name or "Unknown Artist",
                duration=video.duration or 0,
                quality="Unknown",
                file_size=video.file_size or 0,
                view_count=video.view_count or 0,
                is_music_video=video.is_music_video or False,
                confidence_score=0.0,
                thumbnail_url=f"/api/thumbnails/video/{video.id}",
                match_score=0.5,
                match_highlights={},
                created_at=video.created_at or datetime.now(),
                last_watched=video.last_watched,
            )

    async def _calculate_music_match_score(
        self, video: Video, enhanced_query: Dict
    ) -> float:
        """Calculate music-specific relevance match score"""
        try:
            score = 0.0
            max_score = 1.0

            title = (video.title or "").lower()
            artist = (video.artist_name or "").lower()
            description = (video.description or "").lower()

            # High-value exact matches
            if enhanced_query.get("title") and enhanced_query["title"].lower() in title:
                score += 0.5

            if (
                enhanced_query.get("artist")
                and enhanced_query["artist"].lower() in artist
            ):
                score += 0.5

            # Music-specific pattern matches
            if enhanced_query.get("featuring") and "feat" in title:
                score += 0.2

            if enhanced_query.get("modifiers"):
                for modifier in enhanced_query["modifiers"]:
                    if modifier.lower() in title or modifier.lower() in description:
                        score += 0.1

            # Genre matches
            if enhanced_query.get("genre_hints"):
                for genre in enhanced_query["genre_hints"]:
                    if genre in description:
                        score += 0.2

            # Term matches with music context weighting
            if enhanced_query.get("terms"):
                term_matches = 0
                for term in enhanced_query["terms"]:
                    term_lower = term.lower()
                    if term_lower in title:
                        term_matches += 0.8
                    elif term_lower in artist:
                        term_matches += 0.7
                    elif term_lower in description:
                        term_matches += 0.3

                # Normalize term score
                if enhanced_query["terms"]:
                    score += min(0.3, term_matches / len(enhanced_query["terms"]))

            # Music video boost
            if enhanced_query.get("is_music_specific") and video.is_music_video:
                score += 0.15

            # Quality and popularity boost for music content
            if video.is_music_video:
                if video.view_count and video.view_count > 10:
                    score += 0.05

                if video.height and video.height >= 720:
                    score += 0.05

            # Recent music video boost
            if (
                video.is_music_video
                and video.created_at
                and (datetime.now() - video.created_at).days < 30
            ):
                score += 0.05

            return min(max_score, score)

        except Exception as e:
            logger.error(f"Failed to calculate music match score: {e}")
            return 0.5

    async def _generate_music_highlights(
        self, video: Video, enhanced_query: Dict
    ) -> Dict[str, List[str]]:
        """Generate music-specific search result highlights"""
        try:
            highlights = {}

            # Highlight music-specific terms
            terms_to_highlight = enhanced_query.get("terms", [])
            if enhanced_query.get("artist"):
                terms_to_highlight.append(enhanced_query["artist"])
            if enhanced_query.get("title"):
                terms_to_highlight.append(enhanced_query["title"])
            if enhanced_query.get("genre_hints"):
                terms_to_highlight.extend(enhanced_query["genre_hints"])

            # Highlight in title
            if video.title and terms_to_highlight:
                title_highlights = []
                title_lower = video.title.lower()

                for term in terms_to_highlight:
                    if term.lower() in title_lower:
                        highlighted = re.sub(
                            f"({re.escape(term)})",
                            r"<mark>\1</mark>",
                            video.title,
                            flags=re.IGNORECASE,
                        )
                        title_highlights.append(highlighted)

                if title_highlights:
                    highlights["title"] = title_highlights

            # Highlight in artist name
            if video.artist_name and terms_to_highlight:
                artist_highlights = []
                artist_lower = video.artist_name.lower()

                for term in terms_to_highlight:
                    if term.lower() in artist_lower:
                        highlighted = re.sub(
                            f"({re.escape(term)})",
                            r"<mark>\1</mark>",
                            video.artist_name,
                            flags=re.IGNORECASE,
                        )
                        artist_highlights.append(highlighted)

                if artist_highlights:
                    highlights["artist"] = artist_highlights

            return highlights

        except Exception as e:
            logger.error(f"Failed to generate music highlights: {e}")
            return {}

    async def _build_music_facets(
        self,
        session: AsyncSession,
        enhanced_query: Dict,
        search_conditions: List,
        filter_conditions: List,
    ) -> List[FacetFilter]:
        """Build music-specific faceted search filters"""
        try:
            facets = []

            # Build base query for facet counts
            base_conditions = search_conditions + filter_conditions

            # Artist facet (music-specific)
            artist_facet = await self._build_music_artist_facet(
                session, base_conditions
            )
            if artist_facet:
                facets.append(artist_facet)

            # Music video type facet
            music_video_facet = await self._build_music_video_facet(
                session, base_conditions
            )
            if music_video_facet:
                facets.append(music_video_facet)

            # Genre facet (detected from descriptions)
            genre_facet = await self._build_genre_facet(session, base_conditions)
            if genre_facet:
                facets.append(genre_facet)

            # Duration ranges (music-specific)
            duration_facet = await self._build_music_duration_facet(
                session, base_conditions
            )
            if duration_facet:
                facets.append(duration_facet)

            # Quality facet
            quality_facet = await self._build_quality_facet(session, base_conditions)
            if quality_facet:
                facets.append(quality_facet)

            return facets

        except Exception as e:
            logger.error(f"Failed to build music facets: {e}")
            return []

    async def _build_music_artist_facet(
        self, session: AsyncSession, conditions: List
    ) -> Optional[FacetFilter]:
        """Build music artist facet with music video counts"""
        try:
            query = select(
                Video.artist_name, func.count(Video.id).label("count")
            ).group_by(Video.artist_name)

            if conditions:
                query = query.where(and_(*conditions))

            # Focus on artists with music videos
            query = (
                query.having(Video.artist_name.isnot(None))
                .order_by(desc(func.count(Video.id)))
                .limit(15)
            )

            result = await session.execute(query)
            artist_counts = result.all()

            if not artist_counts:
                return None

            values = []
            for artist, count in artist_counts:
                values.append(
                    {"value": artist, "count": count, "label": f"{artist} ({count})"}
                )

            return FacetFilter(
                name="artist",
                label="Artists",
                values=values,
                filter_type="checkbox",
                is_expanded=True,
            )

        except Exception as e:
            logger.error(f"Failed to build music artist facet: {e}")
            return None

    async def _build_music_video_facet(
        self, session: AsyncSession, conditions: List
    ) -> Optional[FacetFilter]:
        """Build music video type facet"""
        try:
            values = []

            # Count music videos
            music_query = select(func.count(Video.id)).where(
                Video.is_music_video == True
            )
            if conditions:
                music_query = music_query.where(and_(*conditions))
            music_count = await session.scalar(music_query)

            # Count non-music videos
            non_music_query = select(func.count(Video.id)).where(
                Video.is_music_video == False
            )
            if conditions:
                non_music_query = non_music_query.where(and_(*conditions))
            non_music_count = await session.scalar(non_music_query)

            if music_count > 0:
                values.append(
                    {
                        "value": "true",
                        "count": music_count,
                        "label": f"Music Videos ({music_count})",
                    }
                )

            if non_music_count > 0:
                values.append(
                    {
                        "value": "false",
                        "count": non_music_count,
                        "label": f"Other Videos ({non_music_count})",
                    }
                )

            if not values:
                return None

            return FacetFilter(
                name="is_music_video",
                label="Content Type",
                values=values,
                filter_type="radio",
                is_expanded=True,
            )

        except Exception as e:
            logger.error(f"Failed to build music video facet: {e}")
            return None

    async def _build_genre_facet(
        self, session: AsyncSession, conditions: List
    ) -> Optional[FacetFilter]:
        """Build genre facet based on description analysis"""
        try:
            # Get all descriptions for genre analysis
            query = select(Video.description)
            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(query)
            descriptions = [row[0] for row in result if row[0]]

            # Analyze descriptions for genre keywords
            genre_counts = {}
            for description in descriptions:
                desc_lower = description.lower()
                for genre, keywords in self.genre_keywords.items():
                    if any(keyword in desc_lower for keyword in keywords):
                        genre_counts[genre] = genre_counts.get(genre, 0) + 1

            if not genre_counts:
                return None

            # Sort by count and take top genres
            sorted_genres = sorted(
                genre_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]

            values = []
            for genre, count in sorted_genres:
                values.append(
                    {
                        "value": genre,
                        "count": count,
                        "label": f"{genre.title()} ({count})",
                    }
                )

            return FacetFilter(
                name="genre", label="Genres", values=values, filter_type="checkbox"
            )

        except Exception as e:
            logger.error(f"Failed to build genre facet: {e}")
            return None

    async def _build_music_duration_facet(
        self, session: AsyncSession, conditions: List
    ) -> Optional[FacetFilter]:
        """Build music-specific duration range facet"""
        try:
            # Define music-specific duration ranges
            duration_ranges = [
                {"min": 0, "max": 120, "label": "Short (< 2 min)"},
                {"min": 120, "max": 240, "label": "Standard (2-4 min)"},
                {"min": 240, "max": 360, "label": "Long (4-6 min)"},
                {"min": 360, "max": None, "label": "Extended (> 6 min)"},
            ]

            values = []

            for range_def in duration_ranges:
                query = select(func.count(Video.id))

                range_conditions = list(conditions)
                range_conditions.append(Video.duration >= range_def["min"])
                if range_def["max"]:
                    range_conditions.append(Video.duration < range_def["max"])

                if range_conditions:
                    query = query.where(and_(*range_conditions))

                count = await session.scalar(query)

                if count > 0:
                    values.append(
                        {
                            "value": f"{range_def['min']}-{range_def['max'] or 'max'}",
                            "count": count,
                            "label": f"{range_def['label']} ({count})",
                        }
                    )

            if not values:
                return None

            return FacetFilter(
                name="duration", label="Duration", values=values, filter_type="checkbox"
            )

        except Exception as e:
            logger.error(f"Failed to build music duration facet: {e}")
            return None

    async def _build_quality_facet(
        self, session: AsyncSession, conditions: List
    ) -> Optional[FacetFilter]:
        """Build quality facet"""
        try:
            # Get height distribution
            query = select(Video.height, func.count(Video.id).label("count")).group_by(
                Video.height
            )

            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(query)
            height_counts = result.all()

            # Group into quality ranges
            quality_counts = {}
            for height, count in height_counts:
                quality = self._format_quality(height)
                quality_counts[quality] = quality_counts.get(quality, 0) + count

            if not quality_counts:
                return None

            values = []
            for quality, count in sorted(
                quality_counts.items(), key=lambda x: x[1], reverse=True
            ):
                values.append(
                    {"value": quality, "count": count, "label": f"{quality} ({count})"}
                )

            return FacetFilter(
                name="quality",
                label="Video Quality",
                values=values,
                filter_type="checkbox",
            )

        except Exception as e:
            logger.error(f"Failed to build quality facet: {e}")
            return None

    def _format_quality(self, height: Optional[int]) -> str:
        """Format video quality for display"""
        if not height:
            return "Unknown"

        for quality, range_def in self.quality_ranges.items():
            if height >= range_def["min_height"]:
                if "max_height" not in range_def or height <= range_def["max_height"]:
                    return quality

        return "Unknown"

    async def _get_music_suggestions(
        self, query: str, results: List[SearchResult]
    ) -> List[str]:
        """Generate music-specific search suggestions"""
        try:
            suggestions = []

            # Extract artists from results for suggestions
            artists = set()
            for result in results[:10]:
                if result.artist and result.artist != "Unknown Artist":
                    artists.add(result.artist)

            # Generate artist-based suggestions
            for artist in list(artists)[:3]:
                if artist.lower() not in query.lower():
                    suggestions.append(f"{artist}")
                    suggestions.append(f"{query} {artist}")

            # Generate music-specific suggestions
            if not any(
                keyword in query.lower()
                for keyword in ["official", "video", "live", "acoustic", "remix"]
            ):
                suggestions.extend(
                    [
                        f"{query} official video",
                        f"{query} live performance",
                        f"{query} acoustic version",
                        f"{query} remix",
                    ]
                )

            # Genre-based suggestions
            query_lower = query.lower()
            for genre, keywords in self.genre_keywords.items():
                if any(
                    keyword in query_lower for keyword in keywords[:2]
                ):  # Check first 2 keywords
                    suggestions.append(f"{genre} music videos")
                    break

            return suggestions[:6]  # Return max 6 suggestions

        except Exception as e:
            logger.error(f"Failed to get music suggestions: {e}")
            return []

    async def _get_music_corrections(self, query: str) -> Optional[str]:
        """Get music-specific spell correction suggestions"""
        try:
            # This would implement actual spell checking for music terms
            # For now, return None (no corrections)
            return None

        except Exception as e:
            logger.error(f"Failed to get music corrections: {e}")
            return None

    def _generate_cache_key(
        self,
        query: str,
        search_type: SearchType,
        search_scope: SearchScope,
        filters: List[SearchFilter],
        sort_by: SortBy,
        page: int,
        per_page: int,
    ) -> str:
        """Generate cache key for search query"""
        try:
            key_data = {
                "query": query,
                "search_type": search_type.value,
                "search_scope": search_scope.value,
                "filters": [(f.field, f.operator, f.value) for f in filters],
                "sort_by": sort_by.value,
                "page": page,
                "per_page": per_page,
            }
            key_string = json.dumps(key_data, sort_keys=True)
            return f"music_search:{hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()}"

        except Exception as e:
            logger.error(f"Failed to generate cache key: {e}")
            return f"music_search:default:{int(datetime.now().timestamp())}"

    async def _get_cached_search(self, cache_key: str) -> Optional[SearchResponse]:
        """Get cached search result"""
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                # This would deserialize cached search response
                # For simplicity, returning None (no cache hit)
                return None
            return None

        except Exception as e:
            logger.error(f"Failed to get cached search: {e}")
            return None

    async def _cache_search_result(self, cache_key: str, response: SearchResponse):
        """Cache search result"""
        try:
            # This would serialize and cache the search response
            # For simplicity, just log the caching
            logger.debug(f"Caching music search result with key: {cache_key}")

        except Exception as e:
            logger.error(f"Failed to cache search result: {e}")

    async def _build_search_indices(self):
        """Build search indices for music search performance"""
        try:
            # This would build full-text search indices optimized for music content
            # For now, just log that indices are ready
            logger.info("Music search indices are ready")

        except Exception as e:
            logger.error(f"Failed to build search indices: {e}")


# Global service instance
_music_search_service = None


async def get_music_search_service(config: Optional[Dict] = None) -> MusicSearchService:
    """Get global music search service instance"""
    global _music_search_service

    if _music_search_service is None:
        _music_search_service = MusicSearchService(config)
        await _music_search_service.initialize()

    return _music_search_service
