"""Consistency fix: UserService.change_password() carried its own copy of
the stale 6-character password minimum (found while fixing the same rule
elsewhere -- see test_update_credentials_password_length.py and
test_credentials_endpoint.py). This method has no callers anywhere in the
codebase today, so the bug wasn't user-reachable, but the constant should
still agree with SimpleAuthService.set_credentials()'s real 8-character
minimum rather than drift further out of sync if it's ever wired up.
"""

import pytest

from src.services.user_service import UserService


@pytest.fixture
def service():
    # change_password's length check raises before any DB access, so a
    # None database_manager is fine for this test.
    return UserService(database_manager=None)


class TestChangePasswordMinimumLength:
    # change_password catches its own length ValueError in a blanket
    # except Exception and returns False rather than letting it
    # propagate -- so the boundary itself shows up as a False return,
    # and the corrected message text (8, not 6) is only observable via
    # the log line it emits on that path.

    def test_seven_char_password_is_rejected(self, service, caplog):
        assert service.change_password(1, "mvidarr") is False
        assert "8 characters" in caplog.text

    def test_six_char_password_is_no_longer_the_enforced_boundary(
        self, service, caplog
    ):
        # Regression pin: this used to be the exact boundary that passed
        # (and, before that, the message said 6 even for a call this
        # short would never have reached in the first place).
        assert service.change_password(1, "six6ch") is False
        assert "8 characters" in caplog.text
