"""Regression test for issue #325: complete_wizard_step() didn't reconcile
the admin User row the way skip_wizard() already does.

Without this, an install that reaches WizardStatus.COMPLETED via
complete_wizard_step() without ever calling POST /create-admin directly
(possible via direct API use, bypassing wizard.js's own UI flow, which
always calls create-admin before advancing) would have the configured
SimpleAuth credential resolve to a READONLY session until the next
application restart — the exact bug already fixed for skip_wizard() in
the auth-cluster branch's final review, just missing here.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.wizard import router
from src.database.connection import Base, get_db_session
from src.database.models import WizardState, WizardStatus, WizardStep


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: get_db_session is a sync
    # generator dependency, so FastAPI runs it via anyio's threadpool
    # while the async route handler runs on the event-loop thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[WizardState.__table__])
    return sessionmaker(bind=engine)


def _make_client(session_factory):
    app = FastAPI()
    app.include_router(router)

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app)


def _seed_wizard_state(session_factory, **flags):
    session = session_factory()
    state = WizardState(
        status=WizardStatus.IN_PROGRESS,
        current_step=WizardStep.VIDEO_IMPORT,
        admin_account_completed=True,
        directories_completed=True,
        api_config_completed=True,
        video_import_completed=False,
        **flags,
    )
    session.add(state)
    session.commit()
    session.close()


RECONCILE_PATCH_TARGET = "src.database.init_db.ensure_admin_user_for_credentials"


class TestCompleteWizardStepReconciliation:
    def test_completing_the_final_step_reconciles_the_admin_user(self, session_factory):
        _seed_wizard_state(session_factory)
        client = _make_client(session_factory)

        with patch(RECONCILE_PATCH_TARGET) as mock_reconcile, patch(
            "src.services.settings_service.SettingsService.get",
            return_value="admin",
        ):
            response = client.post("/api/wizard/steps/video_import/complete", json={})

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        mock_reconcile.assert_called_once_with("admin")

    def test_completing_a_non_final_step_does_not_reconcile(self, session_factory):
        # Seed a wizard genuinely mid-flow (not one step away from
        # completion) so completing this step cannot trigger COMPLETED.
        session = session_factory()
        state = WizardState(
            status=WizardStatus.IN_PROGRESS,
            current_step=WizardStep.WELCOME,
            admin_account_completed=False,
            directories_completed=False,
            api_config_completed=False,
            video_import_completed=False,
        )
        session.add(state)
        session.commit()
        session.close()
        client = _make_client(session_factory)

        with patch(RECONCILE_PATCH_TARGET) as mock_reconcile:
            response = client.post("/api/wizard/steps/welcome/complete", json={})

        assert response.status_code == 200
        assert response.json()["status"] != "completed"
        mock_reconcile.assert_not_called()


class TestSkipWizardStillReconciles:
    """Confirm the fix didn't disturb skip_wizard's existing, already-
    correct reconciliation call.
    """

    def test_skip_still_reconciles(self, session_factory):
        client = _make_client(session_factory)

        with patch(RECONCILE_PATCH_TARGET) as mock_reconcile, patch(
            "src.services.settings_service.SettingsService.get",
            return_value="admin",
        ):
            response = client.post("/api/wizard/skip")

        assert response.status_code == 200
        mock_reconcile.assert_called_once_with("admin")
