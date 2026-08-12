"""Tests for the "admin only" OAuth access policy (explicit product
decision, 2026-08-12): granular roles (USER/MANAGER/READONLY) aren't
well-defined enough yet in this app to safely auto-assign via OAuth.
Anyone trusted enough to pass the oauth_allowed_emails allowlist is
trusted enough to be a full admin — deferred, tiered self-service access
to a later version.

Also removes the per-login Authentik group-to-role sync for EXISTING
users entirely — that exact mechanism (re-evaluating and overwriting an
existing user's role on every login based on current Authentik group
membership) was the live mechanism behind the privilege-escalation
incident fixed in #349, and directly conflicts with "admin only until
proper RBAC exists": role changes for existing accounts should only
happen deliberately, via /admin/users, not silently on next login.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import User, UserRole, UserSession
from src.services.oauth_service import AuthentikProvider, OAuthService


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


def _allow_signup():
    return patch(
        "src.services.oauth_service.OAuthService._is_email_allowed_for_oauth_signup",
        return_value=True,
    )


def _pin_password():
    return patch(
        "src.services.oauth_service.secrets.token_urlsafe",
        return_value="Xk9#mQ7z!vR2wL",
    )


class TestNewOAuthAccountsAlwaysGetAdmin:
    def test_new_google_account_gets_admin(self, session_factory):
        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory), _allow_signup(), _pin_password():
            user, _ = service._find_or_create_oauth_user(
                "google",
                {"email": "newperson@example.test", "id": "id-1"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user.role == UserRole.ADMIN

    def test_new_github_account_gets_admin(self, session_factory):
        service = OAuthService.__new__(OAuthService)

        with _patch_get_db(session_factory), _allow_signup(), _pin_password():
            user, _ = service._find_or_create_oauth_user(
                "github",
                {"email": "newperson2@example.test", "id": "id-2"},
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user.role == UserRole.ADMIN

    def test_new_authentik_account_gets_admin_even_with_no_groups(
        self, session_factory
    ):
        """The old behavior defaulted a group-less Authentik user to
        READONLY via map_groups_to_role. Admin-only policy means new
        accounts get ADMIN regardless of Authentik group membership."""
        service = OAuthService.__new__(OAuthService)
        service.providers = {
            "authentik": AuthentikProvider(
                {
                    "client_id": "id",
                    "client_secret": "secret",
                    "redirect_uri": "https://example.test/callback",
                    "base_url": "https://auth.example.test",
                }
            )
        }

        with _patch_get_db(session_factory), _allow_signup(), _pin_password():
            user, _ = service._find_or_create_oauth_user(
                "authentik",
                {
                    "email": "newperson3@example.test",
                    "id": "id-3",
                    "groups": [],
                    "roles": [],
                },
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user.role == UserRole.ADMIN


class TestExistingUserRoleIsNeverAutoChangedOnLogin:
    def test_authentik_login_does_not_promote_an_existing_user(self, session_factory):
        """Regression pin for the exact live incident (#349): even with
        the substring-match bug fixed, an exact-match Authentik group
        must not silently change an existing account's role on login —
        that decision belongs to /admin/users only."""
        session = session_factory()
        existing = User(
            username="alreadyhere",
            email="alreadyhere@example.test",
            password="Sup3rSecret!",
            role=UserRole.USER,
        )
        session.add(existing)
        session.commit()
        session.close()

        service = OAuthService.__new__(OAuthService)
        service.providers = {
            "authentik": AuthentikProvider(
                {
                    "client_id": "id",
                    "client_secret": "secret",
                    "redirect_uri": "https://example.test/callback",
                    "base_url": "https://auth.example.test",
                }
            )
        }

        with _patch_get_db(session_factory):
            user, _ = service._find_or_create_oauth_user(
                "authentik",
                {
                    "email": "alreadyhere@example.test",
                    "id": "id-4",
                    "groups": ["admins"],
                    "roles": [],
                },
                ip_address="203.0.113.5",
                user_agent="TestAgent/1.0",
            )

        assert user.role == UserRole.USER
