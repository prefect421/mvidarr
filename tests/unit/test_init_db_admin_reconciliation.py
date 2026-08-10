"""Tests for the startup reconciliation that guarantees the configured
simple_auth_username has a matching ADMIN User row.

Without it, installs that finished (or skipped) the installation wizard
before this reconciliation existed have only Setting rows, so
SessionStore.create_session finds no user, fails closed to READONLY, and the
site's only admin account 403s on every admin endpoint.

The reconciliation must NOT run while the installation wizard is still
pending: seeding an ADMIN row on a fresh install makes the wizard's
POST /api/wizard/create-admin reject setup with "Admin user already exists".
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.init_db import ensure_admin_user_for_credentials
from src.database.models import (
    User,
    UserRole,
    WizardState,
    WizardStatus,
    WizardStep,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, WizardState.__table__])
    return sessionmaker(bind=engine)


def _seed_wizard_state(session_factory, status):
    """Put the install past (or inside) first-run setup."""
    session = session_factory()
    session.add(WizardState(status=status, current_step=WizardStep.COMPLETE))
    session.commit()
    session.close()


@pytest.fixture
def completed_install(session_factory):
    """A live install: the wizard has been completed."""
    _seed_wizard_state(session_factory, WizardStatus.COMPLETED)
    return session_factory


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    return patch(
        "src.database.connection.get_db", lambda: _fake_get_db(session_factory)
    )


def _seed_user(session_factory, username, role, password="Sup3rSecret!"):
    session = session_factory()
    user = User(
        username=username,
        email=f"{username}@test.local",
        password=password,
        role=role,
    )
    session.add(user)
    session.commit()
    session.close()


@pytest.mark.usefixtures("completed_install")
class TestEnsureAdminUserForCredentials:
    """Behaviour on a live install (wizard already completed)."""

    def test_creates_admin_user_when_missing(self, session_factory):
        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session = session_factory()
        users = session.query(User).filter(User.username == "admin").all()
        assert len(users) == 1
        assert users[0].role == UserRole.ADMIN
        assert users[0].email == "admin@localhost"
        # Password hash is a real hash of an unusable random secret, never blank.
        assert users[0].password_hash

    def test_leaves_existing_admin_untouched(self, session_factory):
        _seed_user(session_factory, "admin", UserRole.ADMIN)
        session = session_factory()
        original = session.query(User).filter(User.username == "admin").first()
        original_hash = original.password_hash
        original_email = original.email
        original_id = original.id
        session.close()

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session2 = session_factory()
        users = session2.query(User).filter(User.username == "admin").all()
        assert len(users) == 1, "must not duplicate the existing row"
        assert users[0].id == original_id
        assert users[0].password_hash == original_hash, "must not overwrite password"
        assert users[0].email == original_email
        assert users[0].role == UserRole.ADMIN

    def test_does_not_overwrite_a_deliberately_downgraded_account(
        self, session_factory
    ):
        _seed_user(session_factory, "admin", UserRole.READONLY)

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session = session_factory()
        user = session.query(User).filter(User.username == "admin").first()
        assert user.role == UserRole.READONLY

    def test_is_idempotent_across_repeated_boots(self, session_factory):
        with _patch_get_db(session_factory):
            ensure_admin_user_for_credentials("admin")
            ensure_admin_user_for_credentials("admin")
            ensure_admin_user_for_credentials("admin")

        session = session_factory()
        assert session.query(User).filter(User.username == "admin").count() == 1

    def test_returns_false_without_a_configured_username(self, session_factory):
        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("") is False
            assert ensure_admin_user_for_credentials(None) is False


class TestWizardStillPending:
    """Regression coverage: reconciling during first-run setup pre-empts the
    installation wizard, whose create-admin step 400s as soon as any ADMIN
    User row exists.
    """

    def test_skips_when_no_wizard_state_row_exists(self, session_factory):
        """A brand new install has no WizardState row at all — it is created
        lazily by GET /api/wizard/status, POST /start or POST /skip, never at
        boot. The first-run middleware locks the whole app to /wizard in this
        state, so no session role can be needed yet.
        """
        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is False

        session = session_factory()
        assert session.query(User).count() == 0, "must not pre-seed the wizard's admin"

    @pytest.mark.parametrize(
        "status", [WizardStatus.NOT_STARTED, WizardStatus.IN_PROGRESS]
    )
    def test_skips_while_wizard_is_unfinished(self, session_factory, status):
        _seed_wizard_state(session_factory, status)

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is False

        session = session_factory()
        assert session.query(User).count() == 0

    @pytest.mark.parametrize("status", [WizardStatus.COMPLETED, WizardStatus.SKIPPED])
    def test_reconciles_once_first_run_setup_is_over(self, session_factory, status):
        """SKIPPED counts as done: the wizard will never create an admin row
        for a skipped install, so the configured credential needs one here.
        """
        _seed_wizard_state(session_factory, status)

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is True

        session = session_factory()
        user = session.query(User).filter(User.username == "admin").first()
        assert user is not None
        assert user.role == UserRole.ADMIN

    def test_skips_when_wizard_state_cannot_be_read(self, session_factory):
        """Fail safe: if the wizard table is unreadable we must not guess in
        the direction that permanently breaks fresh installs.
        """
        engine = session_factory.kw["bind"]
        WizardState.__table__.drop(engine)

        with _patch_get_db(session_factory):
            assert ensure_admin_user_for_credentials("admin") is False

        session = session_factory()
        assert session.query(User).count() == 0
