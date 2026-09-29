"""
Focused test for a real bug found while updating enrichment.html's UI copy
during #527 (IMVDb removal, Phase 4): get_enrichment_stats()'s
external_id_coverage averaged with_imvdb into a 4-service denominator
(spotify, lastfm, imvdb, musicbrainz). Since imvdb_id is never populated
again (#524/#525), that permanently deflated every artist's coverage
score by counting an unfillable field -- the same bug class as the
Python imvdb_id-IS-NULL trigger-condition fixes from #524/#525 and the
frontend calculateDataCompleteness() fix in artist_detail.html, just the
enrichment-stats equivalent.
"""

from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.connection import Base
from src.database.models import Artist
from src.services.metadata_enrichment_service import MetadataEnrichmentService


def _make_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Artist.__table__])
    return sessionmaker(bind=engine)


class TestExternalIdCoverageExcludesImvdb:
    def test_fully_enriched_artist_missing_only_imvdb_id_scores_100_percent(self):
        session_factory = _make_session_factory()
        session = session_factory()
        session.add(
            Artist(
                name="Fully Enriched",
                spotify_id="sp1",
                lastfm_name="lf1",
                imvdb_id=None,
                imvdb_metadata={"musicbrainz_id": "mb1"},
            )
        )
        session.commit()
        session.close()

        @contextmanager
        def fake_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        service = MetadataEnrichmentService()
        with patch("src.services.metadata_enrichment_service.get_db", fake_get_db):
            stats = service.get_enrichment_stats()

        # Before the fix: (1 + 1 + 0 + 1) / (1 * 4) * 100 == 75.0
        # After the fix: (1 + 1 + 1) / (1 * 3) * 100 == 100.0
        assert stats["external_id_coverage"] == 100.0
        # Per-service breakdown still accurately reports imvdb at 0%,
        # per this migration's "accurate historical reporting stays" rule.
        assert stats["external_id_breakdown"]["imvdb"] == 0.0
