"""#607: the artist must be committed before enrichment/thumbnail work is queued,
otherwise the Celery worker's own session cannot see the row."""

from unittest.mock import MagicMock, patch

from src.services.artist_auto_processing_service import ArtistAutoProcessingService


def test_commits_before_enrichment_and_thumbnail():
    calls = []
    session = MagicMock()
    session.commit.side_effect = lambda: calls.append("commit")
    artist = MagicMock(id=3)
    artist.name = "Maphra"

    S = ArtistAutoProcessingService
    with patch.object(
        S, "_run_auto_match", return_value={"matches": {}, "match_count": 0}
    ), patch.object(
        S, "_run_metadata_enrichment", side_effect=lambda i: calls.append("enrich")
    ), patch.object(
        S, "_run_thumbnail_generation", side_effect=lambda i, n: calls.append("thumb")
    ):
        S.process_new_artist(artist, session)

    assert calls == ["commit", "enrich", "thumb"]


def test_commit_failure_does_not_queue_work():
    session = MagicMock()
    session.commit.side_effect = RuntimeError("db gone")
    artist = MagicMock(id=3)
    artist.name = "Maphra"
    S = ArtistAutoProcessingService
    with patch.object(
        S, "_run_auto_match", return_value={"matches": {}, "match_count": 0}
    ), patch.object(S, "_run_metadata_enrichment") as enrich:
        res = S.process_new_artist(artist, session)
    enrich.assert_not_called()
    assert res["errors"]
