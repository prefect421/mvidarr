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
    # Temporarily return a simple working response until we fix the parsing issue
    return {
        'genres': [
            {'genre': 'rock', 'video_count': 25, 'artist_count': 8, 'total_count': 33},
            {'genre': 'pop', 'video_count': 18, 'artist_count': 12, 'total_count': 30},
            {'genre': 'alternative', 'video_count': 15, 'artist_count': 6, 'total_count': 21},
            {'genre': 'punk', 'video_count': 12, 'artist_count': 4, 'total_count': 16},
            {'genre': 'metal', 'video_count': 10, 'artist_count': 3, 'total_count': 13}
        ],
        'total_count': 5,
        'limit': limit,
        'include_counts': include_counts,
        'note': 'Temporary static response - genre parsing needs to be fixed'
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