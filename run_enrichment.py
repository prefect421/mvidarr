#!/usr/bin/env python3
"""
Run metadata enrichment for artists with videos missing year data
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services.metadata_enrichment_service import MetadataEnrichmentService

async def main():
    enrichment_service = MetadataEnrichmentService()

    # Get artists with videos missing year
    with get_db() as session:
        videos_without_year = session.query(Video).filter(
            Video.year.is_(None)
        ).all()

        artist_ids = sorted(list(set([v.artist_id for v in videos_without_year if v.artist_id])))

        artists = session.query(Artist).filter(Artist.id.in_(artist_ids)).all()
        artist_data = [(a.id, a.name) for a in artists]

    total = len(artist_data)
    print(f'Starting metadata enrichment for {total} artists with missing year data')
    print('=' * 70)

    for i, (artist_id, artist_name) in enumerate(artist_data, 1):
        print(f'\n[{i}/{total}] Enriching {artist_name}...')

        try:
            # Use a new session for each artist
            with get_db() as artist_session:
                # Run enrichment
                result = await enrichment_service.enrich_artist_metadata(
                    artist_id=artist_id,
                    force_refresh=True,
                    session=artist_session
                )

                artist_session.commit()

                if result.success:
                    print(f'  ✅ Completed successfully')
                else:
                    print(f'  ⚠️  Completed with issues')

        except Exception as e:
            print(f'  ❌ Error: {e}')
            continue

    print('\n' + '=' * 70)
    print('Enrichment complete! Checking results...')

    # Check how many videos still lack year data
    with get_db() as check_session:
        remaining_without_year = check_session.query(Video).filter(
            Video.year.is_(None)
        ).count()

        total_videos = check_session.query(Video).count()
        videos_with_year = total_videos - remaining_without_year
        percentage = (videos_with_year / total_videos * 100) if total_videos > 0 else 0

        print(f'\nFinal Statistics:')
        print(f'  Total videos: {total_videos}')
        print(f'  Videos with year: {videos_with_year} ({percentage:.1f}%)')
        print(f'  Videos without year: {remaining_without_year}')

if __name__ == "__main__":
    asyncio.run(main())
