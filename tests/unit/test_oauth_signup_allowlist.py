"""Tests for the OAuth new-account signup allowlist.

Before this: any Google/GitHub/Authentik account that could complete
that provider's consent screen got a brand-new MVidarr account
auto-created on the spot, with no allowlist or approval step — a real
gap for a self-hosted app confirmed live 2026-08-12 (two unintended
accounts self-registered during OAuth testing).

Design, per explicit decision: the allowlist gates only NEW account
creation. An OAuth login that matches an EXISTING user (by email or
username) is always allowed regardless of the allowlist — that account
was already created intentionally, not something this check needs to
second-guess. An unset/empty allowlist denies ALL new signups
(fail closed).
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import User, UserRole, UserSession
from src.services.oauth_service import OAuthService


class TestIsEmailAllowedForOAuthSignup:
    def test_empty_allowlist_denies_everything(self):
        with patch(
            "src.services.settings_service.SettingsService.get", return_value=""
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("anyone@example.com")
                is False
            )

    def test_exact_email_match_is_allowed(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="friend@example.com, other@example.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("friend@example.com")
                is True
            )

    def test_email_not_in_list_is_denied(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="friend@example.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("stranger@example.com")
                is False
            )

    def test_domain_wildcard_allows_any_address_at_that_domain(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="@mycompany.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("anyone@mycompany.com")
                is True
            )

    def test_domain_wildcard_does_not_match_a_different_domain(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="@mycompany.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("someone@evil.com")
                is False
            )

    def test_domain_wildcard_does_not_match_as_a_substring_of_a_longer_domain(self):
        """@mycompany.com must not match notmycompany.com — regression
        for the exact same class of bug as the role-mapping substring
        match (#349): must not use loose substring containment."""
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="@mycompany.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup(
                    "someone@notmycompany.com"
                )
                is False
            )

    def test_matching_is_case_insensitive(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="Friend@Example.com",
        ):
            assert (
                OAuthService._is_email_allowed_for_oauth_signup("friend@example.com")
                is True
            )

    def test_none_email_is_denied(self):
        with patch(
            "src.services.settings_service.SettingsService.get",
            return_value="@mycompany.com",
        ):
            assert OAuthService._is_email_allowed_for_oauth_signup(None) is False


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, UserSession.__table__])
    return sessionmaker(bind=engine)


@contextmanager
def _real_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _patch_get_db(session_factory):
    return patch(
        "src.services.oauth_service.get_db",
        lambda: _real_get_db(session_factory),
    )


class TestFindOrCreateOAuthUserRespectsAllowlist:
    def test_denies_new_account_for_email_not_on_allowlist(self, session_factory):
        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory), patch(
            "src.services.settings_service.SettingsService.get",
            return_value="",
        ):
            user, user_session = service._find_or_create_oauth_user(
                "google",
                {"email": "uninvited@example.com", "id": "provider-id"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user is None
        assert user_session is None

        session = session_factory()
        assert (
            session.query(User).filter_by(email="uninvited@example.com").first() is None
        )
        session.close()

    def test_creates_new_account_for_email_on_allowlist(self, session_factory):
        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory), patch(
            "src.services.settings_service.SettingsService.get",
            return_value="invited@example.com",
        ), patch(
            "src.services.oauth_service.secrets.token_urlsafe",
            return_value="Xk9#mQ7z!vR2wL",
        ):
            user, user_session = service._find_or_create_oauth_user(
                "google",
                {"email": "invited@example.com", "id": "provider-id"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user is not None
        assert user.email == "invited@example.com"

    def test_existing_user_can_still_log_in_regardless_of_allowlist(
        self, session_factory
    ):
        session = session_factory()
        existing = User(
            username="alreadyhere",
            email="alreadyhere@example.com",
            password="Sup3rSecret!",
            role=UserRole.USER,
        )
        session.add(existing)
        session.commit()
        session.close()

        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory), patch(
            "src.services.settings_service.SettingsService.get",
            return_value="",
        ):
            user, user_session = service._find_or_create_oauth_user(
                "google",
                {"email": "alreadyhere@example.com", "id": "provider-id"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user is not None
        assert user.username == "alreadyhere"
