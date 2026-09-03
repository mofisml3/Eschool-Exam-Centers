import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ecsa.db.models import Base
from ecsa.parameters.store import seed_default_parameters


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return eng


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
