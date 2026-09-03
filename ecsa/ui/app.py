"""Streamlit UI — the six screens required by the specification.

    streamlit run ecsa/ui/app.py

1) Import data  2) Parameters  3) Candidate & approved centers
4) Run distribution  5) Compare scenarios  6) Reports & sheets
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Streamlit Community Cloud runs the script from ecsa/ui without installing the
# package, so make the repository root importable first.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

# Streamlit Community Cloud passes settings through st.secrets; export them as
# environment variables before ecsa.config reads them.
try:
    for _k in ("ECSA_DATABASE_URL", "DATABASE_URL"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # no secrets file locally
    pass

from ecsa import config  # noqa: E402
from ecsa.db.session import init_db, session_scope  # noqa: E402
from ecsa.importer import SPECS, import_dataframe
from ecsa.parameters.store import ParameterStore
from ecsa.reports import (assignments_frame, attendance_sheets, center_distribution, export_scenario_excel, student_cards,
                          utilization_frames)
from ecsa.scenarios import (RunRequest, ScenarioError, approve_scenario, compare_scenarios, data_summary, delete_scenario,
                            list_scenarios, preview_decision, run_scenario)
from ecsa.tools.sample_data import generate

st.set_page_config(page_title="ECSA — Exam Centers & Student Allocation", layout="wide")
init_db()


def _governorates() -> list[str]:
    with session_scope() as s:
        return data_summary(s)["governorates"]


def _sidebar() -> tuple[str | None, int]:
    st.sidebar.title("ECSA")
    govs = _governorates()
    gov = st.sidebar.selectbox("Governorate", govs, index=0 if govs else None, placeholder="import data first")
    rnd = st.sidebar.number_input("Exam round", min_value=1, value=1, step=1)
    return gov, int(rnd)


# ---- 0. home ---------------------------------------------------------------

JOURNEY = [
    ("1 · Import data", "Upload students, subjects, student-subjects and candidate schools (or load the demo data below)."),
    ("2 · Parameters", "Every operational value: days per round, sessions per day, safe utilization, reserve ratio, weights…"),
    ("3 · Centers", "See how schools are ranked and which become primary, supporting or reserve centers. Adjust and preview."),
    ("4 · Run distribution", "Build the timetable and seat every student: center → hall → session → seat. Saved as a scenario."),
    ("5 · Compare scenarios", "Run again with different parameters, compare KPIs side by side, approve the one you want."),
    ("6 · Reports & sheets", "Attendance sheets per hall, student exam cards, utilization dashboards, Excel export."),
]


def screen_home(gov):
    st.header("Exam Centers & Student Allocation — MVP")
    st.write("From raw student lists to a seat number for every student in every subject, with every decision explained.")
    db_kind = config.DATABASE_URL.split("://", 1)[0]
    if config.EPHEMERAL_STORAGE:
        st.warning("Running on temporary storage: data disappears on restart. Attach a PostgreSQL database.")
    else:
        st.caption(f"Database: {db_kind} · source: {config.DATABASE_URL_SOURCE}")
    st.subheader("The journey")
    for name, desc in JOURNEY:
        st.markdown(f"**{name}** — {desc}")
    st.subheader("Try it with demo data")
    with session_scope() as s:
        summary = data_summary(s)
    if summary["students"]:
        st.info(f"Data already loaded: {summary['students']:,} students, {summary['schools']} schools, "
                f"governorates: {', '.join(summary['governorates'])}. Use the sidebar to move through the screens.")
    c1, c2, c3 = st.columns(3)
    n_students = c1.select_slider("Students", [500, 1000, 2000, 5000, 10000], value=2000)
    n_schools = c2.slider("Candidate schools", 5, 30, 12)
    gov_name = c3.text_input("Governorate name", value="Basra")
    if st.button("Load demo data", type="primary"):
        with st.spinner("Generating and importing…"):
            files = generate(Path(tempfile.mkdtemp()), governorate=gov_name, students=int(n_students), schools=int(n_schools))
            with session_scope() as s:
                reports = {k: import_dataframe(s, k, pd.read_csv(files[k], dtype=str)).summary()
                           for k in ("students", "subjects", "student_subjects", "schools")}
        st.success("Demo data loaded. Next: screen 3 to see the center decision, then screen 4 to run the distribution.")
        st.json(reports)
        st.rerun()


# ---- 1. import -----------------------------------------------------------

def screen_import(gov):
    st.header("1 · Import data")
    st.caption("Upload CSV or Excel files. Column names must match the specification; rows with errors are skipped and listed.")
    kind = st.selectbox("Table", list(SPECS), format_func=lambda k: f"{k}  ({', '.join(c.name for c in SPECS[k].columns if c.required)})")
    up = st.file_uploader("File", type=["csv", "xlsx"])
    if up and st.button("Import", type="primary"):
        df = pd.read_excel(up, dtype=str) if up.name.lower().endswith("xlsx") else pd.read_csv(up, dtype=str)
        with session_scope() as s:
            rep = import_dataframe(s, kind, df)
        st.json(rep.summary())
        if rep.errors:
            st.dataframe(pd.DataFrame(rep.errors), use_container_width=True)
    with session_scope() as s:
        st.subheader("Current data")
        st.json(data_summary(s, gov))


# ---- 2. parameters -----------------------------------------------------------

def screen_parameters(gov):
    st.header("2 · Parameters")
    st.caption("Every operational value the engines use. Governorate-specific rows override global ones; the latest effective date wins.")
    with session_scope() as s:
        store = ParameterStore(s)
        resolved = store.resolve(gov)
        rows = store.list_all(gov)
        df = pd.DataFrame([{"param_key": p.param_key, "value": p.param_value, "unit": p.unit, "governorate": p.governorate or "(global)",
                            "effective_from": p.effective_from, "description": p.description} for p in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.subheader(f"Set a value{' for ' + gov if gov else ''}")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    key = c1.selectbox("Parameter", sorted(resolved.values), key="p_key")
    val = c2.text_input("New value", value=resolved.values.get(key, ""), key="p_val")
    scope = c3.selectbox("Scope", ["governorate", "global"] if gov else ["global"])
    eff = c4.date_input("Effective from", value=date.today())
    if st.button("Save parameter", type="primary"):
        with session_scope() as s:
            ParameterStore(s).set(key, val, governorate=gov if scope == "governorate" else None, effective_from=eff)
        st.success(f"{key} = {val} ({scope}) from {eff}")
        st.rerun()


# ---- 3. centers ---------------------------------------------------------------

def _overrides_editor(resolved: dict, keys: list[str]) -> dict:
    over = {}
    cols = st.columns(len(keys))
    for c, k in zip(cols, keys):
        v = c.text_input(k, value=resolved.get(k, ""), key=f"ov_{k}")
        if v != resolved.get(k, ""):
            over[k] = v
    return over


def screen_centers(gov, rnd):
    st.header("3 · Candidate & approved centers")
    if not gov:
        st.info("Import data first.")
        return
    with session_scope() as s:
        resolved = ParameterStore(s).resolve(gov).snapshot()
    over = _overrides_editor(resolved, ["safe_utilization_rate", "min_readiness_score", "reserve_center_ratio", "target_utilization_max"])
    exclude = st.text_input("Exclude schools (comma-separated ids)")
    include = st.text_input("Force-include schools (comma-separated ids, in priority order)")
    try:
        with session_scope() as s:
            prev = preview_decision(s, gov, rnd, over, [x.strip() for x in include.split(",") if x.strip()],
                                    [x.strip() for x in exclude.split(",") if x.strip()])
    except ScenarioError as e:
        st.error(str(e))
        return
    d = prev["decision"]
    m = st.columns(5)
    m[0].metric("Exam cases", f"{prev['exam_cases']:,}")
    m[1].metric("Primary", len(d["primary"]))
    m[2].metric("Supporting", len(d["supporting"]))
    m[3].metric("Reserve", len(d["reserve"]))
    m[4].metric("Projected utilization", f"{(d['projected_utilization'] or 0) * 100:.1f}%")
    for n in d["notes"]:
        st.warning(n)
    rk = pd.DataFrame(prev["ranking"])
    cat = {sid: "primary" for sid in d["primary"]} | {sid: "supporting" for sid in d["supporting"]} | {sid: "reserve" for sid in d["reserve"]}
    rk.insert(0, "category", rk["school_id"].map(cat).fillna(""))
    st.dataframe(rk.drop(columns=["weights"], errors="ignore"), use_container_width=True, hide_index=True)
    st.caption("To approve, run the distribution on screen 4 and approve the resulting scenario on screen 5.")


# ---- 4. run ---------------------------------------------------------------------

def screen_run(gov, rnd):
    st.header("4 · Run distribution")
    if not gov:
        st.info("Import data first.")
        return
    with session_scope() as s:
        resolved = ParameterStore(s).resolve(gov).snapshot()
    name = st.text_input("Scenario name", value=f"{gov} R{rnd} {date.today():%Y-%m-%d}")
    start = st.date_input("Round start date", value=date.today())
    st.caption("Optional overrides for this run only (saved in the scenario snapshot):")
    over = _overrides_editor(resolved, ["operating_days_per_round", "sessions_per_day", "safe_utilization_rate", "max_exams_per_student_per_day"])
    if st.button("Run", type="primary"):
        with st.spinner("Ranking, scheduling and allocating…"):
            try:
                with session_scope() as s:
                    sc = run_scenario(s, RunRequest(name, gov, rnd, start, over))
                    sid, status, k, log = sc.scenario_id, sc.status, sc.kpi_summary, sc.decision_log
            except ScenarioError as e:
                st.error(str(e))
                return
        (st.success if status == "completed" else st.error)(f"Scenario {sid} — {status}")
        _kpi_row(k)
        for n in log.get("decision", {}).get("notes", []) + log.get("schedule", {}).get("warnings", []):
            st.warning(n)
        st.json({k2: v for k2, v in k.items() if not isinstance(v, (list, dict))})


def _kpi_row(k: dict):
    m = st.columns(6)
    m[0].metric("Assigned", f"{k.get('assigned', 0):,}", f"{k.get('unassigned', 0)} unassigned", delta_color="inverse")
    m[1].metric("Coverage", f"{k.get('coverage', 0) * 100:.1f}%")
    m[2].metric("Active centers", k.get("active_centers"))
    m[3].metric("Utilization", f"{k.get('overall_utilization', 0) * 100:.1f}%", "in target" if k.get("utilization_in_target") else "out of target")
    m[4].metric("Mean distance", f"{k.get('mean_distance_km') or 0:.1f} km")
    m[5].metric("Not nearest", f"{k.get('not_nearest_share', 0) * 100:.1f}%")


# ---- 5. compare -----------------------------------------------------------------

def screen_compare(gov):
    st.header("5 · Compare scenarios")
    with session_scope() as s:
        scs = list_scenarios(s, gov)
        options = {f"#{x.scenario_id} {x.name} [{x.status}]": x.scenario_id for x in scs}
    if not options:
        st.info("No scenarios yet.")
        return
    chosen = st.multiselect("Scenarios", list(options), default=list(options)[:2])
    ids = [options[c] for c in chosen]
    if ids:
        with session_scope() as s:
            rows = compare_scenarios(s, ids)
        table = pd.DataFrame([{k: v for k, v in r.items() if k not in ("params", "params_diff")} for r in rows]).set_index("scenario_id").T
        st.dataframe(table, use_container_width=True)
        if len(rows) > 1:
            st.subheader("Parameters that differ")
            st.dataframe(pd.DataFrame({r["scenario_id"]: r["params_diff"] for r in rows}), use_container_width=True)
    c1, c2 = st.columns(2)
    target = c1.selectbox("Scenario", list(options), key="cmp_target")
    if c2.button("Approve", type="primary"):
        with session_scope() as s:
            try:
                approve_scenario(s, options[target])
                st.success("approved; its schools are now marked is_approved")
            except ScenarioError as e:
                st.error(str(e))
    if c2.button("Delete"):
        with session_scope() as s:
            delete_scenario(s, options[target])
        st.rerun()


# ---- 6. reports -----------------------------------------------------------------

def screen_reports(gov):
    st.header("6 · Reports & sheets")
    with session_scope() as s:
        scs = list_scenarios(s, gov)
        options = {f"#{x.scenario_id} {x.name} [{x.status}]": x.scenario_id for x in scs}
    if not options:
        st.info("No scenarios yet.")
        return
    sid = options[st.selectbox("Scenario", list(options))]
    with session_scope() as s:
        sc = next(x for x in scs if x.scenario_id == sid)
        df = assignments_frame(s, sid)
        util = utilization_frames(s, sid, df)
    _kpi_row(sc.kpi_summary)
    tabs = st.tabs(["Utilization", "Centers", "Attendance sheet", "Student card", "Distribution", "Decision log", "Export"])
    with tabs[0]:
        st.subheader("Per center")
        st.dataframe(util["centers"], use_container_width=True, hide_index=True)
        st.subheader("Per slot")
        if not util["slots"].empty:
            st.bar_chart(util["slots"].set_index("slot")["utilization"])
        st.subheader("Per hall")
        st.dataframe(util["halls"], use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(pd.DataFrame(sc.kpi_summary.get("centers", [])), use_container_width=True, hide_index=True)
    with tabs[2]:
        sheets = attendance_sheets(df)
        if sheets:
            key = st.selectbox("Hall session", list(sheets), format_func=lambda k: f"{k[0]} · session {k[1]} · {k[2]} · {k[3]}")
            st.dataframe(sheets[key], use_container_width=True, hide_index=True)
    with tabs[3]:
        cards = student_cards(df)
        sid_q = st.text_input("Student id")
        if sid_q and not cards.empty:
            st.dataframe(cards[cards["student_id"] == sid_q.strip()], use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(center_distribution(df), use_container_width=True, hide_index=True)
    with tabs[5]:
        st.json(sc.decision_log)
    with tabs[6]:
        att = st.checkbox("Include attendance sheets (larger file)")
        if st.button("Build Excel workbook"):
            buf = io.BytesIO()
            out = Path(tempfile.mkdtemp()) / f"scenario_{sid}.xlsx"
            with session_scope() as s:
                export_scenario_excel(s, sid, out, att)
            buf.write(out.read_bytes())
            st.download_button("Download", buf.getvalue(), file_name=out.name,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def main():
    gov, rnd = _sidebar()
    screen = st.sidebar.radio("Screen", ["0 · Home", "1 · Import data", "2 · Parameters", "3 · Centers", "4 · Run distribution",
                                         "5 · Compare scenarios", "6 · Reports & sheets"])
    {"0": lambda: screen_home(gov), "1": lambda: screen_import(gov), "2": lambda: screen_parameters(gov),
     "3": lambda: screen_centers(gov, rnd), "4": lambda: screen_run(gov, rnd), "5": lambda: screen_compare(gov),
     "6": lambda: screen_reports(gov)}[screen[0]]()


main()
