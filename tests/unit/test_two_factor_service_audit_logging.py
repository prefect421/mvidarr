"""Regression tests for TwoFactorService's broken AuditService call sites.

Root cause (found 2026-08-12, live lockout incident): every
AuditService.log_security_event / log_user_action call in
src/services/two_factor_service.py passes arguments that don't match the
real method signatures — missing the required `message` argument (or, for
log_user_action, missing `resource` and passing a nonexistent
`admin_user_id` kwarg). Each call site raises TypeError at the call itself
(argument binding fails before AuditService's own body — and its own
internal try/except — ever runs).

Every TwoFactorService method wraps its whole body in `except Exception`,
so the TypeError is swallowed and turned into a reported failure — even on
the SUCCESS path, after the DB write already committed. Concretely:
confirm_two_factor_setup sets user.two_factor_enabled = True and commits,
then immediately crashes calling AuditService.log_user_action, returning
False to the caller. The frontend shows "verification failed" while 2FA is
now actually enabled with no confirmed-working authenticator entry —
exactly what caused a real admin lockout.

These tests call the real (unpatched) AuditService — the bug is a call-time
argument-binding TypeError, so mocking AuditService away would hide it.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pyotp
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.connection import Base
from src.database.models import User, UserRole
from src.services.two_factor_service import TwoFactorService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__])
    return sessionmaker(bind=engine)


@contextmanager
def _fake_get_db(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _patch_get_db(session_factory):
    # See tests/unit/test_two_factor_status_endpoint.py for why this has to
    # patch src.services.two_factor_service.get_db specifically.
    return patch(
        "src.services.two_factor_service.get_db",
        lambda: _fake_get_db(session_factory),
    )


def _seed_user(session_factory, password="Sup3rSecret!", two_factor_enabled=False):
    session = session_factory()
    user = User(
        username="someone",
        email="someone@test.local",
        password=password,
        role=UserRole.USER,
    )
    user.two_factor_enabled = two_factor_enabled
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id


class TestConfirmTwoFactorSetup:
    def test_valid_token_enables_2fa_and_returns_success(self, session_factory):
        user_id = _seed_user(session_factory)
        secret = TwoFactorService.generate_secret()

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.two_factor_secret = secret
        session.commit()
        session.close()

        valid_token = pyotp.TOTP(secret).now()

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.confirm_two_factor_setup(
                user_id, valid_token
            )

        assert success is True
        assert message == "Two-factor authentication enabled successfully"

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        assert user.two_factor_enabled is True
        session.close()

    def test_invalid_token_returns_failure_without_crashing(self, session_factory):
        user_id = _seed_user(session_factory)
        secret = TwoFactorService.generate_secret()

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.two_factor_secret = secret
        session.commit()
        session.close()

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.confirm_two_factor_setup(
                user_id, "000000"
            )

        assert success is False
        # Pin the real rejection message, not a swallowed TypeError like
        # "Confirmation failed: log_security_event() missing 1 required
        # positional argument: 'message'".
        assert message == "Invalid verification code. Please try again."


class TestDisableTwoFactor:
    def test_correct_password_disables_2fa_and_returns_success(self, session_factory):
        user_id = _seed_user(session_factory, two_factor_enabled=True)

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.disable_two_factor(
                user_id, "Sup3rSecret!"
            )

        assert success is True
        assert message == "Two-factor authentication disabled successfully"

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        assert user.two_factor_enabled is False
        session.close()

    def test_wrong_password_returns_failure_without_crashing(self, session_factory):
        user_id = _seed_user(session_factory, two_factor_enabled=True)

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.disable_two_factor(
                user_id, "WrongPassword!"
            )

        assert success is False
        assert message == "Incorrect password"


class TestVerifyTwoFactorLogin:
    def test_valid_totp_returns_success(self, session_factory):
        user_id = _seed_user(session_factory, two_factor_enabled=True)
        secret = TwoFactorService.generate_secret()

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.two_factor_secret = secret
        session.commit()
        session.close()

        valid_token = pyotp.TOTP(secret).now()

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.verify_two_factor_login(
                user_id, valid_token
            )

        assert success is True
        assert message == "Two-factor authentication successful"

    def test_invalid_totp_returns_failure_without_crashing(self, session_factory):
        user_id = _seed_user(session_factory, two_factor_enabled=True)
        secret = TwoFactorService.generate_secret()

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.two_factor_secret = secret
        session.commit()
        session.close()

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.verify_two_factor_login(
                user_id, "000000"
            )

        assert success is False
        assert message == "Invalid verification code"

    def test_valid_backup_code_returns_success_and_consumes_code(self, session_factory):
        import json

        user_id = _seed_user(session_factory, two_factor_enabled=True)

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.backup_codes = json.dumps(["ABCD1234", "EFGH5678"])
        session.commit()
        session.close()

        with _patch_get_db(session_factory):
            success, message = TwoFactorService.verify_two_factor_login(
                user_id, "abcd1234"
            )

        assert success is True
        assert message == "Backup code accepted"

        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        remaining = json.loads(user.backup_codes)
        assert remaining == ["EFGH5678"]
        session.close()


class TestRegenerateBackupCodes:
    def test_correct_password_regenerates_codes_without_crashing(self, session_factory):
        import json

        user_id = _seed_user(session_factory, two_factor_enabled=True)
        session = session_factory()
        user = session.query(User).filter_by(id=user_id).first()
        user.backup_codes = json.dumps(["OLDCODE1"])
        session.commit()
        session.close()

        with _patch_get_db(session_factory):
            success, message, new_codes = TwoFactorService.regenerate_backup_codes(
                user_id, "Sup3rSecret!"
            )

        assert success is True
        assert message == "Backup codes regenerated successfully"
        assert new_codes is not None
        assert "OLDCODE1" not in new_codes
        assert len(new_codes) == 8
