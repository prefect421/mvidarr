"""Regression test for an IDOR/authorization gap in themes.py, flagged by
background security review right after #392 Phase 2 follow-up PR #429
added the missing require_authentication baseline to delete_theme and
export_all_themes -- but neither route actually checked *whose* theme it
was touching.

CustomTheme already carries created_by and is_public columns, and
get_theme()/get_themes() already establish the intended ownership model
(a user can see their own themes, public themes, and built-in themes) --
delete_theme and export_all_themes just never applied it:

- delete_theme let ANY authenticated user delete ANY other user's custom
  theme, public or private (broken authorization / IDOR).
- export_all_themes returned every custom theme in the system, including
  other users' private (non-public) themes (information disclosure via
  IDOR).

Fix:
- delete_theme now 404s for another user's private theme (matching
  get_theme's own not-found-for-invisible-theme behavior -- doesn't
  confirm whether a private theme id even exists) and 403s for another
  user's public theme (the theme's existence is already visible via
  GET /api/themes, so a 403 here doesn't leak anything new; it just says
  "yes, but you can't delete this one").
- export_all_themes now only includes the caller's own themes plus
  public ones, matching get_themes()'s existing filter.
"""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.fastapi.themes import delete_theme, export_all_themes
from src.database.connection import Base
from src.database.models import CustomTheme


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomTheme.__table__])
    return sessionmaker(bind=engine)


def _seed_theme(session_factory, *, created_by, is_public=False, is_built_in=False):
    session = session_factory()
    theme = CustomTheme(
        name=f"theme-{created_by}-{is_public}-{is_built_in}",
        display_name="Test Theme",
        created_by=created_by,
        is_public=is_public,
        is_built_in=is_built_in,
        theme_data={"--color": "#000"},
    )
    session.add(theme)
    session.commit()
    theme_id = theme.id
    session.close()
    return theme_id


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class TestDeleteThemeOwnership:
    def test_owner_can_delete_their_own_private_theme(self, session_factory):
        theme_id = _seed_theme(session_factory, created_by=1, is_public=False)
        session = session_factory()

        result = _run(
            delete_theme(
                theme_id=theme_id,
                db=session,
                current_user={"user_id": 1, "username": "owner"},
            )
        )

        assert result["success"] is True
        assert session.query(CustomTheme).filter_by(id=theme_id).first() is None

    def test_non_owner_cannot_delete_someone_elses_private_theme(self, session_factory):
        theme_id = _seed_theme(session_factory, created_by=1, is_public=False)
        session = session_factory()

        with pytest.raises(HTTPException) as exc_info:
            _run(
                delete_theme(
                    theme_id=theme_id,
                    db=session,
                    current_user={"user_id": 2, "username": "attacker"},
                )
            )

        # Doesn't confirm whether a private theme id even exists --
        # matches get_theme()'s own not-found-for-invisible-theme
        # behavior.
        assert exc_info.value.status_code == 404
        assert session.query(CustomTheme).filter_by(id=theme_id).first() is not None

    def test_non_owner_cannot_delete_someone_elses_public_theme(self, session_factory):
        theme_id = _seed_theme(session_factory, created_by=1, is_public=True)
        session = session_factory()

        with pytest.raises(HTTPException) as exc_info:
            _run(
                delete_theme(
                    theme_id=theme_id,
                    db=session,
                    current_user={"user_id": 2, "username": "attacker"},
                )
            )

        # A public theme's existence is already visible via GET
        # /api/themes, so 403 (as opposed to 404) doesn't leak anything
        # new here.
        assert exc_info.value.status_code == 403
        assert session.query(CustomTheme).filter_by(id=theme_id).first() is not None

    def test_built_in_theme_still_blocked_regardless_of_owner(self, session_factory):
        # Regression guard: the pre-existing is_built_in check must keep
        # working even for the theme's own creator.
        theme_id = _seed_theme(
            session_factory, created_by=1, is_public=True, is_built_in=True
        )
        session = session_factory()

        with pytest.raises(HTTPException) as exc_info:
            _run(
                delete_theme(
                    theme_id=theme_id,
                    db=session,
                    current_user={"user_id": 1, "username": "owner"},
                )
            )

        assert exc_info.value.status_code == 403
        assert "built-in" in exc_info.value.detail.lower()


class TestExportAllThemesOwnership:
    def test_export_includes_own_and_public_themes_only(self, session_factory):
        own_theme_id = _seed_theme(session_factory, created_by=1, is_public=False)
        public_theme_id = _seed_theme(session_factory, created_by=2, is_public=True)
        other_private_theme_id = _seed_theme(
            session_factory, created_by=2, is_public=False
        )
        session = session_factory()

        response = _run(
            export_all_themes(
                db=session,
                current_user={"user_id": 1, "username": "owner"},
            )
        )
        result = json.loads(response.body)

        exported_names = {t["name"] for t in result["themes"]}
        session2 = session_factory()
        own_name = session2.query(CustomTheme).filter_by(id=own_theme_id).first().name
        public_name = (
            session2.query(CustomTheme).filter_by(id=public_theme_id).first().name
        )
        other_private_name = (
            session2.query(CustomTheme)
            .filter_by(id=other_private_theme_id)
            .first()
            .name
        )

        assert own_name in exported_names
        assert public_name in exported_names
        assert other_private_name not in exported_names
