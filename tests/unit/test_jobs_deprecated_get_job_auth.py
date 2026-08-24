"""Regression test for a gap in jobs.py's deprecated GET /{job_id}
(get_job), found while reviewing #405's wizard.py fix. get_job() had no
gating at all -- not even the wizard-completion awareness wizard.py's
other dual-purpose endpoints got.

Its own docstring says "wizard-compatible, no auth required", and
wizard.js does poll it pre-setup (`fetch(`/api/jobs/${wizardState.
importJobId}`)`) -- but grepping the frontend shows settings.html's
"Settings > System" import feature ALSO polls this exact same endpoint
post-setup (pollVideoImportProgress() -> fetch(`/api/jobs/${importJobId}`)),
to track progress of jobs started by /api/wizard/import/start -- the
identical dual-purpose situation #405 fixed for that endpoint. Without
any gate, any unauthenticated caller could poll the status/progress/
result of ANY Celery job_id in the system, indefinitely, post-setup.

Fix: reuse wizard.py's require_wizard_incomplete_or_authenticated
dependency (already covers exactly this pre-setup/post-setup split) --
passes through untouched while the wizard is still incomplete, and
requires a real authenticated session once it's completed.

cancel_job (DELETE /{job_id}) and the other jobs.py endpoints are
untouched here: cancel_job is a redirect-only 301 to
/api/metadata-enrichment/job/{job_id}/cancel, which is already
require_authentication-gated at the real destination; health/status/
list_jobs/create_job return only static deprecation messages or generic
migration info, no per-job or system data.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.fastapi.jobs import router
from src.database.connection import Base, get_db_session
from src.database.models import WizardState, WizardStatus

SOURCE_PATH = (
    Path(__file__).parent.parent.parent / "src" / "api" / "fastapi" / "jobs.py"
)


def _function_source(function_name: str) -> str:
    text = SOURCE_PATH.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[start:end])
    raise AssertionError(f"Could not find function {function_name!r} in {SOURCE_PATH}")


class TestGetJobUsesTheDualPurposeGate:
    def test_get_job_wires_the_wizard_or_authenticated_dependency(self):
        source = _function_source("get_job")
        assert "Depends(" in source
        assert "require_wizard_incomplete_or_authenticated" in source

    def test_cancel_job_stays_untouched_pure_redirect(self):
        # Regression guard: cancel_job must stay a bare redirect (its
        # security already comes from the destination route), not
        # accidentally pick up its own auth dependency that could break
        # the redirect-only contract.
        source = _function_source("cancel_job")
        assert "RedirectResponse" in source
        assert "Depends(" not in source


@pytest.fixture
def session_factory():
    # TestClient runs the ASGI app in its own background thread.
    # check_same_thread=False permits cross-thread use of the connection;
    # StaticPool keeps it to the single connection actually holding the
    # schema (SQLAlchemy's default SingletonThreadPool for sqlite:///:memory:
    # hands the *other* thread a brand new, empty in-memory database
    # instead of reusing this one).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[WizardState.__table__])
    return sessionmaker(bind=engine)


class TestGetJobBehavioralAuth:
    def _client(self, session_factory):
        app = FastAPI()
        app.include_router(router)
        # get_db_session is a generator dependency (yields a session);
        # this override is a plain callable, so FastAPI injects
        # whatever it *returns* directly rather than unwrapping a
        # generator -- must return the session itself, not an iterator
        # wrapping it, or session.query(...) fails on the wrapper object.
        app.dependency_overrides[get_db_session] = lambda: session_factory()
        return TestClient(app)

    def test_401s_for_a_completed_wizard_with_no_session(self, session_factory):
        session = session_factory()
        session.add(WizardState(status=WizardStatus.COMPLETED))
        session.commit()
        session.close()

        client = self._client(session_factory)
        response = client.get("/api/jobs/some-job-id")
        assert response.status_code == 401

    def test_passes_through_while_wizard_is_incomplete(self, session_factory):
        # No WizardState row seeded -- matches a fresh install where the
        # wizard hasn't started yet.
        client = self._client(session_factory)
        response = client.get("/api/jobs/some-job-id")
        # Reaches the route body (may itself fail against a fake/missing
        # Celery backend, but must not be rejected by the auth gate).
        assert response.status_code != 401
