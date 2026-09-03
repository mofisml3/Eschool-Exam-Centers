import time
from collections import Counter

from ecsa.engines.allocation import allocate
from ecsa.engines.scheduling import generate_schedule
from ecsa.engines.seating import number_seats
from ecsa.engines.validation import validate
from tests.helpers import START, default_params, make_center, make_students


def _run(students, centers, params):
    sched = generate_schedule(students, START, params)
    res = allocate(students, centers, sched, params)
    number_seats(res.assignments, students)
    return sched, res, validate(students, centers, res.assignments)


def test_everyone_seated_and_hard_constraints_hold():
    params = default_params(operating_days_per_round=4, sessions_per_day=2)
    students = make_students(60, ["D1", "D2"], ["A", "B", "C"])
    centers = [make_center(1, "D1", halls=2), make_center(2, "D2", halls=2)]
    sched, res, rep = _run(students, centers, params)
    assert rep.ok, rep.summary()
    assert res.assigned_count == 180 and not res.unassigned


def test_nearest_center_preferred():
    params = default_params(operating_days_per_round=6, sessions_per_day=2)
    students = make_students(20, ["D1"], ["A"]) + make_students(20, ["D2"], ["A"], prefix="t")
    centers = [make_center(1, "D1", halls=3), make_center(2, "D2", halls=3)]
    _, res, rep = _run(students, centers, params)
    assert rep.ok
    for a in res.assignments:
        student_district = "D1" if a.student_id.startswith("s") else "D2"
        assert a.center_id == (1 if student_district == "D1" else 2)
    assert res.not_nearest == 0


def test_overflow_redirects_to_other_center_with_note():
    # D1 has one tiny center (1 hall × 25 × 0.85 = 21 seats/slot, 2 slots) -> 42 seats; 60 students need 60
    params = default_params(operating_days_per_round=1, sessions_per_day=2, emergency_margin_rate=0)
    students = make_students(60, ["D1"], ["A"])
    centers = [make_center(1, "D1", halls=1), make_center(2, "D2", halls=3)]
    _, res, rep = _run(students, centers, params)
    assert rep.ok
    by_center = Counter(a.center_id for a in res.assignments)
    assert by_center[1] == 42 and by_center[2] == 18
    assert res.not_nearest == 18
    assert all("not nearest" in (a.note or "") for a in res.assignments if a.center_id == 2)


def test_unassigned_when_capacity_exhausted():
    params = default_params(operating_days_per_round=1, sessions_per_day=1)
    students = make_students(30, ["D1"], ["A"])
    centers = [make_center(1, "D1", halls=1)]  # 21 seats
    _, res, rep = _run(students, centers, params)
    assert res.assigned_count == 21 and len(res.unassigned) == 9
    assert not rep.ok and len(rep.missing) == 9
    assert not rep.over_capacity


def test_emergency_margin_kept_when_possible_and_used_when_needed():
    params = default_params(operating_days_per_round=1, sessions_per_day=1, emergency_margin_rate=0.10)
    # 1 hall safe 21, margin floor(2.1)=2 -> 19 normal seats
    centers = [make_center(1, "D1", halls=1)]
    _, res, _ = _run(make_students(19, ["D1"], ["A"]), centers, params)
    assert res.margin_used == 0
    _, res, rep = _run(make_students(21, ["D1"], ["A"]), centers, params)
    assert res.margin_used == 2 and rep.ok


def test_daily_limit_is_soft():
    # 1 day × 3 sessions, 3 subjects: the only way to seat everyone is 3 exams in one day
    params = default_params(operating_days_per_round=1, sessions_per_day=3, max_exams_per_student_per_day=1)
    students = make_students(5, ["D1"], ["A", "B", "C"])
    _, res, rep = _run(students, [make_center(1, "D1")], params)
    assert rep.ok and res.day_limit_relaxed == 10  # 2 extra exams/day × 5 students


def test_load_balance_between_equidistant_centers():
    params = default_params(operating_days_per_round=2, sessions_per_day=2)
    students = make_students(100, ["D1"], ["A"])
    centers = [make_center(1, "D1", halls=2), make_center(2, "D1", halls=2)]  # both 0 km
    _, res, rep = _run(students, centers, params)
    by_center = Counter(a.center_id for a in res.assignments)
    assert rep.ok and abs(by_center[1] - by_center[2]) <= 1


def test_seats_are_sequential_and_districts_interleaved():
    params = default_params(operating_days_per_round=1, sessions_per_day=1)
    students = make_students(10, ["D1"], ["A"]) + make_students(10, ["D2"], ["A"], prefix="t")
    _, res, rep = _run(students, [make_center(1, "D1", halls=1)], params)
    assert rep.ok
    seats = sorted(a.seat_no for a in res.assignments)
    assert seats == list(range(1, 21))
    ordered = sorted(res.assignments, key=lambda a: a.seat_no)
    districts = ["D1" if a.student_id.startswith("s") else "D2" for a in ordered]
    assert all(districts[i] != districts[i + 1] for i in range(len(districts) - 1))


def test_medium_scale_run_is_complete_and_fast():
    params = default_params()
    subjects = [f"SUB{j}" for j in range(7)]
    students = make_students(3000, ["D1", "D2", "D3", "D4"], subjects)
    # 3000 × 7 = 21,000 cases; each center 10 halls × 21 seats × 160 slots = 33,600 -> one center enough, use 2
    centers = [make_center(1, "D1", halls=10), make_center(2, "D3", halls=10)]
    t0 = time.perf_counter()
    sched, res, rep = _run(students, centers, params)
    elapsed = time.perf_counter() - t0
    assert rep.ok, rep.summary()
    assert res.assigned_count == 21_000
    assert elapsed < 30, f"took {elapsed:.1f}s"
