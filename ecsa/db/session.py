from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ecsa import config
from ecsa.db.models import Base

_engine = None
_factory = None


def get_engine(url: str | None = None):
    global _engine, _factory
    if url is None and _engine is not None:
        return _engine
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ignores FKs unless told otherwise
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    _engine = engine
    _factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine


def get_session_factory():
    if _factory is None:
        get_engine()
    return _factory


def init_db(url: str | None = None, seed_defaults: bool = True):
    """Create all tables and (optionally) load default parameters."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    if seed_defaults:
        from ecsa.parameters.store import seed_default_parameters
        with session_scope() as s:
            seed_default_parameters(s)
    return engine


@contextmanager
def session_scope() -> Session:
    s = get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
