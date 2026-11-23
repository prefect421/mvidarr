"""#615: every request/caller must get its own Session, never a thread-shared one."""

from sqlalchemy import create_engine

import src.database.connection as conn


def _manager(monkeypatch):
    mgr = conn.DatabaseManager.__new__(conn.DatabaseManager)
    mgr.engine = create_engine("sqlite://")
    mgr.session_factory = None
    from threading import Lock

    mgr._lock = Lock()
    monkeypatch.setattr(conn, "db_manager", mgr)
    return mgr


def test_get_db_session_returns_distinct_sessions_on_one_thread(monkeypatch):
    _manager(monkeypatch)
    g1 = conn.get_db_session()
    g2 = conn.get_db_session()
    s1, s2 = next(g1), next(g2)
    assert s1 is not s2
    g1.close()
    # closing one request's session must not affect the other
    assert s2.is_active
    g2.close()


def test_nested_get_db_blocks_get_distinct_sessions(monkeypatch):
    mgr = _manager(monkeypatch)
    with mgr.get_session() as outer:
        with mgr.get_session() as inner:
            assert outer is not inner
        # inner closing must leave the outer session usable
        assert outer.is_active
