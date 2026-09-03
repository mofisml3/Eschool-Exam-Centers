import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def _reload_config(monkeypatch, **env):
    for k in ("VERCEL", "ECSA_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "ECSA_DATA_DIR"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from ecsa import config
    return importlib.reload(config)


def test_neon_style_database_url_is_picked_up(monkeypatch):
    cfg = _reload_config(monkeypatch, VERCEL="1", DATABASE_URL="postgres://u:p@host/db")
    assert cfg.DATABASE_URL == "postgresql+psycopg://u:p@host/db"
    assert cfg.DATABASE_URL_SOURCE == "DATABASE_URL" and not cfg.EPHEMERAL_STORAGE
    assert str(cfg.DATA_DIR).startswith("/tmp")


def test_serverless_without_database_falls_back_to_tmp_and_warns(monkeypatch, tmp_path):
    cfg = _reload_config(monkeypatch, VERCEL="1", ECSA_DATA_DIR=str(tmp_path))
    assert cfg.EPHEMERAL_STORAGE and cfg.DATABASE_URL.startswith("sqlite:///")
    from ecsa.db import session as dbsession
    monkeypatch.setattr(dbsession, "_engine", None)
    monkeypatch.setattr(dbsession, "_factory", None)
    sys.modules.pop("api.index", None)
    sys.path.insert(0, str(ROOT))
    entry = importlib.import_module("api.index")
    with TestClient(entry.app) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and "ephemeral" in h["warning"]
        assert c.get("/", follow_redirects=False).status_code == 307
        assert c.get("/parameters/resolved").json()["sessions_per_day"] == "4"
    monkeypatch.setattr(dbsession, "_engine", None)
    monkeypatch.setattr(dbsession, "_factory", None)
    _reload_config(monkeypatch)


def test_local_default_is_project_sqlite(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert not cfg.IS_SERVERLESS and cfg.DATABASE_URL_SOURCE == "default-sqlite" and not cfg.EPHEMERAL_STORAGE
