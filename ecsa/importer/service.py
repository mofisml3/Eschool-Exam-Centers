"""Import students, subjects, student_subjects, schools and school_halls from
Excel/CSV with validation. Rows that fail validation are reported and
skipped; valid rows are upserted by primary key."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecsa.db.models import School, SchoolHall, Student, StudentSubject, Subject


@dataclass
class ColumnSpec:
    name: str
    required: bool = True
    kind: str = "str"  # str | int | float
    min: float | None = None
    max: float | None = None


@dataclass
class TableSpec:
    kind: str
    columns: list[ColumnSpec]
    key: tuple[str, ...]


SPECS: dict[str, TableSpec] = {
    "students": TableSpec("students", [
        ColumnSpec("student_id"), ColumnSpec("full_name"), ColumnSpec("governorate"), ColumnSpec("district"),
        ColumnSpec("lat", False, "float", -90, 90), ColumnSpec("lng", False, "float", -180, 180),
        ColumnSpec("gender", False), ColumnSpec("status", False)], ("student_id",)),
    "subjects": TableSpec("subjects", [
        ColumnSpec("subject_id"), ColumnSpec("name"), ColumnSpec("stage", False),
        ColumnSpec("duration_minutes", False, "int", 1)], ("subject_id",)),
    "student_subjects": TableSpec("student_subjects", [
        ColumnSpec("student_id"), ColumnSpec("subject_id"), ColumnSpec("exam_round", True, "int", 1)],
        ("student_id", "subject_id", "exam_round")),
    "schools": TableSpec("schools", [
        ColumnSpec("school_id"), ColumnSpec("name"), ColumnSpec("governorate"), ColumnSpec("district"),
        ColumnSpec("lat", False, "float", -90, 90), ColumnSpec("lng", False, "float", -180, 180),
        ColumnSpec("halls_count", True, "int", 0), ColumnSpec("hall_capacity", True, "int", 0),
        ColumnSpec("readiness_score", False, "float", 0, 100)], ("school_id",)),
    "school_halls": TableSpec("school_halls", [
        ColumnSpec("school_id"), ColumnSpec("hall_name"), ColumnSpec("capacity", True, "int", 1)],
        ("school_id", "hall_name")),
}


@dataclass
class ImportReport:
    kind: str
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)  # {"row": n, "error": msg}

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict:
        return {"kind": self.kind, "total_rows": self.total_rows, "inserted": self.inserted,
                "updated": self.updated, "skipped": self.skipped, "errors": len(self.errors)}


def read_table(path: str | Path, sheet: str | int | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0, dtype=str)
    return pd.read_csv(path, dtype=str)


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() == "")


def _coerce(col: ColumnSpec, raw):
    if _is_blank(raw):
        if col.required:
            raise ValueError(f"{col.name} is required")
        return None
    if col.kind == "str":
        return str(raw).strip()
    try:
        num = float(str(raw).strip())
    except ValueError as e:
        raise ValueError(f"{col.name} must be a number, got {raw!r}") from e
    if col.kind == "int":
        if abs(num - round(num)) > 1e-9:
            raise ValueError(f"{col.name} must be an integer, got {raw!r}")
        num = int(round(num))
    if col.min is not None and num < col.min:
        raise ValueError(f"{col.name} must be >= {col.min:g}, got {num:g}")
    if col.max is not None and num > col.max:
        raise ValueError(f"{col.name} must be <= {col.max:g}, got {num:g}")
    return num


def validate_dataframe(spec: TableSpec, df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Return (clean_rows, errors). Column names are normalized to lower snake case."""
    df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
    missing = [c.name for c in spec.columns if c.required and c.name not in df.columns]
    if missing:
        return [], [{"row": 0, "error": f"missing required columns: {', '.join(missing)}"}]
    clean, errors, seen = [], [], set()
    for i, raw in enumerate(df.to_dict("records"), start=2):  # 2 = first data row in a spreadsheet
        try:
            row = {c.name: _coerce(c, raw.get(c.name)) for c in spec.columns}
        except ValueError as e:
            errors.append({"row": i, "error": str(e)})
            continue
        key = tuple(row[k] for k in spec.key)
        if key in seen:
            errors.append({"row": i, "error": f"duplicate key {key} in file"})
            continue
        seen.add(key)
        clean.append(row)
    return clean, errors


def _chunks(seq, n=500):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _upsert(session: Session, model, pk_cols: tuple[str, ...], rows: list[dict], rep: ImportReport):
    """Batch upsert: existing rows are fetched in chunks by key, then updated; the rest are inserted."""
    cols = [getattr(model, c) for c in pk_cols]
    existing: dict[tuple, object] = {}
    if len(pk_cols) == 1:
        keys = [r[pk_cols[0]] for r in rows]
        for chunk in _chunks(keys):
            for obj in session.execute(select(model).where(cols[0].in_(chunk))).scalars():
                existing[(getattr(obj, pk_cols[0]),)] = obj
    else:
        first_keys = sorted({r[pk_cols[0]] for r in rows})
        for chunk in _chunks(first_keys):
            for obj in session.execute(select(model).where(cols[0].in_(chunk))).scalars():
                existing[tuple(getattr(obj, c) for c in pk_cols)] = obj
    for row in rows:
        obj = existing.get(tuple(row[k] for k in pk_cols))
        if obj is None:
            session.add(model(**row))
            rep.inserted += 1
        else:
            for k, v in row.items():
                setattr(obj, k, v)
            rep.updated += 1
    session.flush()


def import_dataframe(session: Session, kind: str, df: pd.DataFrame) -> ImportReport:
    spec = SPECS[kind]
    rep = ImportReport(kind, total_rows=len(df))
    rows, rep.errors = validate_dataframe(spec, df)

    if kind == "students":
        for r in rows:
            r["status"] = r["status"] or "active"
        _upsert(session, Student, spec.key, rows, rep)
    elif kind == "subjects":
        for r in rows:
            r["duration_minutes"] = r["duration_minutes"] or 180
        _upsert(session, Subject, spec.key, rows, rep)
    elif kind == "student_subjects":
        known_students = set(session.execute(select(Student.student_id)).scalars())
        known_subjects = set(session.execute(select(Subject.subject_id)).scalars())
        ok_rows = []
        for r in rows:
            if r["student_id"] not in known_students:
                rep.errors.append({"row": None, "error": f"unknown student_id {r['student_id']}"})
            elif r["subject_id"] not in known_subjects:
                rep.errors.append({"row": None, "error": f"unknown subject_id {r['subject_id']}"})
            else:
                ok_rows.append(r)
        _upsert(session, StudentSubject, spec.key, ok_rows, rep)
    elif kind == "schools":
        for r in rows:
            r.setdefault("is_approved", False)
        _upsert(session, School, spec.key, rows, rep)
    elif kind == "school_halls":
        known = set(session.execute(select(School.school_id)).scalars())
        ok_rows = [r for r in rows if r["school_id"] in known]
        for r in rows:
            if r["school_id"] not in known:
                rep.errors.append({"row": None, "error": f"unknown school_id {r['school_id']}"})
        _upsert(session, SchoolHall, spec.key, ok_rows, rep)
    else:
        raise ValueError(f"unknown import kind {kind}")
    rep.skipped = rep.total_rows - rep.inserted - rep.updated
    return rep


def import_file(session: Session, kind: str, path: str | Path, sheet: str | int | None = None) -> ImportReport:
    return import_dataframe(session, kind, read_table(path, sheet))
