"""Smoke test: every screen renders without exceptions on a populated DB."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ecsa.db import session as dbsession
from ecsa.importer import import_dataframe
from ecsa.scenarios import RunRequest, run_scenario
from ecsa.tools.sample_data import generate
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "ecsa" / "ui" / "app.py"


@pytest.fixture()
def populated_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ui.db'}"
    monkeypatch.setattr(dbsession, "_engine", None)
    monkeypatch.setattr(dbsession, "_factory", None)
    monkeypatch.setattr(dbsession.config, "DATABASE_URL", url)
    dbsession.init_db(url)
    files = generate(tmp_path / "s", students=200, schools=5, districts=2, seed=2)
    with dbsession.session_scope() as s:
        for kind in ("students", "subjects", "student_subjects", "schools"):
            import_dataframe(s, kind, pd.read_csv(files[kind], dtype=str))
    from datetime import date
    with dbsession.session_scope() as s:
        run_scenario(s, RunRequest("ui", "Basra", 1, date(2026, 3, 1), {"operating_days_per_round": 8}))
    yield
    monkeypatch.setattr(dbsession, "_engine", None)
    monkeypatch.setattr(dbsession, "_factory", None)


@pytest.mark.parametrize("screen", ["1 · Import data", "2 · Parameters", "3 · Centers", "4 · Run distribution",
                                    "5 · Compare scenarios", "6 · Reports & sheets"])
def test_screen_renders(populated_db, screen):
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception, at.exception
    at.sidebar.radio[0].set_value(screen).run()
    assert not at.exception, at.exception
    assert any(screen[0] in h.value for h in at.header)


def test_run_button_creates_scenario(populated_db):
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.radio[0].set_value("4 · Run distribution").run()
    at.text_input(key="ov_operating_days_per_round").set_value("6").run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert any("completed" in s.value for s in at.success)
    with dbsession.session_scope() as s:
        from ecsa.scenarios import list_scenarios
        scs = list_scenarios(s, "Basra")
        assert len(scs) == 2 and scs[0].params_snapshot["operating_days_per_round"] == "6"
