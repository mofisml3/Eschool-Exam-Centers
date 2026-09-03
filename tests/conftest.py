import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ecsa.db.models import Base
from ecsa.parameters.store import seed_default_parameters


TEST_DB_URL = os.getenv("ECSA_TEST_DATABASE_URL")  # e.g. postgresql+psycopg://ecsa:ecsa@localhost/ecsa_test


@pytest.fixture()
def engine():
    if TEST_DB_URL:
        from ecsa.config import normalize_database_url
        eng = create_engine(normalize_database_url(TEST_DB_URL), future=True)
        Base.metadata.drop_all(eng)
        Base.metadata.create_all(eng)
        yield eng
        Base.metadata.drop_all(eng)
        eng.dispose()
        return
    eng = create_engine("sqlite://", future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng


@pytest.fixture()
def db(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = factory()
    seed_default_parameters(s)
    s.commit()
    try:
        yield s
    finally:
        s.close()
