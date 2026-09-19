"""Tests for playlist read-path access control (#509).

#500 fixed the write paths; get_playlists / get_playlist still exposed every
user's playlists to any authenticated user. These call the route functions
directly against an in-memory SQLite session.
"""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.fastapi.playlists_auth import UserInfo
from src.api.fastapi.playlists_crud import get_playlist, get_playlists
from src.database.connection import Base
from src.database.models import (
    Playlist,
    PlaylistEntry,
    PlaylistType,
    User,
    UserRole,
    Video,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Playlist.__table__,
            PlaylistEntry.__table__,
            Video.__table__,
        ],
    )
    s = sessionmaker(bind=engine, autoflush=False)()
    for uid, name, role in (
        (1, "alice", UserRole.USER),
        (2, "bob", UserRole.USER),
        (3, "root", UserRole.ADMIN),
    ):
        user = User(
            username=name,
            email=f"{name}@example.com",
            password="Zq7!vLm2$Xk9#Rt4",
            role=role,
        )
        user.id = uid
        s.add(user)
    for pid, owner, public in (
        (10, 1, False),  # alice private
        (11, 1, True),  # alice public
        (20, 2, False),  # bob private
    ):
        playlist = Playlist(
            name=f"pl{pid}",
            user_id=owner,
            is_public=public,
            playlist_type=PlaylistType.STATIC,
        )
        playlist.id = pid
        s.add(playlist)
    s.commit()
    yield s
    s.close()


def _user(uid, name, role):
    return UserInfo(id=uid, username=name, role=role.value)


def _list_ids(session, user):
    result = asyncio.run(
        get_playlists(page=1, per_page=50, current_user=user, session=session)
    )
    return {p["id"] for p in result["playlists"]}, result["pagination"]["total"]


class TestGetPlaylistsListing:
    def test_user_sees_own_and_public_only(self, session):
        ids, total = _list_ids(session, _user(1, "alice", UserRole.USER))
        assert ids == {10, 11}
        assert total == 2

    def test_other_users_private_playlist_hidden(self, session):
        ids, _ = _list_ids(session, _user(2, "bob", UserRole.USER))
        assert ids == {11, 20}  # alice's public + own, not alice's private (10)

    def test_admin_sees_everything(self, session):
        ids, total = _list_ids(session, _user(3, "root", UserRole.ADMIN))
        assert ids == {10, 11, 20}
        assert total == 3


class TestGetPlaylistSingle:
    def _get(self, session, user, pid):
        return asyncio.run(
            get_playlist(
                request=None,
                playlist_id=pid,
                include_entries=False,
                current_user=user,
                session=session,
            )
        )

    def test_owner_can_read_private(self, session):
        assert self._get(session, _user(1, "alice", UserRole.USER), 10)["success"]

    def test_non_owner_gets_404_on_private(self, session):
        with pytest.raises(HTTPException) as exc:
            self._get(session, _user(2, "bob", UserRole.USER), 10)
        assert exc.value.status_code == 404

    def test_non_owner_can_read_public(self, session):
        assert self._get(session, _user(2, "bob", UserRole.USER), 11)["success"]

    def test_admin_can_read_any(self, session):
        assert self._get(session, _user(3, "root", UserRole.ADMIN), 20)["success"]
