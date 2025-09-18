#!/usr/bin/env python3

from src.database.connection import get_db
from src.database.models import Video

with get_db() as session:
    videos = session.query(Video).filter(Video.id.in_([284, 285, 286, 287, 288, 289, 290])).all()
    for video in videos:
        has_thumbnail = video.thumbnail_path and video.thumbnail_path.strip() and video.thumbnail_path != 'None'
        thumbnail_status = 'HAS THUMBNAIL' if has_thumbnail else 'NO THUMBNAIL'
        print(f'Video {video.id}: "{video.title}" - {thumbnail_status}')
        if has_thumbnail:
            print(f'  Path: {video.thumbnail_path}')