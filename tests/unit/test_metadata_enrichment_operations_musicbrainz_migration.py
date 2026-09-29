"""
Focused tests for the IMVDb -> MusicBrainz migration of
src/api/fastapi/metadata_enrichment_operations.py (Phase 2 of the IMVDb
removal plan, GitHub issue #525).

auto_match_services() and its bulk-path helper _auto_match_artist() both
had an "IMVDb auto-match" block calling imvdb_service.search_artist() to
backfill Artist.imvdb_id -- no MusicBrainz equivalent for this
artist-level lookup exists (same reasoning already applied elsewhere in
#524/#525), so both are removed outright rather than migrated.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.api.fastapi.metadata_enrichment_operations import _auto_match_artist


def _make_artist():
    return SimpleNamespace(
        id=1,
        name="Ghost",
        spotify_id="sp1",
        lastfm_name="lf1",
        imvdb_id=None,
        imvdb_metadata=None,
    )


class TestAutoMatchArtistImvdbRemoved:
    @pytest.mark.asyncio
    async def test_no_imvdb_key_and_imvdb_id_never_touched(self):
        artist = _make_artist()

        with patch(
            "src.api.fastapi.metadata_enrichment_operations.get_async_spotify_service",
            None,
        ), patch(
            "src.api.fastapi.metadata_enrichment_operations.lastfm_service", None
        ), patch(
            "src.api.fastapi.metadata_enrichment_operations.musicbrainz_service", None
        ):
            matches_found = await _auto_match_artist(artist, session=None)

        assert "imvdb" not in matches_found
        assert artist.imvdb_id is None
