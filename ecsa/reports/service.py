"""Reports & export: attendance sheets per hall-session, distribution per
center, student exam cards, utilization tables, Excel workbook export."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecsa.db.models import Assignment, Center, Hall, Scenario, School, Session as ExamSession, Student, Subject


def _scenario(s: Session, scenario_id: int) -> Scenario:
    sc = s.get(Scenario, scenario_id)
    if sc is None:
        raise ValueError(f"scenario {scenario_id} not found")
    return sc


def assignments_frame(s: Session, scenario_id: int) -> pd.DataFrame:
    q = (select(Assignment.assignment_id, Assignment.student_id, Student.full_name, Student.district.label("student_district"),
                Student.gender, ExamSession.exam_date, ExamSession.session_no, ExamSession.subject_id, Subject.name.label("subject_name"),
                Center.center_id, School.school_id, School.name.label("center_name"), School.district.label("center_district"),
                Center.category, Hall.hall_id, Hall.hall_name, Hall.safe_capacity, Assignment.seat_no, Assignment.distance_km, Assignment.note)
         .join(Student, Student.student_id == Assignment.student_id)
         .join(ExamSession, ExamSession.session_id == Assignment.session_id)
         .join(Subject, Subject.subject_id == ExamSession.subject_id)
         .join(Center, Center.center_id == Assignment.center_id)
         .join(School, School.school_id == Center.school_id)
         .join(Hall, Hall.hall_id == Assignment.hall_id)
         .where(Assignment.scenario_id == scenario_id)
         .order_by(ExamSession.exam_date, ExamSession.session_no, Center.center_id, Hall.hall_id, Assignment.seat_no))
    df = pd.DataFrame(s.execute(q).mappings().all())
    if df.empty:
        df = pd.DataFrame(columns=["assignment_id", "student_id", "full_name", "student_district", "gender", "exam_date", "session_no",
                                   "subject_id", "subject_name", "center_id", "school_id", "center_name", "center_district", "category",
                                   "hall_id", "hall_name", "safe_capacity", "seat_no", "distance_km", "note"])
    return df


def centers_frame(s: Session, scenario_id: int) -> pd.DataFrame:
    q = (select(Center.center_id, Center.school_id, School.name, School.district, Center.category, Center.activation_status,
                Center.rank, Center.score, School.readiness_score)
         .join(School, School.school_id == Center.school_id).where(Center.scenario_id == scenario_id).order_by(Center.rank))
    df = pd.DataFrame(s.execute(q).mappings().all())
    halls = pd.DataFrame(s.execute(select(Hall.center_id, Hall.hall_id, Hall.hall_name, Hall.capacity, Hall.safe_capacity)
                                   .join(Center).where(Center.scenario_id == scenario_id)).mappings().all())
    if not df.empty and not halls.empty:
        agg = halls.groupby("center_id").agg(halls=("hall_id", "count"), capacity=("capacity", "sum"), safe_capacity=("safe_capacity", "sum"))
        df = df.merge(agg, left_on="center_id", right_index=True, how="left")
    return df


def sessions_frame(s: Session, scenario_id: int) -> pd.DataFrame:
    q = (select(ExamSession.session_id, ExamSession.exam_date, ExamSession.session_no, ExamSession.subject_id, Subject.name.label("subject_name"))
         .join(Subject).where(ExamSession.scenario_id == scenario_id).order_by(ExamSession.exam_date, ExamSession.session_no, ExamSession.subject_id))
    return pd.DataFrame(s.execute(q).mappings().all())


def attendance_sheets(df: pd.DataFrame) -> dict[tuple, pd.DataFrame]:
    """One attendance sheet per (exam_date, session_no, center, hall)."""
    cols = ["seat_no", "student_id", "full_name", "student_district", "subject_id", "subject_name"]
    out = {}
    if df.empty:
        return out
    for key, g in df.groupby(["exam_date", "session_no", "center_name", "hall_name"], sort=True):
        sheet = g.sort_values("seat_no")[cols].reset_index(drop=True)
        sheet["signature"] = ""
        out[key] = sheet
    return out


def center_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Per center: students per date/session/hall."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(["center_id", "center_name", "exam_date", "session_no", "hall_name", "safe_capacity"]).size().reset_index(name="students")
    g["utilization"] = (g["students"] / g["safe_capacity"]).round(4)
    return g


def student_cards(df: pd.DataFrame) -> pd.DataFrame:
    """One row per student × subject with where and when to sit."""
    if df.empty:
        return pd.DataFrame()
    cols = ["student_id", "full_name", "student_district", "subject_id", "subject_name", "exam_date", "session_no",
            "center_name", "center_district", "hall_name", "seat_no", "distance_km"]
    return df[cols].sort_values(["student_id", "exam_date", "session_no"]).reset_index(drop=True)


def utilization_frames(s: Session, scenario_id: int, df: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    sc = _scenario(s, scenario_id)
    k = sc.kpi_summary
    centers = pd.DataFrame(k.get("centers", []))
    slots = pd.DataFrame(k.get("slots_detail", []))
    df = assignments_frame(s, scenario_id) if df is None else df
    if df.empty:
        halls = pd.DataFrame()
    else:
        halls = df.groupby(["center_name", "hall_name", "safe_capacity"]).size().reset_index(name="assigned")
        n_slots = k.get("slots", 1) or 1
        halls["safe_seats"] = halls["safe_capacity"] * n_slots
        halls["utilization"] = (halls["assigned"] / halls["safe_seats"]).round(4)
    return {"centers": centers, "halls": halls, "slots": slots}


def scenario_summary(s: Session, scenario_id: int) -> pd.DataFrame:
    sc = _scenario(s, scenario_id)
    rows = [{"key": "scenario", "value": f"{sc.scenario_id} — {sc.name}"}, {"key": "governorate", "value": sc.governorate},
            {"key": "exam_round", "value": sc.exam_round}, {"key": "status", "value": sc.status},
            {"key": "created_at", "value": sc.created_at.isoformat()}]
    rows += [{"key": k, "value": v} for k, v in sc.kpi_summary.items() if not isinstance(v, (list, dict))]
    return pd.DataFrame(rows)


def unassigned_frame(s: Session, scenario_id: int) -> pd.DataFrame:
    sc = _scenario(s, scenario_id)
    return pd.DataFrame(sc.decision_log.get("allocation", {}).get("unassigned_sample", []))


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = "".join(ch for ch in str(name) if ch not in '[]:*?/\\')[:28] or "sheet"
    candidate, i = base, 1
    while candidate in used:
        i += 1
        candidate = f"{base[:25]}_{i}"
    used.add(candidate)
    return candidate


def export_scenario_excel(s: Session, scenario_id: int, path: str | Path, attendance: bool = False) -> Path:
    """Write the scenario workbook. With attendance=True, adds one sheet per
    exam date containing all attendance lists of that day (kept in one sheet
    per day to stay within Excel's sheet limits)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = _scenario(s, scenario_id)
    df = assignments_frame(s, scenario_id)
    util = utilization_frames(s, scenario_id, df)
    params = pd.DataFrame([{"param_key": k, "param_value": v} for k, v in sorted(sc.params_snapshot.items())])
    ranking = pd.DataFrame(sc.decision_log.get("ranking", []))
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        scenario_summary(s, scenario_id).to_excel(xw, sheet_name="Summary", index=False)
        params.to_excel(xw, sheet_name="Parameters", index=False)
        if not ranking.empty:
            ranking.drop(columns=["weights"], errors="ignore").to_excel(xw, sheet_name="School_Ranking", index=False)
        centers_frame(s, scenario_id).to_excel(xw, sheet_name="Centers", index=False)
        sessions_frame(s, scenario_id).to_excel(xw, sheet_name="Sessions", index=False)
        student_cards(df).to_excel(xw, sheet_name="Student_Cards", index=False)
        center_distribution(df).to_excel(xw, sheet_name="Center_Distribution", index=False)
        util["centers"].to_excel(xw, sheet_name="Util_Centers", index=False)
        util["halls"].to_excel(xw, sheet_name="Util_Halls", index=False)
        util["slots"].to_excel(xw, sheet_name="Util_Slots", index=False)
        unassigned_frame(s, scenario_id).to_excel(xw, sheet_name="Unassigned", index=False)
        if attendance and not df.empty:
            used: set[str] = set()
            for exam_date, day in df.groupby("exam_date", sort=True):
                rows: list[dict] = []
                for (sess, center, hall), g in day.groupby(["session_no", "center_name", "hall_name"], sort=True):
                    rows.append({"seat_no": f"Session {sess} — {center} — {hall}"})
                    rows.extend({"seat_no": r.seat_no, "student_id": r.student_id, "full_name": r.full_name,
                                 "subject_name": r.subject_name, "signature": ""}
                                for r in g.sort_values("seat_no").itertuples(index=False))
                    rows.append({})
                pd.DataFrame(rows, columns=["seat_no", "student_id", "full_name", "subject_name", "signature"]).to_excel(
                    xw, sheet_name=_safe_sheet_name(f"Att_{exam_date}", used), index=False)
    return path
