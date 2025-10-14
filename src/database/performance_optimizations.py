"""
Database Performance Optimizations for MVidarr
Implements strategic indexes and query optimizations for critical bottlenecks
"""

from sqlalchemy import text

from src.database.connection import engine
from src.database.models import Artist, Download, Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.database.performance")


class DatabasePerformanceOptimizer:
    """Handles database performance optimizations"""

    def __init__(self):
        self.engine = engine
        self.dialect_name = engine.dialect.name

    def create_performance_indexes(self):
        """Create strategic indexes for performance optimization"""

        # Get the current connection
        with self.engine.connect() as conn:

            # 1. Composite index for video search optimization
            # Optimizes: video search with status + title filtering
            try:
                if self.dialect_name == "mysql":
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_search_composite 
                        ON videos(status, title(100), artist_id)
                    """
                        )
                    )
                else:
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_search_composite 
                        ON videos(status, title, artist_id)
                    """
                        )
                    )
                print("✅ Created composite search index for videos")
            except Exception as e:
                print(f"⚠️ Search composite index already exists or failed: {e}")

            # 2. Full-text search indexes for title and artist name
            try:
                if self.dialect_name == "mysql":
                    # MySQL full-text indexes
                    conn.execute(
                        text(
                            """
                        CREATE FULLTEXT INDEX IF NOT EXISTS idx_video_title_fulltext 
                        ON videos(title)
                    """
                        )
                    )
                    conn.execute(
                        text(
                            """
                        CREATE FULLTEXT INDEX IF NOT EXISTS idx_artist_name_fulltext 
                        ON artists(name)
                    """
                        )
                    )
                    print("✅ Created MySQL full-text search indexes")
                elif self.dialect_name == "postgresql":
                    # PostgreSQL GIN indexes for text search
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_title_gin 
                        ON videos USING gin(to_tsvector('english', title))
                    """
                        )
                    )
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_artist_name_gin 
                        ON artists USING gin(to_tsvector('english', name))
                    """
                        )
                    )
                    print("✅ Created PostgreSQL GIN text search indexes")
                else:
                    # SQLite - use trigram-like approach with expression index
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_title_lower 
                        ON videos(LOWER(title))
                    """
                        )
                    )
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_artist_name_lower 
                        ON artists(LOWER(name))
                    """
                        )
                    )
                    print("✅ Created SQLite case-insensitive indexes")
            except Exception as e:
                print(f"⚠️ Full-text indexes failed or already exist: {e}")

            # 3. JSON genre search optimization
            try:
                if self.dialect_name == "mysql":
                    # MySQL JSON index
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_genres_json 
                        ON videos((CAST(genres AS CHAR(255) ARRAY)))
                    """
                        )
                    )
                elif self.dialect_name == "postgresql":
                    # PostgreSQL JSON GIN index
                    conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_video_genres_gin 
                        ON videos USING gin(genres)
                    """
                        )
                    )
                else:
                    # SQLite - basic JSON support
                    pass
                print("✅ Created JSON genre search index")
            except Exception as e:
                print(f"⚠️ JSON genre index failed or not supported: {e}")

            # 4. Composite index for artist listing with video counts
            try:
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_artist_monitoring_composite 
                    ON artists(monitored, name, created_at)
                """
                    )
                )
                print("✅ Created artist monitoring composite index")
            except Exception as e:
                print(f"⚠️ Artist composite index failed: {e}")

            # 5. Video filtering composite indexes
            try:
                # Status + quality filtering
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_video_status_quality 
                    ON videos(status, quality)
                """
                    )
                )

                # Source + status filtering
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_video_source_status 
                    ON videos(source, status)
                """
                    )
                )

                # Date range filtering
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_video_created_status 
                    ON videos(created_at, status)
                """
                    )
                )

                print("✅ Created video filtering composite indexes")
            except Exception as e:
                print(f"⚠️ Video filtering indexes failed: {e}")

            # 6. Download queue optimization
            try:
                conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS idx_download_queue_composite 
                    ON downloads(status, priority, created_at)
                """
                    )
                )
                print("✅ Created download queue composite index")
            except Exception as e:
                print(f"⚠️ Download queue index failed: {e}")

            # Commit all changes
            conn.commit()
            print("🎯 Database performance indexes created successfully!")

    def optimize_video_search_query(self, session, filters):
        """Optimized video search query with strategic joins and filters"""
        from sqlalchemy import and_, func, or_

        # Start with base video query - avoid unnecessary joins
        query = session.query(Video)

        # Only join Artist table if needed
        need_artist_join = (
            filters.get("query")
            or filters.get("artist_name")
            or "artist" in str(filters.get("sort_by", ""))
        )

        if need_artist_join:
            query = query.join(Artist)

        # Apply filters in order of selectivity (most selective first)

        # Status filter (usually very selective)
        if filters.get("status"):
            try:
                # Convert string to VideoStatus enum
                logger.debug(
                    f"Converting status filter '{filters['status']}' to VideoStatus enum"
                )
                status_enum = VideoStatus(filters["status"])
                query = query.filter(Video.status == status_enum)
                logger.debug(f"Successfully applied status filter: {status_enum}")
            except ValueError as ve:
                # Invalid status value, skip filter
                logger.error(
                    f"Invalid video status filter: {filters['status']}, error: {ve}"
                )
                logger.error(
                    f"Valid VideoStatus values: {[status.value for status in VideoStatus]}"
                )
                pass
            except Exception as e:
                # Catch any other errors during status filtering
                logger.error(f"Unexpected error during status filtering: {e}")
                logger.error(f"Status filter value: {filters['status']}")
                raise

        # Source filter (often selective)
        if filters.get("source"):
            if filters["source"] == "youtube":
                query = query.filter(Video.youtube_id.isnot(None))
            elif filters["source"] == "imvdb":
                query = query.filter(Video.imvdb_id.isnot(None))
            elif filters["source"] == "manual":
                query = query.filter(
                    and_(Video.youtube_id.is_(None), Video.imvdb_id.is_(None))
                )

        # Quality filter
        if filters.get("quality"):
            query = query.filter(Video.quality == filters["quality"])

        # Year filter
        if filters.get("year"):
            try:
                year_int = int(filters["year"])
                query = query.filter(Video.year == year_int)
            except ValueError:
                pass

        # Text search (use appropriate method based on database)
        if filters.get("query"):
            search_term = filters["query"]

            if self.dialect_name == "mysql":
                # Use MySQL full-text search
                if need_artist_join:
                    query = query.filter(
                        or_(
                            func.match(Video.title).against(search_term),
                            func.match(Artist.name).against(search_term),
                        )
                    )
                else:
                    query = query.filter(func.match(Video.title).against(search_term))
            elif self.dialect_name == "postgresql":
                # Use PostgreSQL text search
                if need_artist_join:
                    query = query.filter(
                        or_(
                            func.to_tsvector("english", Video.title).match(
                                func.plainto_tsquery("english", search_term)
                            ),
                            func.to_tsvector("english", Artist.name).match(
                                func.plainto_tsquery("english", search_term)
                            ),
                        )
                    )
                else:
                    query = query.filter(
                        func.to_tsvector("english", Video.title).match(
                            func.plainto_tsquery("english", search_term)
                        )
                    )
            else:
                # Fallback for SQLite - use case-insensitive LIKE with indexes
                search_lower = search_term.lower()
                if need_artist_join:
                    query = query.filter(
                        or_(
                            func.lower(Video.title).contains(search_lower),
                            func.lower(Artist.name).contains(search_lower),
                        )
                    )
                else:
                    query = query.filter(func.lower(Video.title).contains(search_lower))

        # Artist name filter (separate from general search)
        if filters.get("artist_name"):
            if self.dialect_name in ["mysql", "postgresql"]:
                query = query.filter(
                    func.lower(Artist.name).contains(filters["artist_name"].lower())
                )
            else:
                query = query.filter(Artist.name.contains(filters["artist_name"]))

        # Genre filter (optimize JSON search)
        if filters.get("genre"):
            genre = filters["genre"]
            if self.dialect_name == "postgresql":
                # Use PostgreSQL JSON operators
                query = query.filter(Video.genres.op("?")(genre))
            elif self.dialect_name == "mysql":
                # Use MySQL JSON_CONTAINS
                query = query.filter(func.json_contains(Video.genres, f'"{genre}"'))
            else:
                # Fallback for SQLite
                query = query.filter(Video.genres.contains(f'"{genre}"'))

        # Thumbnail filter
        if filters.get("has_thumbnail"):
            has_thumbnail_bool = filters["has_thumbnail"].lower() in [
                "true",
                "1",
                "yes",
            ]
            if has_thumbnail_bool:
                query = query.filter(Video.thumbnail_path.isnot(None))
            else:
                query = query.filter(Video.thumbnail_path.is_(None))

        # Date range filters
        if filters.get("date_from"):
            try:
                from datetime import datetime

                date_from = datetime.strptime(filters["date_from"], "%Y-%m-%d")
                query = query.filter(Video.created_at >= date_from)
            except ValueError:
                pass

        if filters.get("date_to"):
            try:
                from datetime import datetime

                date_to = datetime.strptime(filters["date_to"], "%Y-%m-%d")
                query = query.filter(Video.created_at <= date_to)
            except ValueError:
                pass

        # Duration range filters
        if filters.get("duration_min"):
            try:
                duration_min = int(filters["duration_min"]) * 60  # Convert to seconds
                query = query.filter(Video.duration >= duration_min)
            except (ValueError, TypeError):
                pass

        if filters.get("duration_max"):
            try:
                duration_max = int(filters["duration_max"]) * 60  # Convert to seconds
                query = query.filter(Video.duration <= duration_max)
            except (ValueError, TypeError):
                pass

        # Keywords filter - search in video title and description
        if filters.get("keywords"):
            keywords = filters["keywords"].strip()
            if keywords:
                keyword_list = [
                    k.strip().lower() for k in keywords.split(",") if k.strip()
                ]
                if keyword_list:
                    from sqlalchemy import func, or_

                    # Create OR conditions for each keyword
                    keyword_conditions = []
                    for keyword in keyword_list:
                        keyword_conditions.append(
                            func.lower(Video.title).contains(keyword)
                        )
                        # Only search description if it exists
                        keyword_conditions.append(
                            func.lower(Video.description).contains(keyword)
                        )
                    query = query.filter(or_(*keyword_conditions))

        # Year range filters (from frontend - year_from/year_to)
        year_from = filters.get("year_from")
        year_to = filters.get("year_to")
        if year_from:
            try:
                year_from_int = int(year_from)
                query = query.filter(Video.year >= year_from_int)
            except (ValueError, TypeError):
                pass
        if year_to:
            try:
                year_to_int = int(year_to)
                query = query.filter(Video.year <= year_to_int)
            except (ValueError, TypeError):
                pass

        return query

    def get_optimized_artist_video_counts(self, session, monitored_only=True):
        """Optimized query for artist video counts to avoid N+1 problem"""
        from sqlalchemy import func

        # Single query to get all artists with video counts
        subquery = (
            session.query(Video.artist_id, func.count(Video.id).label("video_count"))
            .filter(
                Video.status.in_(
                    ["DOWNLOADED", "WANTED", "DOWNLOADING"]
                )  # Only count relevant videos
            )
            .group_by(Video.artist_id)
            .subquery()
        )

        # Main query with left join to get all artists
        query = session.query(
            Artist, func.coalesce(subquery.c.video_count, 0).label("video_count")
        ).outerjoin(subquery, Artist.id == subquery.c.artist_id)

        if monitored_only:
            query = query.filter(Artist.monitored == True)

        return query

    def create_materialized_artist_counts(self):
        """Create a materialized view for artist video counts (PostgreSQL/MySQL)"""

        with self.engine.connect() as conn:
            try:
                if self.dialect_name == "postgresql":
                    # PostgreSQL materialized view
                    conn.execute(
                        text(
                            """
                        CREATE MATERIALIZED VIEW IF NOT EXISTS artist_video_counts AS
                        SELECT 
                            a.id as artist_id,
                            a.name,
                            a.monitored,
                            COALESCE(v.video_count, 0) as video_count,
                            COALESCE(v.downloaded_count, 0) as downloaded_count
                        FROM artists a
                        LEFT JOIN (
                            SELECT 
                                artist_id,
                                COUNT(*) as video_count,
                                SUM(CASE WHEN status = 'DOWNLOADED' THEN 1 ELSE 0 END) as downloaded_count
                            FROM videos 
                            WHERE status IN ('DOWNLOADED', 'WANTED', 'DOWNLOADING')
                            GROUP BY artist_id
                        ) v ON a.id = v.artist_id;
                        
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_artist_counts_id 
                        ON artist_video_counts(artist_id);
                    """
                        )
                    )
                    print("✅ Created PostgreSQL materialized view for artist counts")

                elif self.dialect_name == "mysql":
                    # MySQL doesn't have materialized views, create a regular table
                    conn.execute(
                        text(
                            """
                        CREATE TABLE IF NOT EXISTS artist_video_counts (
                            artist_id INT PRIMARY KEY,
                            name VARCHAR(255),
                            monitored BOOLEAN,
                            video_count INT DEFAULT 0,
                            downloaded_count INT DEFAULT 0,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_artist_counts_monitored (monitored),
                            INDEX idx_artist_counts_video_count (video_count)
                        );
                    """
                        )
                    )
                    print("✅ Created MySQL table for artist counts cache")

                conn.commit()

            except Exception as e:
                print(f"⚠️ Materialized view creation failed: {e}")

    def refresh_artist_counts_cache(self):
        """Refresh the artist video counts cache"""

        with self.engine.connect() as conn:
            try:
                if self.dialect_name == "postgresql":
                    conn.execute(text("REFRESH MATERIALIZED VIEW artist_video_counts;"))
                    print("✅ Refreshed PostgreSQL materialized view")

                elif self.dialect_name == "mysql":
                    # Refresh MySQL cache table
                    conn.execute(
                        text(
                            """
                        REPLACE INTO artist_video_counts (artist_id, name, monitored, video_count, downloaded_count)
                        SELECT 
                            a.id,
                            a.name,
                            a.monitored,
                            COALESCE(v.video_count, 0),
                            COALESCE(v.downloaded_count, 0)
                        FROM artists a
                        LEFT JOIN (
                            SELECT 
                                artist_id,
                                COUNT(*) as video_count,
                                SUM(CASE WHEN status = 'DOWNLOADED' THEN 1 ELSE 0 END) as downloaded_count
                            FROM videos 
                            WHERE status IN ('DOWNLOADED', 'WANTED', 'DOWNLOADING')
                            GROUP BY artist_id
                        ) v ON a.id = v.artist_id;
                    """
                        )
                    )
                    print("✅ Refreshed MySQL artist counts cache")

                conn.commit()

            except Exception as e:
                print(f"⚠️ Cache refresh failed: {e}")

    def get_bulk_video_files_data(self, session, file_paths_list):
        """Optimized bulk retrieval of video file data to avoid N+1 queries during indexing"""

        if not file_paths_list:
            return {}

        # Create a mapping for quick lookups
        path_map = {}

        # Query for existing videos and downloads in batches
        batch_size = 100
        existing_videos = {}
        existing_downloads = {}

        for i in range(0, len(file_paths_list), batch_size):
            batch_paths = file_paths_list[i : i + batch_size]

            # Query videos with local_path matching
            video_results = (
                session.query(Video).filter(Video.local_path.in_(batch_paths)).all()
            )

            for video in video_results:
                existing_videos[video.local_path] = video

            # Query downloads with file_path matching
            download_results = (
                session.query(Download)
                .filter(Download.file_path.in_(batch_paths))
                .all()
            )

            for download in download_results:
                existing_downloads[download.file_path] = download

        # Bulk load all artists to avoid repeated queries
        all_artists = session.query(Artist).all()
        artists_by_name = {artist.name.lower(): artist for artist in all_artists}
        artists_by_id = {artist.id: artist for artist in all_artists}

        return {
            "existing_videos": existing_videos,
            "existing_downloads": existing_downloads,
            "artists_by_name": artists_by_name,
            "artists_by_id": artists_by_id,
        }

    def optimize_bulk_insert_videos(self, session, video_data_list):
        """Optimized bulk insert for videos to improve indexing performance"""
        from sqlalchemy import insert

        if not video_data_list:
            return []

        try:
            # Use bulk insert for better performance
            stmt = insert(Video)
            result = session.execute(stmt, video_data_list)
            session.flush()  # Ensure we get the IDs back

            # Return the inserted video IDs
            return list(result.inserted_primary_key_rows)

        except Exception as e:
            print(f"⚠️ Bulk insert failed, falling back to individual inserts: {e}")
            # Fallback to individual inserts
            inserted_videos = []
            for video_data in video_data_list:
                try:
                    video = Video(**video_data)
                    session.add(video)
                    session.flush()
                    inserted_videos.append(video)
                except Exception as e2:
                    print(
                        f"⚠️ Individual insert failed for {video_data.get('title', 'unknown')}: {e2}"
                    )

            return inserted_videos

    def optimize_bulk_insert_artists(self, session, artist_data_list):
        """Optimized bulk insert for artists"""
        from sqlalchemy import insert

        if not artist_data_list:
            return []

        try:
            # Use bulk insert for better performance
            stmt = insert(Artist)
            result = session.execute(stmt, artist_data_list)
            session.flush()

            return list(result.inserted_primary_key_rows)

        except Exception as e:
            print(f"⚠️ Bulk artist insert failed, falling back: {e}")
            # Fallback to individual inserts
            inserted_artists = []
            for artist_data in artist_data_list:
                try:
                    artist = Artist(**artist_data)
                    session.add(artist)
                    session.flush()
                    inserted_artists.append(artist)
                except Exception as e2:
                    print(
                        f"⚠️ Individual artist insert failed for {artist_data.get('name', 'unknown')}: {e2}"
                    )

            return inserted_artists

    def analyze_query_performance(self):
        """Analyze current query performance and identify slow queries"""

        with self.engine.connect() as conn:
            try:
                if self.dialect_name == "mysql":
                    # Enable query logging temporarily
                    result = conn.execute(
                        text(
                            """
                        SELECT 
                            sql_text,
                            exec_count,
                            avg_timer_wait/1000000000 as avg_seconds,
                            sum_timer_wait/1000000000 as total_seconds
                        FROM performance_schema.events_statements_summary_by_digest 
                        WHERE schema_name = DATABASE()
                        ORDER BY sum_timer_wait DESC 
                        LIMIT 10;
                    """
                        )
                    )

                    print("🔍 Top 10 slowest MySQL queries:")
                    for row in result:
                        print(
                            f"  {row.avg_seconds:.3f}s avg | {row.exec_count} executions | {row.sql_text[:100]}..."
                        )

                elif self.dialect_name == "postgresql":
                    # Check if pg_stat_statements is enabled
                    result = conn.execute(
                        text(
                            """
                        SELECT query, calls, mean_exec_time, total_exec_time
                        FROM pg_stat_statements 
                        WHERE query LIKE '%videos%' OR query LIKE '%artists%'
                        ORDER BY total_exec_time DESC 
                        LIMIT 10;
                    """
                        )
                    )

                    print("🔍 Top 10 slowest PostgreSQL queries:")
                    for row in result:
                        print(
                            f"  {row.mean_exec_time:.3f}ms avg | {row.calls} calls | {row.query[:100]}..."
                        )

            except Exception as e:
                print(f"⚠️ Query performance analysis not available: {e}")
                print(
                    "💡 Consider enabling performance schema (MySQL) or pg_stat_statements (PostgreSQL)"
                )

    def optimize_video_indexing_stats(self, session):
        """Optimized query for video indexing statistics"""
        from sqlalchemy import case, func

        from src.database.models import VideoStatus

        # Single query to get all statistics at once
        stats_query = (
            session.query(
                func.count(Artist.id).label("total_artists"),
                func.count(Video.id).label("total_videos"),
                func.count(Download.id).label("total_downloads"),
                func.sum(case((Video.imvdb_id.isnot(None), 1), else_=0)).label(
                    "videos_with_imvdb"
                ),
                func.sum(
                    case((Video.status == VideoStatus.DOWNLOADED, 1), else_=0)
                ).label("downloaded_videos"),
                func.sum(case((Download.file_path.isnot(None), 1), else_=0)).label(
                    "videos_with_files"
                ),
            )
            .select_from(Artist)
            .outerjoin(Video)
            .outerjoin(Download)
        )

        result = stats_query.first()

        total_videos = result.total_videos or 0
        videos_with_imvdb = result.videos_with_imvdb or 0

        return {
            "total_artists": result.total_artists or 0,
            "total_videos": total_videos,
            "total_downloads": result.total_downloads or 0,
            "videos_with_imvdb": videos_with_imvdb,
            "downloaded_videos": result.downloaded_videos or 0,
            "videos_with_files": result.videos_with_files or 0,
            "imvdb_coverage": (
                round((videos_with_imvdb / total_videos * 100), 2)
                if total_videos > 0
                else 0
            ),
        }
