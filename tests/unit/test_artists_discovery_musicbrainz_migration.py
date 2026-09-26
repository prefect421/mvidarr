"""
Focused tests for the IMVDb -> MusicBrainz migration of
src/api/fastapi/artists_discovery.py (Phase 2 of the IMVDb removal plan,
GitHub issue #525).

Three IMVDb-only endpoints (GET /discover, POST /import-from-imvdb, GET
/preview/{imvdb_id}) had no MusicBrainz equivalent worth building -- same
"no 1:1 replacement" reasoning already applied to artist-level bulk
discovery elsewhere in #524/#525 -- and were deleted outright rather than
migrated, consistent with the full-removal decision for IMVDb (not just
the broken search path).

discover_artist_videos() combined IMVDb + YouTube results; the IMVDb half
is removed (MusicBrainz's find_official_video() needs a known track, it
can't do from-scratch artist-level discovery), YouTube search remains the
sole discovery source.

bulk_auto_process_artists()'s "needs processing" filter OR'd in
Artist.imvdb_id.is_(None) -- since imvdb_id is never populated again, that
arm was permanently true for every artist, the same trigger-condition bug
class already fixed in wizard_tasks.py/performance_optimizations.py during
#524.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.artists_discovery import (
    bulk_auto_process_artists,
    discover_artist_videos,
    router,
)
from src.database.connection import Base
from src.database.models import Artist, Video


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Artist.__table__, Video.__table__])
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


class TestImvdbOnlyEndpointsRemoved:
    def test_no_imvdb_only_routes_remain(self):
        paths = {route.path for route in router.routes}
        assert "/discover" not in paths
        assert "/import-from-imvdb" not in paths
        assert "/preview/{imvdb_id}" not in paths


class TestDiscoverArtistVideosYoutubeOnly:
    @pytest.mark.asyncio
    async def test_returns_only_youtube_sourced_videos(self, session):
        artist = Artist(name="Ghost", imvdb_id=None)
        session.add(artist)
        session.commit()

        youtube_response = {
            "videos": [
                {
                    "youtube_id": "abc123",
                    "title": "Rats",
                    "upload_year": 2018,
                    "duration": 240,
                    "thumbnail_url": "https://img.example/abc123.jpg",
                    "view_count": 1000,
                    "channel_title": "Ghost",
                }
            ]
        }

        with patch(
            "src.api.fastapi.artists_discovery.youtube_search_service.search_artist_videos",
            return_value=youtube_response,
        ) as mock_youtube:
            result = await discover_artist_videos(
                artist_id=artist.id,
                request={},
                current_user={"user_id": 1},
                session=session,
            )

        mock_youtube.assert_called_once()
        assert result["success"] is True
        assert len(result["discovered_videos"]) == 1
        video = result["discovered_videos"][0]
        assert video["source"] == "youtube"
        assert video["youtube_id"] == "abc123"
        assert "imvdb_id" not in video
        assert "imvdb_results" not in result["stats"]


class TestBulkAutoProcessArtistsTriggerCondition:
    @pytest.mark.asyncio
    async def test_fully_enriched_artist_missing_only_imvdb_id_is_not_reselected(
        self, session
    ):
        fully_enriched = Artist(
            name="Fully Enriched",
            imvdb_id=None,
            spotify_id="sp1",
            lastfm_name="lf1",
            musicbrainz_id="mb1",
            biography="bio",
            thumbnail_url="https://example/thumb.jpg",
        )
        needs_processing = Artist(
            name="Needs Processing",
            imvdb_id=None,
            spotify_id=None,
            lastfm_name=None,
            musicbrainz_id=None,
            biography=None,
            thumbnail_url=None,
        )
        session.add_all([fully_enriched, needs_processing])
        session.commit()

        with patch(
            "src.services.artist_auto_processing_service.ArtistAutoProcessingService._run_auto_match",
            return_value={"match_count": 0},
        ), patch(
            "src.jobs.metadata_tasks.enrich_artist_metadata_task.delay",
            return_value=MagicMock(id="task-1"),
        ):
            result = await bulk_auto_process_artists(
                force_refresh=False,
                current_user={"user_id": 1},
                session=session,
            )

        processed_names = {r["artist_name"] for r in result["results"]}
        assert processed_names == {"Needs Processing"}
