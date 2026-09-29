"""Regression tests for #545: universal_search() must search for what the
user typed.

Previously the whole query was matched as one substring against
Video.title OR Artist.name, so a multi-word query spanning both ("artist
song") matched nothing; `%`/`_` typed by the user acted as SQL wildcards;
and the query was lowercased before being forwarded to YouTube.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.videos_search import universal_search
from src.database.connection import Base
from src.database.models import Artist, Video, VideoStatus


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Artist.__table__, Video.__table__])
    session = sessionmaker(bind=engine)()

    led = Artist(name="Led Zeppelin")
    other = Artist(name="Other Band")
    session.add_all([led, other])
    session.commit()
    session.add_all(
        [
            Video(
                artist_id=led.id,
                title="Whole Lotta Love",
                status=VideoStatus.WANTED,
                url="https://youtube.com/watch?v=a1",
            ),
            Video(
                artist_id=other.id,
                title="100% Pure_Gold",
                status=VideoStatus.WANTED,
                url="https://youtube.com/watch?v=a2",
            ),
            Video(
                artist_id=other.id,
                title="1000 Pure Gold",
                status=VideoStatus.WANTED,
                url="https://youtube.com/watch?v=a3",
            ),
        ]
    )
    session.commit()
    yield session
    session.close()


async def _search(session, q):
    with patch(
        "src.services.youtube_search_service.youtube_search_service"
    ) as mock_youtube:
        mock_youtube.api_key = None
        return await universal_search(
            q=q, extended=False, current_user={"user_id": 1}, session=session
        )


def _titles(result):
    return sorted(v["title"] for v in result["videos"])


class TestLocalSearchTerms:
    @pytest.mark.asyncio
    async def test_terms_split_across_artist_and_title_match(self, session):
        result = await _search(session, "led zeppelin whole lotta love")
        assert _titles(result) == ["Whole Lotta Love"]

    @pytest.mark.asyncio
    async def test_term_order_does_not_matter(self, session):
        result = await _search(session, "love whole")
        assert _titles(result) == ["Whole Lotta Love"]

    @pytest.mark.asyncio
    async def test_punctuation_only_tokens_are_ignored(self, session):
        result = await _search(session, "Led Zeppelin - Whole Lotta Love")
        assert _titles(result) == ["Whole Lotta Love"]

    @pytest.mark.asyncio
    async def test_every_term_must_match(self, session):
        result = await _search(session, "led zeppelin nonexistentword")
        assert result["videos"] == []

    @pytest.mark.asyncio
    async def test_percent_is_literal_not_wildcard(self, session):
        result = await _search(session, "100%")
        assert _titles(result) == ["100% Pure_Gold"]

    @pytest.mark.asyncio
    async def test_underscore_is_literal_not_wildcard(self, session):
        result = await _search(session, "pure_gold")
        assert _titles(result) == ["100% Pure_Gold"]

    @pytest.mark.asyncio
    async def test_artist_results_match_multiword_artist_name(self, session):
        result = await _search(session, "led zepp")
        assert [a["name"] for a in result["artists"]] == ["Led Zeppelin"]


class TestQueryForwardedAsTyped:
    @pytest.mark.asyncio
    async def test_youtube_receives_original_casing(self, session):
        with patch(
            "src.services.youtube_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_youtube.api_key = "fake-key"
            mock_youtube.search_videos_as_typed.return_value = {"videos": []}

            await universal_search(
                q="AC/DC Back In Black",
                extended=False,
                current_user={"user_id": 1},
                session=session,
            )

        assert mock_youtube.search_videos_as_typed.call_args.args[0] == (
            "AC/DC Back In Black"
        )


class TestExternalSearchWarnings:
    """A YouTube failure must be reported, not shown as "no results"."""

    async def _search_with_youtube(self, session, youtube_result):
        with patch(
            "src.services.youtube_search_service.youtube_search_service"
        ) as mock_youtube:
            mock_youtube.api_key = "fake-key"
            mock_youtube.search_videos_as_typed.return_value = youtube_result
            return await universal_search(
                q="moon", extended=False, current_user={"user_id": 1}, session=session
            )

    @pytest.mark.asyncio
    async def test_quota_error_becomes_friendly_warning(self, session):
        result = await self._search_with_youtube(
            session,
            {
                "videos": [],
                "error": "429 Client Error: Too Many Requests for url: https://x",
            },
        )
        assert len(result["warnings"]) == 1
        assert "quota" in result["warnings"][0].lower()
        assert "https://" not in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_quota_exhausted_message_becomes_warning(self, session):
        result = await self._search_with_youtube(
            session,
            {"videos": [], "error": "YouTube API quota exhausted for today"},
        )
        assert "quota" in result["warnings"][0].lower()

    @pytest.mark.asyncio
    async def test_other_error_becomes_generic_warning(self, session):
        result = await self._search_with_youtube(
            session, {"videos": [], "error": "boom"}
        )
        assert result["warnings"] == ["YouTube search failed; see server logs."]

    @pytest.mark.asyncio
    async def test_missing_api_key_becomes_warning(self, session):
        result = await _search(session, "moon")
        assert any("api key" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_no_warning_when_youtube_returns_no_matches_cleanly(self, session):
        result = await self._search_with_youtube(session, {"videos": []})
        assert result["warnings"] == []
