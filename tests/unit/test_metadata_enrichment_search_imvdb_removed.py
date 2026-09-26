"""
Regression test for the IMVDb removal from
src/api/fastapi/metadata_enrichment_search.py (Phase 2 of the IMVDb
removal plan, GitHub issue #525).

This file already had a working musicbrainz_service.search_artist
endpoint alongside the imvdb_service.search_artist one -- per the plan,
the IMVDb one is simply deleted, no replacement needed.
"""

from src.api.fastapi.metadata_enrichment_search import router


def test_no_imvdb_search_route_remains():
    paths = {route.path for route in router.routes}
    assert "/search/imvdb" not in paths
    assert "/search/musicbrainz" in paths
