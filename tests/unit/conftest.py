"""Shared fixtures for tests/unit/.

Currently provides one thing: a real, temp-file SQLite database wired
transparently behind `src.database.connection.get_db()` for
`test_claim_video_for_download.py` (#329). That test module intentionally
calls the *real*, unpatched `get_db()` (see its docstring — it wants a
real database, not mocks), but this repo's `Config`/`DatabaseManager`
only ever build a `mysql+pymysql://` URL, and no MySQL/MariaDB server is
reachable from this sandboxed test environment (the dev stack's mariadb
container publishes no host port). Rather than have that test module
silently require infrastructure that isn't there, this fixture swaps the
module-level `db_manager` singleton in `src.database.connection` for one
backed by a throwaway SQLite file for the duration of that module only,
then restores it. Every other test module is unaffected -- most already
patch `get_db`/`get_db_session` themselves and none rely on this file.
"""

import os
import tempfile
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.connection as connection
from src.database.models import Artist, Video

# Test modules that want a real (unpatched) get_db() backed by a real DB.
_REAL_DB_MODULES = {
    "test_claim_video_for_download.py",
    "test_claim_video_for_redownload.py",
    "test_failure_write_protects_downloaded_status.py",
}


@pytest.fixture(autouse=True)
def _wire_real_sqlite_db(request, monkeypatch):
    if request.node.fspath.basename not in _REAL_DB_MODULES:
        yield
        return

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}")
    connection.Base.metadata.create_all(
        engine, tables=[Artist.__table__, Video.__table__]
    )
    # expire_on_commit=False: the wanted_video fixture in
    # test_claim_video_for_download.py reads `artist.id` in its teardown
    # block, after the setup `with get_db()` session (where `artist` was
    # created) has already committed and closed. With the default
    # expire_on_commit=True -- which this codebase's real
    # DatabaseManager.create_session_factory() also uses, unchanged here
    # -- that attribute access raises DetachedInstanceError because the
    # object's attributes are expired on commit and there's no session
    # left to reload them from. Disabling it only in this test shim keeps
    # already-loaded attribute values cached on the Python object across
    # the session boundary, which is what the fixture assumes.
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def _fake_get_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    class _FakeDbManager:
        def get_session(self):
            return _fake_get_session()

        def create_engine(self):
            # claim_video_for_download() (#329) deliberately uses its own
            # engine connection/transaction instead of get_db()'s scoped
            # session -- see that function's docstring. Return the same
            # engine backing get_session() above so both routes see the
            # same SQLite-backed data.
            return engine

    monkeypatch.setattr(connection, "db_manager", _FakeDbManager())

    yield

    engine.dispose()
    os.remove(db_path)
