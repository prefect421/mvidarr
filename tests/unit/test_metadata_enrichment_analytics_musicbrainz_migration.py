"""
Focused tests for the IMVDb -> MusicBrainz migration of
src/api/fastapi/metadata_enrichment_analytics.py (Phase 2 of the IMVDb
removal plan, GitHub issue #525).

get_enrichment_candidates()'s "missing_external_ids" filter OR'd in
Artist.imvdb_id.is_(None) -- since imvdb_id is never populated again, that
arm was permanently true for every artist, the same trigger-condition bug
class already fixed in wizard_tasks.py/performance_optimizations.py and
metadata_enrichment_service.py during #524.

enrich_single_artist()'s IMVDb enrichment block (imvdb_service.search_artist)
is removed with no replacement -- same "no MusicBrainz equivalent for
artist-level lookup" reasoning used elsewhere in #524/#525.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.metadata_enrichment_analytics import (
    enrich_single_artist,
    get_enrichment_candidates,
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


class TestEnrichmentCandidatesTriggerCondition:
    @pytest.mark.asyncio
    async def test_fully_enriched_artist_missing_only_imvdb_id_is_not_a_candidate(
        self, session
    ):
        fully_enriched = Artist(
            name="Fully Enriched", spotify_id="sp1", lastfm_name="lf1", imvdb_id=None
        )
        needs_enrichment = Artist(
            name="Needs Enrichment", spotify_id=None, lastfm_name=None, imvdb_id=None
        )
        session.add_all([fully_enriched, needs_enrichment])
        session.commit()

        result = await get_enrichment_candidates(
            limit=50,
            offset=0,
            missing_external_ids=True,
            current_user={"user_id": 1},
            session=session,
        )

        names = {c["name"] for c in result["candidates"]}
        assert names == {"Needs Enrichment"}
        assert "imvdb_id" not in result["candidates"][0]["missing_external_ids"]


class TestEnrichSingleArtistImvdbRemoved:
    @pytest.mark.asyncio
    async def test_no_imvdb_key_in_matches_found(self, session):
        artist = Artist(name="Ghost", spotify_id="sp1", lastfm_name="lf1")
        session.add(artist)
        session.commit()

        with patch(
            "src.api.fastapi.metadata_enrichment_analytics.musicbrainz_service", None
        ):
            result = await enrich_single_artist(
                artist_id=artist.id,
                current_user={"user_id": 1},
                session=session,
            )

        assert "imvdb" not in result["matches_found"]
