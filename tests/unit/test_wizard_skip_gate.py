"""POST /api/wizard/skip takes no authentication, and the gates added for #405
only closed the wizard's public endpoints on WizardStatus.COMPLETED. An
anonymous caller could therefore turn a finished wizard back into SKIPPED and
reopen them: /validate-directory, /test-api and /import/start all answered
without a session again.

A skipped wizard is as finished as a completed one (wizard_middleware.py and
init_db.py already read it that way), so both statuses now close the public
endpoints, and skip only works while the wizard is still unfinished.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.api.fastapi.wizard import (
    CreateAdminRequest,
    create_admin_user,
    require_wizard_incomplete,
    require_wizard_incomplete_or_authenticated,
    skip_wizard,
)
from src.database.connection import Base
from src.database.models import WizardState, WizardStatus

FINISHED = [WizardStatus.COMPLETED, WizardStatus.SKIPPED]
UNFINISHED = [WizardStatus.NOT_STARTED, WizardStatus.IN_PROGRESS]


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[WizardState.__table__])
    return sessionmaker(bind=engine)()


def _seed(session, status):
    session.add(WizardState(status=status))
    session.commit()


def _anonymous_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/wizard/import/start",
            "headers": [],
            "query_string": b"",
            "server": ("localhost", 5000),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "app": None,
        }
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class TestSkipOnlyWorksWhileUnfinished:
    @pytest.mark.parametrize("status", FINISHED)
    def test_refuses_and_keeps_the_status(self, session, status):
        _seed(session, status)
        with pytest.raises(HTTPException) as exc_info:
            _run(skip_wizard(session=session))
        assert exc_info.value.status_code == 409
        session.expire_all()
        assert session.query(WizardState).first().status == status

    @pytest.mark.parametrize("status", UNFINISHED)
    def test_skips(self, session, status):
        _seed(session, status)
        with patch("src.database.init_db.ensure_admin_user_for_credentials"):
            _run(skip_wizard(session=session))
        session.expire_all()
        assert session.query(WizardState).first().status == WizardStatus.SKIPPED


class TestFinishedWizardClosesPublicEndpoints:
    @pytest.mark.parametrize("status", FINISHED)
    def test_require_wizard_incomplete(self, session, status):
        _seed(session, status)
        with pytest.raises(HTTPException) as exc_info:
            _run(require_wizard_incomplete(session=session))
        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize("status", FINISHED)
    def test_import_start_needs_a_session(self, session, status):
        _seed(session, status)
        with pytest.raises(HTTPException) as exc_info:
            _run(
                require_wizard_incomplete_or_authenticated(
                    request=_anonymous_request(), session=session
                )
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.parametrize("status", FINISHED)
    def test_create_admin_refuses(self, session, status):
        _seed(session, status)
        with pytest.raises(HTTPException) as exc_info:
            _run(
                create_admin_user(
                    request=MagicMock(spec=CreateAdminRequest), session=session
                )
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("status", UNFINISHED)
    def test_gates_stay_open_during_setup(self, session, status):
        _seed(session, status)
        assert _run(require_wizard_incomplete(session=session)) is None
        assert (
            _run(
                require_wizard_incomplete_or_authenticated(
                    request=_anonymous_request(), session=session
                )
            )
            is None
        )
