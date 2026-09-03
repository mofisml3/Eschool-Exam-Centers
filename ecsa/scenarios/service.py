"""Scenario service: loads data, runs the engines in order, persists the
result, and stores a snapshot of the parameters used (rule 4 in CLAUDE.md).

Pipeline:  load → parameters → rank schools → decide centers → seed halls
           → schedule → allocate → number seats → validate → KPIs → persist
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ecsa.db.models import Assignment, Center, Hall, Scenario, School, SchoolHall, Session as ExamSession, Student, StudentSubject
from ecsa.engines import allocation, capacity, kpi, ranking, scheduling, seating, validation
from ecsa.engines.geo import DistanceResolver
from ecsa.engines.types import CenterRec, HallRec, SchoolRec, StudentRec
from ecsa.parameters.store import ParameterSet, ParameterStore


class ScenarioError(RuntimeError):
    pass


@dataclass
class RunRequest:
    name: str
    governorate: str
    exam_round: int
    round_start_date: date
    param_overrides: dict = field(default_factory=dict)
    include_schools: list[str] = field(default_factory=list)   # forced in (still must be eligible)
    exclude_schools: list[str] = field(default_factory=list)   # forced out
    as_of: date | None = None


# ---- loaders -------------------------------------------------------------

def load_students(s: Session, governorate: str, exam_round: int) -> list[StudentRec]:
    rows = s.execute(select(Student).where(Student.governorate == governorate, Student.status == "active")).scalars().all()
    subs = s.execute(select(StudentSubject.student_id, StudentSubject.subject_id)
                     .join(Student, Student.student_id == StudentSubject.student_id)
                     .where(Student.governorate == governorate, StudentSubject.exam_round == exam_round)).all()
    by_student: dict[str, list[str]] = defaultdict(list)
    for sid, subj in subs:
        by_student[sid].append(subj)
    return [StudentRec(r.student_id, r.district, sorted(by_student.get(r.student_id, [])), r.lat, r.lng, r.gender)
            for r in rows if by_student.get(r.student_id)]


def load_schools(s: Session, governorate: str) -> tuple[list[SchoolRec], dict[str, list[SchoolHall]]]:
    rows = s.execute(select(School).where(School.governorate == governorate)).scalars().all()
    halls = s.execute(select(SchoolHall).join(School).where(School.governorate == governorate)).scalars().all()
    by_school: dict[str, list[SchoolHall]] = defaultdict(list)
    for h in halls:
        by_school[h.school_id].append(h)
    recs = []
    for r in rows:
        real = by_school.get(r.school_id)
        halls_count = len(real) if real else r.halls_count
        hall_cap = (round(sum(h.capacity for h in real) / len(real)) if real else r.hall_capacity)
        recs.append(SchoolRec(r.school_id, r.name, r.district, halls_count, hall_cap, r.readiness_score, r.lat, r.lng))
    return recs, by_school


def seed_halls(school: SchoolRec, real_halls: list[SchoolHall] | None, params: ParameterSet) -> list[HallRec]:
    """Decision D8: real per-hall data wins; otherwise halls_count × hall_capacity."""
    rate = params.float("safe_utilization_rate")
    if real_halls:
        return [HallRec(f"{school.school_id}:{h.hall_name}", h.hall_name, h.capacity, capacity.hall_safe_capacity(h.capacity, rate))
                for h in sorted(real_halls, key=lambda x: x.hall_name)]
    return [HallRec(f"{school.school_id}:H{i}", f"H{i}", school.hall_capacity, capacity.hall_safe_capacity(school.hall_capacity, rate))
            for i in range(1, school.halls_count + 1)]


# ---- ranking + decision (shared by run and preview) ------------------------

def rank_and_decide(students, schools, params, geo, include_schools=(), exclude_schools=()):
    excluded = set(exclude_schools)
    ranked = ranking.rank_schools([sc for sc in schools if sc.school_id not in excluded], students, params, geo)
    if include_schools:  # forced schools go to the top, in the given order, if eligible
        forced = {sid: i for i, sid in enumerate(include_schools)}
        ranked.sort(key=lambda r: (0 if (r.eligible and r.school.school_id in forced) else 1,
                                   forced.get(r.school.school_id, 10**9), r.rank or 10**9))
        for i, r in enumerate([x for x in ranked if x.eligible], start=1):
            r.rank = i
    cases = capacity.exam_cases(students)
    cands = [capacity.CandidateCapacity(r.school.school_id,
                                        capacity.center_round_capacity(r.school.raw_capacity_per_session, params), r.score)
             for r in ranked if r.eligible]
    return ranked, capacity.decide_centers(cases, cands, params), cases


def ranking_rows(ranked) -> list[dict]:
    return [{"school_id": r.school.school_id, "name": r.school.name, "district": r.school.district, "eligible": r.eligible,
             "rank": r.rank, "score": round(r.score, 4), "exclusion_reason": r.exclusion_reason, **r.factors} for r in ranked]


def decision_rows(d: capacity.CenterDecision) -> dict:
    return {"exam_cases": d.exam_cases, "avg_center_round_capacity": round(d.avg_center_round_capacity, 1),
            "primary": d.primary, "supporting": d.supporting, "reserve": d.reserve, "main_capacity": d.main_capacity,
            "projected_utilization": round(d.projected_utilization, 4) if d.main_capacity else None,
            "capacity_shortfall": d.capacity_shortfall, "reserve_shortfall": d.reserve_shortfall, "notes": d.notes}


def preview_decision(s: Session, governorate: str, exam_round: int, param_overrides: dict | None = None,
                     include_schools=(), exclude_schools=(), as_of: date | None = None) -> dict:
    """Screen 3: ranking + center decision without persisting anything."""
    params = ParameterStore(s).resolve(governorate, as_of).with_overrides(param_overrides or {})
    students = load_students(s, governorate, exam_round)
    schools, _ = load_schools(s, governorate)
    if not students or not schools:
        raise ScenarioError("students with subjects and candidate schools are both required")
    geo = DistanceResolver(params.float("unknown_distance_km"), [*students, *schools])
    ranked, decision, cases = rank_and_decide(students, schools, params, geo, include_schools, exclude_schools)
    return {"governorate": governorate, "exam_round": exam_round, "students": len(students), "exam_cases": cases,
            "ranking": ranking_rows(ranked), "decision": decision_rows(decision), "params": params.snapshot()}


def data_summary(s: Session, governorate: str | None = None) -> dict:
    """Counts for the import screen."""
    from sqlalchemy import func
    q_students = select(func.count()).select_from(Student)
    q_schools = select(func.count()).select_from(School)
    q_cases = select(StudentSubject.exam_round, func.count()).join(Student, Student.student_id == StudentSubject.student_id)
    if governorate:
        q_students = q_students.where(Student.governorate == governorate)
        q_schools = q_schools.where(School.governorate == governorate)
        q_cases = q_cases.where(Student.governorate == governorate)
    cases = dict(s.execute(q_cases.group_by(StudentSubject.exam_round)).all())
    governorates = sorted(set(s.execute(select(Student.governorate).distinct()).scalars()) | set(s.execute(select(School.governorate).distinct()).scalars()))
    return {"governorate": governorate, "students": s.execute(q_students).scalar(), "schools": s.execute(q_schools).scalar(),
            "exam_cases_by_round": {int(k): v for k, v in cases.items()}, "governorates": governorates}


# ---- main run ------------------------------------------------------------

def run_scenario(s: Session, req: RunRequest) -> Scenario:
    params = ParameterStore(s).resolve(req.governorate, req.as_of).with_overrides(req.param_overrides)
    students = load_students(s, req.governorate, req.exam_round)
    schools, school_halls = load_schools(s, req.governorate)
    if not students:
        raise ScenarioError(f"no students with subjects for governorate={req.governorate!r} round={req.exam_round}")
    if not schools:
        raise ScenarioError(f"no candidate schools for governorate={req.governorate!r}")

    scenario = Scenario(name=req.name, governorate=req.governorate, exam_round=req.exam_round,
                        round_start_date=req.round_start_date, status="draft", params_snapshot=params.snapshot(),
                        created_at=datetime.utcnow())
    s.add(scenario)
    s.flush()
    log: dict = {"request": {"include_schools": req.include_schools, "exclude_schools": req.exclude_schools,
                             "param_overrides": {k: str(v) for k, v in req.param_overrides.items()}}}

    # 1–2. ranking and decision (خ1–خ4, D1, D2)
    geo = DistanceResolver(params.float("unknown_distance_km"), [*students, *schools])
    ranked, decision, cases = rank_and_decide(students, schools, params, geo, req.include_schools, req.exclude_schools)
    eligible = [r for r in ranked if r.eligible]
    log["ranking"] = ranking_rows(ranked)
    log["excluded_by_request"] = sorted(set(req.exclude_schools))
    log["decision"] = decision_rows(decision)

    # 3. persist centers + halls (D8)
    school_by_id = {sc.school_id: sc for sc in schools}
    rank_of = {r.school.school_id: r for r in eligible}
    centers: list[CenterRec] = []
    for category, ids in (("primary", decision.primary), ("supporting", decision.supporting), ("reserve", decision.reserve)):
        for sid in ids:
            sc = school_by_id[sid]
            active = category != "reserve"
            c = Center(scenario_id=scenario.scenario_id, school_id=sid, governorate=req.governorate, category=category,
                       activation_status="active" if active else "inactive", rank=rank_of[sid].rank, score=rank_of[sid].score)
            s.add(c)
            s.flush()
            halls = []
            for h in seed_halls(sc, school_halls.get(sid), params):
                row = Hall(center_id=c.center_id, hall_name=h.hall_name, capacity=h.capacity, safe_capacity=h.safe_capacity)
                s.add(row)
                s.flush()
                halls.append(HallRec(row.hall_id, h.hall_name, h.capacity, h.safe_capacity))
            centers.append(CenterRec(c.center_id, sid, sc.name, sc.district, category, active, halls, sc.lat, sc.lng))
    if not any(c.active for c in centers):
        scenario.status = "failed"
        scenario.decision_log = log
        scenario.kpi_summary = {"error": "no active centers could be selected"}
        s.flush()
        return scenario

    # 4. schedule (خ5)
    seats_per_slot = sum(c.safe_seats_per_slot for c in centers if c.active)
    try:
        schedule = scheduling.generate_schedule(students, req.round_start_date, params, seats_per_slot)
    except scheduling.SchedulingError as e:
        raise ScenarioError(f"scheduling failed: {e}") from e
    session_ids: dict = {}
    for sess in schedule.sessions:
        row = ExamSession(scenario_id=scenario.scenario_id, exam_round=req.exam_round, exam_date=sess.slot.exam_date,
                          session_no=sess.slot.session_no, subject_id=sess.subject_id)
        s.add(row)
        s.flush()
        session_ids[sess.session_id] = row.session_id
        sess.session_id = row.session_id
    log["schedule"] = {"slots": len(schedule.slots), "sessions": len(schedule.sessions), "groups": schedule.groups,
                       "sittings_per_subject": dict(schedule.sittings_per_subject), "warnings": schedule.warnings}

    # 5. allocate, seat, validate (خ6–خ8)
    result = allocation.allocate(students, centers, schedule, params, geo)
    seating.number_seats(result.assignments, students)
    report = validation.validate(students, centers, result.assignments)
    log["allocation"] = {"assigned": result.assigned_count, "unassigned": len(result.unassigned),
                         "unassigned_sample": [u.__dict__ for u in result.unassigned[:100]],
                         "emergency_margin_used": result.margin_used, "day_limit_relaxed": result.day_limit_relaxed,
                         "not_nearest": result.not_nearest}
    log["validation"] = report.summary()

    if result.assignments:
        s.execute(insert(Assignment), [
            {"scenario_id": scenario.scenario_id, "student_id": a.student_id, "session_id": a.session_id,
             "center_id": a.center_id, "hall_id": a.hall_id, "seat_no": a.seat_no, "distance_km": a.distance_km, "note": a.note}
            for a in result.assignments])

    # 6. KPIs
    scenario.kpi_summary = kpi.compute_kpis(students, centers, schedule, result, params) | {"validation": report.summary()}
    scenario.decision_log = log
    scenario.status = "completed" if report.ok else "failed"
    s.flush()
    return scenario


# ---- management ----------------------------------------------------------

def list_scenarios(s: Session, governorate: str | None = None) -> list[Scenario]:
    q = select(Scenario).order_by(Scenario.created_at.desc())
    if governorate:
        q = q.where(Scenario.governorate == governorate)
    return list(s.execute(q).scalars().all())


def approve_scenario(s: Session, scenario_id: int) -> Scenario:
    sc = s.get(Scenario, scenario_id)
    if sc is None:
        raise ScenarioError(f"scenario {scenario_id} not found")
    if sc.status != "completed":
        raise ScenarioError(f"only completed scenarios can be approved (status={sc.status})")
    for other in s.execute(select(Scenario).where(Scenario.governorate == sc.governorate, Scenario.exam_round == sc.exam_round,
                                                  Scenario.status == "approved")).scalars():
        other.status = "completed"
    for school in s.execute(select(School).where(School.governorate == sc.governorate)).scalars():
        school.is_approved = False
    for c in s.execute(select(Center).where(Center.scenario_id == scenario_id)).scalars():
        c.school.is_approved = True
    sc.status = "approved"
    s.flush()
    return sc


def delete_scenario(s: Session, scenario_id: int) -> None:
    sc = s.get(Scenario, scenario_id)
    if sc is None:
        raise ScenarioError(f"scenario {scenario_id} not found")
    center_ids = select(Center.center_id).where(Center.scenario_id == scenario_id)
    s.execute(delete(Assignment).where(Assignment.scenario_id == scenario_id))
    s.execute(delete(ExamSession).where(ExamSession.scenario_id == scenario_id))
    s.execute(delete(Hall).where(Hall.center_id.in_(center_ids)))
    s.execute(delete(Center).where(Center.scenario_id == scenario_id))
    s.execute(delete(Scenario).where(Scenario.scenario_id == scenario_id))
    s.expire_all()


COMPARE_KEYS = ("exam_cases", "assigned", "unassigned", "coverage", "active_centers", "reserve_centers",
                "total_safe_seats", "overall_utilization", "utilization_in_target", "max_hall_slot_utilization",
                "mean_distance_km", "not_nearest_share", "emergency_margin_used", "day_limit_relaxed")


def compare_scenarios(s: Session, ids: list[int]) -> list[dict]:
    out = []
    for sid in ids:
        sc = s.get(Scenario, sid)
        if sc is None:
            raise ScenarioError(f"scenario {sid} not found")
        row = {"scenario_id": sc.scenario_id, "name": sc.name, "status": sc.status, "governorate": sc.governorate,
               "exam_round": sc.exam_round, "created_at": sc.created_at.isoformat()}
        row.update({k: sc.kpi_summary.get(k) for k in COMPARE_KEYS})
        row["params"] = sc.params_snapshot
        out.append(row)
    if len(out) > 1:  # mark which parameters differ
        keys = set().union(*(set(r["params"]) for r in out))
        diff = {k for k in keys if len({r["params"].get(k) for r in out}) > 1}
        for r in out:
            r["params_diff"] = {k: r["params"].get(k) for k in sorted(diff)}
    return out
