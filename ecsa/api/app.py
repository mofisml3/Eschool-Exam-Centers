"""FastAPI application. Thin layer over the service modules."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecsa import __version__
from ecsa.api.schemas import ParameterIn, ParameterOut, PreviewIn, RunIn, ScenarioDetailOut, ScenarioOut
from ecsa.db.models import Center, Hall, School, Session as ExamSession
from ecsa.db.session import get_session_factory, init_db
from ecsa.importer import SPECS, import_dataframe
from ecsa.parameters.store import ParameterStore
from ecsa.reports import assignments_frame, export_scenario_excel
from ecsa.scenarios import (RunRequest, ScenarioError, approve_scenario, compare_scenarios, data_summary, delete_scenario,
                            list_scenarios, preview_decision, run_scenario)


def create_app(database_url: str | None = None, session_factory=None) -> FastAPI:
    if session_factory is None:
        init_db(database_url)
        session_factory = get_session_factory()

    app = FastAPI(title="ECSA — Exam Centers & Student Allocation", version=__version__)

    def db():
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @app.exception_handler(ScenarioError)
    async def _scenario_error(_, exc: ScenarioError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    # ---- data & import ----------------------------------------------------
    @app.get("/data/summary")
    def summary(governorate: str | None = None, s: Session = Depends(db)):
        return data_summary(s, governorate)

    @app.post("/import/{kind}")
    async def import_data(kind: str, file: UploadFile = File(...), s: Session = Depends(db)):
        if kind not in SPECS:
            raise HTTPException(404, f"unknown import kind {kind}; expected one of {sorted(SPECS)}")
        content = await file.read()
        name = (file.filename or "").lower()
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        rep = import_dataframe(s, kind, df)
        return {**rep.summary(), "error_rows": rep.errors[:200]}

    @app.get("/schools")
    def schools(governorate: str | None = None, s: Session = Depends(db)):
        q = select(School)
        if governorate:
            q = q.where(School.governorate == governorate)
        return [{c.name: getattr(r, c.name) for c in School.__table__.columns} for r in s.execute(q.order_by(School.school_id)).scalars()]

    # ---- parameters -------------------------------------------------------
    @app.get("/parameters", response_model=list[ParameterOut])
    def parameters(governorate: str | None = None, s: Session = Depends(db)):
        return ParameterStore(s).list_all(governorate)

    @app.get("/parameters/resolved")
    def parameters_resolved(governorate: str | None = None, s: Session = Depends(db)):
        return ParameterStore(s).resolve(governorate).snapshot()

    @app.put("/parameters", response_model=ParameterOut)
    def set_parameter(body: ParameterIn, s: Session = Depends(db)):
        return ParameterStore(s).set(body.param_key, body.param_value, governorate=body.governorate, unit=body.unit,
                                     effective_from=body.effective_from, description=body.description)

    # ---- centers preview (screen 3) ----------------------------------------
    @app.post("/centers/preview")
    def centers_preview(body: PreviewIn, s: Session = Depends(db)):
        return preview_decision(s, body.governorate, body.exam_round, body.param_overrides, body.include_schools, body.exclude_schools)

    # ---- scenarios ---------------------------------------------------------
    @app.post("/scenarios", response_model=ScenarioOut)
    def run(body: RunIn, s: Session = Depends(db)):
        return run_scenario(s, RunRequest(body.name, body.governorate, body.exam_round, body.round_start_date,
                                          body.param_overrides, body.include_schools, body.exclude_schools))

    @app.get("/scenarios", response_model=list[ScenarioOut])
    def scenarios(governorate: str | None = None, s: Session = Depends(db)):
        return list_scenarios(s, governorate)

    @app.get("/scenarios/compare")
    def compare(ids: list[int] = Query(...), s: Session = Depends(db)):
        return compare_scenarios(s, ids)

    @app.get("/scenarios/{scenario_id}", response_model=ScenarioDetailOut)
    def scenario(scenario_id: int, s: Session = Depends(db)):
        sc = next((x for x in list_scenarios(s) if x.scenario_id == scenario_id), None)
        if sc is None:
            raise HTTPException(404, "scenario not found")
        return sc

    @app.get("/scenarios/{scenario_id}/centers")
    def scenario_centers(scenario_id: int, s: Session = Depends(db)):
        rows = s.execute(select(Center).where(Center.scenario_id == scenario_id).order_by(Center.rank)).scalars().all()
        return [{"center_id": c.center_id, "school_id": c.school_id, "name": c.school.name, "district": c.school.district,
                 "category": c.category, "activation_status": c.activation_status, "rank": c.rank, "score": c.score,
                 "halls": [{"hall_id": h.hall_id, "hall_name": h.hall_name, "capacity": h.capacity, "safe_capacity": h.safe_capacity} for h in c.halls]}
                for c in rows]

    @app.get("/scenarios/{scenario_id}/sessions")
    def scenario_sessions(scenario_id: int, s: Session = Depends(db)):
        rows = s.execute(select(ExamSession).where(ExamSession.scenario_id == scenario_id)
                         .order_by(ExamSession.exam_date, ExamSession.session_no, ExamSession.subject_id)).scalars().all()
        return [{"session_id": r.session_id, "exam_date": r.exam_date, "session_no": r.session_no, "subject_id": r.subject_id} for r in rows]

    @app.get("/scenarios/{scenario_id}/assignments")
    def scenario_assignments(scenario_id: int, student_id: str | None = None, center_id: int | None = None,
                             exam_date: str | None = None, limit: int = 500, offset: int = 0, s: Session = Depends(db)):
        df = assignments_frame(s, scenario_id)
        if student_id:
            df = df[df["student_id"] == student_id]
        if center_id is not None:
            df = df[df["center_id"] == center_id]
        if exam_date:
            df = df[df["exam_date"].astype(str) == exam_date]
        total = len(df)
        page = df.iloc[offset:offset + limit]
        return {"total": total, "rows": page.astype(object).where(page.notna(), None).to_dict("records")}

    @app.post("/scenarios/{scenario_id}/approve", response_model=ScenarioOut)
    def approve(scenario_id: int, s: Session = Depends(db)):
        return approve_scenario(s, scenario_id)

    @app.delete("/scenarios/{scenario_id}")
    def remove(scenario_id: int, s: Session = Depends(db)):
        delete_scenario(s, scenario_id)
        return {"deleted": scenario_id}

    @app.get("/scenarios/{scenario_id}/export.xlsx")
    def export(scenario_id: int, attendance: bool = False, s: Session = Depends(db)):
        out = Path(tempfile.mkdtemp()) / f"scenario_{scenario_id}.xlsx"
        try:
            export_scenario_excel(s, scenario_id, out, attendance)
        except ValueError as e:
            raise HTTPException(404, str(e))
        return FileResponse(out, filename=out.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return app


app = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
