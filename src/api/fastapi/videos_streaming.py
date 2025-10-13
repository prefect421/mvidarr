"""
FastAPI Videos Streaming API - Video Streaming and Subtitle Operations
Extracted from videos.py for better code organization

Handles:
- Video streaming with HTTP range support
- Subtitle discovery and serving
- File relocation detection
"""

import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.database.models import Video
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.utils.logger import get_logger

router = APIRouter(
    prefix="",
    tags=["videos-streaming"],
    responses={
        404: {"description": "Video or file not found"},
        500: {"description": "Internal server error"},
    },
)
logger = get_logger("mvidarr.api.fastapi.videos_streaming")


# ========================================================================================
# HELPER FUNCTIONS
# ========================================================================================


async def find_relocated_video(video: Video) -> Optional[Path]:
    """Find video file if it has been relocated"""
    if not getattr(video, "file_path", video.local_path):
        return None

    original_path = Path(getattr(video, "file_path", video.local_path))
    if original_path.exists():
        return original_path

    # Search for relocated file
    filename = original_path.name
    search_dirs = [
        Path("/data/musicvideos"),
        Path("/data/music_videos"),
        Path("data/musicvideos"),
        Path("data/music_videos"),
    ]

    for search_dir in search_dirs:
        if search_dir.exists():
            for file_path in search_dir.rglob(filename):
                if file_path.is_file():
                    logger.info(f"Found relocated video: {file_path}")
                    return file_path

    return None


# ========================================================================================
# VIDEO STREAMING ENDPOINTS
# ========================================================================================


@router.get("/{video_id}/stream")
@router.head("/{video_id}/stream")
async def stream_video(
    request: Request,
    video_id: int = FastAPIPath(..., ge=1),
    session: Session = Depends(get_db_session),
):
    """Stream video with HTTP range support"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Find the video file
        video_path = None
        if video.local_path and Path(video.local_path).exists():
            video_path = Path(video.local_path)
        else:
            # Try to find relocated file
            video_path = await find_relocated_video(video)

        if not video_path or not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Get file size
        file_size = video_path.stat().st_size

        # Handle range requests for video streaming
        range_header = request.headers.get("Range")

        if range_header:
            # Parse range header
            range_match = range_header.replace("bytes=", "").split("-")
            range_start = int(range_match[0]) if range_match[0] else 0
            range_end = int(range_match[1]) if range_match[1] else file_size - 1

            # Ensure valid range
            range_start = max(0, min(range_start, file_size - 1))
            range_end = max(range_start, min(range_end, file_size - 1))
            content_length = range_end - range_start + 1

            # Create streaming response for range
            def generate_range():
                with open(video_path, "rb") as f:
                    f.seek(range_start)
                    remaining = content_length
                    while remaining:
                        chunk_size = min(8192, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            # Get MIME type - handle common video formats explicitly
            # For MKV files, use MP4 MIME type to trick browsers into attempting playback
            # Most MKV files contain H.264/AAC which browsers can decode
            content_type, _ = mimetypes.guess_type(str(video_path))
            suffix = video_path.suffix.lower()

            if not content_type or suffix == ".mkv":
                # Explicit handling for common video formats
                if suffix == ".mkv":
                    # Serve MKV as MP4 MIME type - browsers can often decode the codecs
                    content_type = "video/mp4"
                elif suffix == ".webm":
                    content_type = "video/webm"
                elif suffix == ".avi":
                    content_type = "video/x-msvideo"
                elif suffix in [".mp4", ".m4v"]:
                    content_type = "video/mp4"
                elif suffix == ".mov":
                    content_type = "video/quicktime"
                else:
                    content_type = "video/mp4"  # Default fallback

            headers = {
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
            }

            return StreamingResponse(generate_range(), status_code=206, headers=headers)
        else:
            # Return full file - handle common video formats explicitly
            # For MKV files, use MP4 MIME type to trick browsers into attempting playback
            content_type, _ = mimetypes.guess_type(str(video_path))
            suffix = video_path.suffix.lower()

            if not content_type or suffix == ".mkv":
                # Explicit handling for common video formats
                if suffix == ".mkv":
                    # Serve MKV as MP4 MIME type - browsers can often decode the codecs
                    content_type = "video/mp4"
                elif suffix == ".webm":
                    content_type = "video/webm"
                elif suffix == ".avi":
                    content_type = "video/x-msvideo"
                elif suffix in [".mp4", ".m4v"]:
                    content_type = "video/mp4"
                elif suffix == ".mov":
                    content_type = "video/quicktime"
                else:
                    content_type = "video/mp4"  # Default fallback

            return FileResponse(
                video_path, media_type=content_type, filename=video_path.name
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# SUBTITLE OPERATIONS
# ========================================================================================


@router.get("/{video_id}/subtitles")
async def get_subtitles(
    video_id: int = FastAPIPath(..., description="Video ID"),
    session: Session = Depends(get_db_session),
):
    """Get available subtitle tracks for a video"""
    try:
        video = session.query(Video).filter(Video.id == video_id).first()

        if not video or not video.local_path:
            return {"subtitles": []}

        video_path = Path(video.local_path)
        if not video_path.exists():
            return {"subtitles": []}

        # Look for subtitle files in the same directory
        video_dir = video_path.parent
        video_name_stem = video_path.stem

        subtitle_extensions = [".srt", ".vtt", ".ass", ".ssa", ".sub"]
        subtitles = []

        # Look for all subtitle files in the directory and filter by base name
        for subtitle_file in video_dir.iterdir():
            if (
                subtitle_file.is_file()
                and subtitle_file.suffix.lower() in subtitle_extensions
            ):
                # Check if this subtitle file belongs to our video
                if subtitle_file.name.startswith(video_name_stem):
                    # Extract language from filename (e.g., video.en.srt -> en)
                    relative_name = subtitle_file.name
                    parts = relative_name.split(".")

                    language = "unknown"
                    if len(parts) >= 3:  # video.en.srt
                        language = parts[-2]
                    elif len(parts) == 2:  # video.srt (assume default language)
                        language = "default"

                    subtitles.append(
                        {
                            "language": language,
                            "filename": relative_name,
                            "url": f"/api/videos/{video_id}/subtitles/{quote(relative_name)}",
                            "format": subtitle_file.suffix[1:],  # Remove the dot
                        }
                    )

        return {"subtitles": subtitles}

    except Exception as e:
        logger.error(f"Failed to get subtitles for video {video_id}: {e}")
        return {"subtitles": []}


@router.get("/{video_id}/subtitles/{subtitle_filename}")
async def serve_subtitle(
    video_id: int = FastAPIPath(..., description="Video ID"),
    subtitle_filename: str = FastAPIPath(..., description="Subtitle filename"),
    session: Session = Depends(get_db_session),
):
    """Serve subtitle file for a video"""
    try:
        # URL decode the subtitle filename
        decoded_filename = unquote(subtitle_filename)

        video = session.query(Video).filter(Video.id == video_id).first()

        if not video or not video.local_path:
            raise HTTPException(status_code=404, detail="Video not found")

        video_path = Path(video.local_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        video_dir = video_path.parent

        # Security check: ensure subtitle filename doesn't contain path traversal
        if ".." in decoded_filename or "/" in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid subtitle filename")

        # Find subtitle file in the same directory as the video
        subtitle_path = video_dir / decoded_filename

        if not subtitle_path.exists():
            raise HTTPException(status_code=404, detail="Subtitle file not found")

        # Security check: ensure subtitle file is in the same directory as video
        if not str(subtitle_path).startswith(str(video_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        # Determine MIME type
        subtitle_ext = subtitle_path.suffix.lower()
        if subtitle_ext == ".srt":
            mimetype = "text/srt"
        elif subtitle_ext == ".vtt":
            mimetype = "text/vtt"
        elif subtitle_ext in [".ass", ".ssa"]:
            mimetype = "text/x-ssa"
        else:
            mimetype = "text/plain"

        # Return the subtitle file with CORS headers
        response = FileResponse(
            path=subtitle_path, media_type=mimetype, filename=decoded_filename
        )

        # Add CORS headers to allow video player to access subtitles
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET"
        response.headers["Access-Control-Allow-Headers"] = "*"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to serve subtitle {subtitle_filename} for video {video_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")
