"""
FastAPI Genres API
Provides genre-related endpoints for video and artist genre management
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.database.models import Video, Artist
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.genres")


def parse_genre_string(genre_string):
    """Parse genre string into list, handling different formats - completely safe version"""
    try:
        # Handle None/empty
        if not genre_string:
            return []
        
        # Handle lists - directly return processed list
        if isinstance(genre_string, list):
            result = []
            for item in genre_string:
                if item and isinstance(item, str):
                    clean_item = item.strip()
                    if clean_item:
                        result.append(clean_item)
                elif item and not isinstance(item, str):
                    # Convert non-string items to strings
                    clean_item = str(item).strip()
                    if clean_item and clean_item not in ['None', 'null']:
                        result.append(clean_item)
            return result
        
        # Convert everything else to string first
        if not isinstance(genre_string, str):
            genre_string = str(genre_string)
        
        # Now we definitely have a string
        genre_string = genre_string.strip()
        if not genre_string or genre_string in ['None', 'null', '[]', '{}']:
            return []
        
        # Try JSON parsing first
        if (genre_string.startswith('[') and genre_string.endswith(']')) or \
           (genre_string.startswith('"[') and genre_string.endswith(']"')):
            import json
            try:
                # Remove outer quotes if present
                json_str = genre_string
                if json_str.startswith('"') and json_str.endswith('"'):
                    json_str = json_str[1:-1]
                
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except:
                pass
        
        # Try ast.literal_eval for Python list strings
        if genre_string.startswith("['") or genre_string.startswith('["'):
            import ast
            try:
                parsed = ast.literal_eval(genre_string)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except:
                pass
        
        # Fallback: treat as comma-separated values
        parts = [part.strip() for part in genre_string.split(',')]
        return [part for part in parts if part and part not in ['None', 'null']]
        
    except Exception as e:
        # Absolute fallback - log the error and return empty list
        logger.error(f"CRITICAL: parse_genre_string failed completely for {type(genre_string)}: {repr(genre_string)}, error: {e}")
        return []


router = APIRouter(
    prefix="/api/genres", 
    tags=["genres"],
    responses={
        404: {"description": "Genre not found"}
    }
)


@router.get("/")
async def get_all_genres(
    limit: int = Query(100, ge=1, le=500),
    include_counts: bool = Query(True),
    session: Session = Depends(get_db_session)
):
    """Get all genres used in the system"""
    try:
        genre_stats = {}
        
        # Get video genres
        videos = session.query(Video.genres).filter(
            Video.genres.isnot(None), Video.genres != ''
        ).all()
        
        for (genre_string,) in videos:
            try:
                genre_list = parse_genre_string(genre_string)
                for genre in genre_list:
                    if genre and genre.strip():
                        genre_clean = genre.strip().lower()
                        if genre_clean not in genre_stats:
                            genre_stats[genre_clean] = {'video_count': 0, 'artist_count': 0, 'original_case': genre.strip()}
                        genre_stats[genre_clean]['video_count'] += 1
            except Exception as e:
                logger.warning(f"Failed to parse video genres: {genre_string}, error: {e}")
        
        # Get artist genres
        artists = session.query(Artist.genres).filter(
            Artist.genres.isnot(None), Artist.genres != ''
        ).all()
        
        for (genre_string,) in artists:
            try:
                genre_list = parse_genre_string(genre_string)
                for genre in genre_list:
                    if genre and genre.strip():
                        genre_clean = genre.strip().lower()
                        if genre_clean not in genre_stats:
                            genre_stats[genre_clean] = {'video_count': 0, 'artist_count': 0, 'original_case': genre.strip()}
                        genre_stats[genre_clean]['artist_count'] += 1
            except Exception as e:
                logger.warning(f"Failed to parse artist genres: {genre_string}, error: {e}")
        
        # Convert to response format and sort by total usage
        genre_list = []
        for genre_key, stats in genre_stats.items():
            total_count = stats['video_count'] + stats['artist_count']
            genre_list.append({
                'genre': stats['original_case'],
                'video_count': stats['video_count'],
                'artist_count': stats['artist_count'],
                'total_count': total_count
            })
        
        # Sort by total usage (descending)
        genre_list.sort(key=lambda x: x['total_count'], reverse=True)
        
        # Apply limit
        if len(genre_list) > limit:
            genre_list = genre_list[:limit]
        
        return {
            'genres': genre_list,
            'total_count': len(genre_list),
            'limit': limit,
            'include_counts': include_counts
        }
        
    except Exception as e:
        logger.error(f"Error getting genres: {e}")
        # Fallback to simple static response on error
        return {
            'genres': [
                {'genre': 'Error loading genres', 'video_count': 0, 'artist_count': 0, 'total_count': 0}
            ],
            'total_count': 1,
            'limit': limit,
            'include_counts': include_counts,
            'error': str(e)
        }


@router.get("/simple")
async def simple_genres():
    """Simple static endpoint to test if genres router works at all"""
    return {
        "genres": [
            {"genre": "rock", "count": 10},
            {"genre": "pop", "count": 5}
        ],
        "total_count": 2,
        "message": "Simple static response works"
    }


@router.get("/popular")
async def get_popular_genres(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db_session)
):
    """Get most popular genres by usage count"""
    try:
        # This is a simplified version that focuses on the most commonly used functionality
        genre_stats = {}
        
        # Get video genres
        videos = session.query(Video.genres).filter(
            Video.genres.isnot(None), Video.genres != ''
        ).all()
        
        for (genre_string,) in videos:
            genre_list = parse_genre_string(genre_string)
            for genre in genre_list:
                genre_stats[genre] = genre_stats.get(genre, 0) + 1
        
        # Sort and limit
        popular_genres = sorted(genre_stats.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        return {
            'genres': [
                {'genre': genre, 'count': count} 
                for genre, count in popular_genres
            ],
            'total_count': len(popular_genres),
            'limit': limit
        }
        
    except Exception as e:
        logger.error(f"Error getting popular genres: {e}")
        return {
            'genres': [],
            'total_count': 0,
            'limit': limit,
            'error': str(e)
        }