"""
Personal analytics service for MVidarr.

Provides simple collection insights for home self-hosters:
- Collection statistics
- Personal viewing insights
- Collection health assessment
- Discovery suggestions
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_

logger = logging.getLogger(__name__)


def get_collection_statistics() -> Dict:
    """
    Get basic collection statistics.

    Returns:
        Dict with collection stats
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Artist, Playlist, Video

        with get_db() as session:
            # Video statistics
            total_videos = session.query(Video).count()
            downloaded_videos = (
                session.query(Video).filter(Video.local_path.isnot(None)).count()
            )

            # Get total duration
            total_duration_result = (
                session.query(func.sum(Video.duration))
                .filter(Video.duration.isnot(None))
                .scalar()
            )
            total_duration_seconds = int(total_duration_result or 0)

            # Artist statistics
            total_artists = session.query(Artist).count()
            monitored_artists = (
                session.query(Artist).filter(Artist.monitored == True).count()
            )

            # Playlist statistics
            total_playlists = session.query(Playlist).count()

            # Genre statistics - count distinct genres from videos
            # Genres are stored as JSON arrays in the videos table
            videos_with_genres = (
                session.query(Video).filter(Video.genres.isnot(None)).all()
            )

            unique_genres = set()
            for video in videos_with_genres:
                if video.genres and isinstance(video.genres, list):
                    unique_genres.update(video.genres)

            total_genres = len(unique_genres)

            # Videos by year (using year field instead of release_date)
            videos_by_year = (
                session.query(
                    Video.year.label("year"),
                    func.count(Video.id).label("count"),
                )
                .filter(Video.year.isnot(None))
                .group_by(Video.year)
                .order_by(Video.year.desc())
                .limit(10)
                .all()
            )

            return {
                "success": True,
                "videos": {
                    "total": total_videos,
                    "downloaded": downloaded_videos,
                    "pending": total_videos - downloaded_videos,
                    "total_duration_seconds": total_duration_seconds,
                    "total_duration_hours": round(total_duration_seconds / 3600, 1),
                    "average_duration_minutes": (
                        round(total_duration_seconds / total_videos / 60, 1)
                        if total_videos > 0
                        else 0
                    ),
                },
                "artists": {
                    "total": total_artists,
                    "monitored": monitored_artists,
                    "unmonitored": total_artists - monitored_artists,
                },
                "playlists": {
                    "total": total_playlists,
                },
                "genres": {
                    "total": total_genres,
                },
                "by_year": [
                    {"year": year, "count": count} for year, count in videos_by_year
                ],
            }
    except Exception as e:
        logger.error(f"Error getting collection statistics: {e}")
        return {"success": False, "error": str(e)}


def get_top_artists(limit: int = 10) -> Dict:
    """
    Get top artists by video count.

    Args:
        limit: Number of artists to return

    Returns:
        Dict with top artists
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Artist, Video

        with get_db() as session:
            top_artists = (
                session.query(
                    Artist.id, Artist.name, func.count(Video.id).label("video_count")
                )
                .join(Video, Video.artist_id == Artist.id)
                .group_by(Artist.id, Artist.name)
                .order_by(func.count(Video.id).desc())
                .limit(limit)
                .all()
            )

            return {
                "success": True,
                "artists": [
                    {"id": artist_id, "name": name, "video_count": count}
                    for artist_id, name, count in top_artists
                ],
            }
    except Exception as e:
        logger.error(f"Error getting top artists: {e}")
        return {"success": False, "error": str(e)}


def get_top_genres(limit: int = 10) -> Dict:
    """
    Get top genres by video count.

    Args:
        limit: Number of genres to return

    Returns:
        Dict with top genres
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Video

        with get_db() as session:
            # Get all videos with genres
            videos_with_genres = (
                session.query(Video).filter(Video.genres.isnot(None)).all()
            )

            # Count genre occurrences
            genre_counts = {}
            for video in videos_with_genres:
                if video.genres and isinstance(video.genres, list):
                    for genre in video.genres:
                        if genre:  # Skip empty strings
                            genre_counts[genre] = genre_counts.get(genre, 0) + 1

            # Sort by count and limit
            top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[
                :limit
            ]

            return {
                "success": True,
                "genres": [
                    {"name": genre, "video_count": count} for genre, count in top_genres
                ],
            }
    except Exception as e:
        logger.error(f"Error getting top genres: {e}")
        return {"success": False, "error": str(e), "genres": []}


def get_collection_health() -> Dict:
    """
    Assess collection health - identify videos with missing metadata.

    Returns:
        Dict with health assessment
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Video

        with get_db() as session:
            total_videos = session.query(Video).count()

            # Missing metadata checks
            missing_thumbnail = (
                session.query(Video)
                .filter(or_(Video.thumbnail_url.is_(None), Video.thumbnail_url == ""))
                .count()
            )

            missing_duration = (
                session.query(Video).filter(Video.duration.is_(None)).count()
            )

            missing_release_date = (
                session.query(Video).filter(Video.release_date.is_(None)).count()
            )

            missing_description = (
                session.query(Video)
                .filter(or_(Video.description.is_(None), Video.description == ""))
                .count()
            )

            missing_file = (
                session.query(Video)
                .filter(or_(Video.local_path.is_(None), Video.local_path == ""))
                .count()
            )

            # Calculate health score (simple percentage)
            issues = (
                missing_thumbnail
                + missing_duration
                + missing_release_date
                + missing_description
                + missing_file
            )
            max_possible_issues = total_videos * 5  # 5 metadata fields
            health_score = 100
            if max_possible_issues > 0:
                health_score = round((1 - (issues / max_possible_issues)) * 100, 1)

            return {
                "success": True,
                "total_videos": total_videos,
                "health_score": health_score,
                "issues": {
                    "missing_thumbnail": missing_thumbnail,
                    "missing_duration": missing_duration,
                    "missing_release_date": missing_release_date,
                    "missing_description": missing_description,
                    "missing_file": missing_file,
                },
                "recommendations": generate_health_recommendations(
                    {
                        "missing_thumbnail": missing_thumbnail,
                        "missing_duration": missing_duration,
                        "missing_release_date": missing_release_date,
                        "missing_description": missing_description,
                        "missing_file": missing_file,
                    }
                ),
            }
    except Exception as e:
        logger.error(f"Error assessing collection health: {e}")
        return {"success": False, "error": str(e)}


def generate_health_recommendations(issues: Dict) -> List[str]:
    """
    Generate recommendations based on collection health issues.

    Args:
        issues: Dict of issue counts

    Returns:
        List of recommendation strings
    """
    recommendations = []

    if issues.get("missing_thumbnail", 0) > 10:
        recommendations.append(
            f"Run thumbnail generation for {issues['missing_thumbnail']} videos"
        )

    if issues.get("missing_file", 0) > 0:
        recommendations.append(f"Download {issues['missing_file']} pending videos")

    if issues.get("missing_release_date", 0) > 20:
        recommendations.append(
            f"Enrich metadata for {issues['missing_release_date']} videos missing release dates"
        )

    if issues.get("missing_description", 0) > 50:
        recommendations.append(
            "Consider running metadata enrichment to fill in missing descriptions"
        )

    if not recommendations:
        recommendations.append("Collection is in good health! 🎉")

    return recommendations


def get_recent_additions(days: int = 30, limit: int = 10) -> Dict:
    """
    Get recently added videos.

    Args:
        days: Number of days to look back
        limit: Max number of videos to return

    Returns:
        Dict with recent videos
    """
    try:
        from src.database.connection import get_db
        from src.database.models import Artist, Video

        cutoff_date = datetime.now() - timedelta(days=days)

        with get_db() as session:
            recent_videos = (
                session.query(
                    Video.id,
                    Video.title,
                    Video.created_at,
                    Artist.name.label("artist_name"),
                )
                .join(Artist, Video.artist_id == Artist.id)
                .filter(Video.created_at >= cutoff_date)
                .order_by(Video.created_at.desc())
                .limit(limit)
                .all()
            )

            return {
                "success": True,
                "videos": [
                    {
                        "id": video_id,
                        "title": title,
                        "artist_name": artist_name,
                        "added_at": created_at.isoformat() if created_at else None,
                    }
                    for video_id, title, created_at, artist_name in recent_videos
                ],
            }
    except Exception as e:
        logger.error(f"Error getting recent additions: {e}")
        return {"success": False, "error": str(e)}


def get_analytics_summary() -> Dict:
    """
    Get comprehensive analytics summary.

    Returns:
        Dict with all analytics data
    """
    return {
        "collection": get_collection_statistics(),
        "top_artists": get_top_artists(limit=10),
        "top_genres": get_top_genres(limit=10),
        "health": get_collection_health(),
        "recent_additions": get_recent_additions(days=30, limit=10),
    }


def export_collection_csv() -> str:
    """
    Export collection data as CSV.

    Returns:
        CSV string
    """
    try:
        import csv
        from io import StringIO

        from src.database.connection import get_db
        from src.database.models import Artist, Video

        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "Video ID",
                "Title",
                "Artist",
                "Release Date",
                "Duration (seconds)",
                "File Path",
                "Added Date",
            ]
        )

        # Write data
        with get_db() as session:
            videos = (
                session.query(
                    Video.id,
                    Video.title,
                    Artist.name,
                    Video.release_date,
                    Video.duration,
                    Video.local_path,
                    Video.created_at,
                )
                .join(Artist, Video.artist_id == Artist.id)
                .order_by(Artist.name, Video.title)
                .all()
            )

            for video in videos:
                writer.writerow(
                    [
                        video.id,
                        video.title or "",
                        video.name or "",
                        video.release_date.isoformat() if video.release_date else "",
                        video.duration or "",
                        video.local_path or "",
                        video.created_at.isoformat() if video.created_at else "",
                    ]
                )

        return output.getvalue()
    except Exception as e:
        logger.error(f"Error exporting collection CSV: {e}")
        return f"Error: {str(e)}"
