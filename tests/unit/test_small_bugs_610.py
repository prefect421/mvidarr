"""#610: health check SELECT 1, YouTube test endpoint errors, stale empty API key."""

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_scheduler_health_check_sees_the_database():
    from src.tasks import scheduled_tasks

    engine = create_engine("sqlite://")

    @contextmanager
    def fake_get_db():
        with Session(engine) as s:
            yield s

    with patch.object(scheduled_tasks, "get_db", fake_get_db), patch.object(
        scheduled_tasks, "celery_app", MagicMock()
    ):
        result = scheduled_tasks.scheduler_health_check_task.run()

    assert result["database_connected"] is True
    assert result["status"] != "unhealthy"


def test_youtube_test_endpoint_returns_400_when_key_missing():
    from src.api.fastapi import youtube_playlists as yp

    with patch.object(
        type(yp.youtube_playlist_service),
        "api_key",
        new_callable=PropertyMock,
        return_value="",
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(yp.test_youtube_integration(current_user={}, session=None))
    assert exc.value.status_code == 400


def test_empty_api_key_is_not_cached():
    from src.services import youtube_playlist_service as yps

    svc = yps.YouTubePlaylistService()
    with patch.object(yps.settings, "get", side_effect=["", "NEWKEY"]):
        assert not svc.api_key
        assert svc.api_key == "NEWKEY"  # picked up without a restart
