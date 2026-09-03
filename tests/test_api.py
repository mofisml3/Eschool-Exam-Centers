import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from ecsa.api import create_app
from ecsa.tools.sample_data import generate


@pytest.fixture()
def client(engine, db, tmp_path):
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    app = create_app(session_factory=factory)
    with TestClient(app) as c:
        files = generate(tmp_path, students=300, schools=6, districts=2, seed=1)
        for kind in ("students", "subjects", "student_subjects", "schools"):
            r = c.post(f"/import/{kind}", files={"file": (f"{kind}.csv", files[kind].read_bytes(), "text/csv")})
            assert r.status_code == 200 and r.json()["errors"] == 0, r.text
        yield c


def test_health_and_summary(client):
    assert client.get("/health").json()["status"] == "ok"
    s = client.get("/data/summary", params={"governorate": "Basra"}).json()
    assert s["students"] == 300 and s["schools"] == 6 and s["governorates"] == ["Basra"]


def test_parameters_roundtrip(client):
    r = client.put("/parameters", json={"param_key": "sessions_per_day", "param_value": "3", "governorate": "Basra", "effective_from": "2020-01-01"})
    assert r.status_code == 200
    assert client.get("/parameters/resolved", params={"governorate": "Basra"}).json()["sessions_per_day"] == "3"
    assert client.get("/parameters/resolved").json()["sessions_per_day"] == "4"


def test_preview_then_run_then_export(client):
    p = client.post("/centers/preview", json={"governorate": "Basra", "exam_round": 1, "param_overrides": {"operating_days_per_round": 10}})
    assert p.status_code == 200 and p.json()["decision"]["primary"]
    r = client.post("/scenarios", json={"name": "api", "governorate": "Basra", "exam_round": 1, "round_start_date": "2026-03-01",
                                        "param_overrides": {"operating_days_per_round": 10}})
    assert r.status_code == 200, r.text
    sc = r.json()
    assert sc["status"] == "completed" and sc["kpi_summary"]["coverage"] == 1.0
    sid = sc["scenario_id"]
    assert client.get(f"/scenarios/{sid}").json()["decision_log"]["decision"]["primary"]
    assert client.get(f"/scenarios/{sid}/centers").json()[0]["halls"]
    assert client.get(f"/scenarios/{sid}/sessions").json()
    a = client.get(f"/scenarios/{sid}/assignments", params={"limit": 10}).json()
    assert a["total"] == sc["kpi_summary"]["assigned"] and len(a["rows"]) == 10
    one = client.get(f"/scenarios/{sid}/assignments", params={"student_id": a["rows"][0]["student_id"]}).json()
    assert 1 <= one["total"] <= 7
    x = client.get(f"/scenarios/{sid}/export.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.post(f"/scenarios/{sid}/approve").json()["status"] == "approved"
    cmp = client.get("/scenarios/compare", params={"ids": [sid]}).json()
    assert cmp[0]["scenario_id"] == sid
    assert client.delete(f"/scenarios/{sid}").json()["deleted"] == sid
    assert client.get(f"/scenarios/{sid}").status_code == 404


def test_scenario_error_is_400(client):
    r = client.post("/scenarios", json={"name": "x", "governorate": "Nowhere", "exam_round": 1, "round_start_date": "2026-03-01"})
    assert r.status_code == 400 and "no students" in r.json()["detail"]


def test_import_reports_errors(client):
    bad = io.BytesIO(b"school_id,name\nX,Y\n")
    r = client.post("/import/schools", files={"file": ("schools.csv", bad.getvalue(), "text/csv")})
    assert r.status_code == 200 and r.json()["errors"] == 1
    assert client.post("/import/nope", files={"file": ("a.csv", b"a\n1\n", "text/csv")}).status_code == 404
