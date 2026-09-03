from datetime import date

import pytest

from ecsa.engines.scheduling import (SchedulingError, build_slots, conflict_groups, generate_schedule,
                                     parse_rest_weekdays, subject_demand)
from ecsa.engines.types import StudentRec
from ecsa.parameters.store import ParameterSet, load_default_definitions


@pytest.fixture()
def params():
    return ParameterSet({d["param_key"]: d["param_value"] for d in load_default_definitions()})


def test_slots_count_is_days_times_sessions(params):
    slots = build_slots(date(2026, 3, 1), params)
    assert len(slots) == 40 * 4
    assert slots[0].exam_date == date(2026, 3, 1) and slots[0].session_no == 1
    assert slots[-1].session_no == 4


def test_rest_weekdays_are_skipped(params):
    p = params.with_overrides({"rest_weekdays": "4,5", "operating_days_per_round": 5, "sessions_per_day": 1})
    slots = build_slots(date(2026, 3, 2), p)  # Monday
    assert [s.exam_date.weekday() for s in slots] == [0, 1, 2, 3, 6]


def test_parse_rest_weekdays():
    assert parse_rest_weekdays("") == set()
    assert parse_rest_weekdays("4, 5") == {4, 5}


def test_conflict_groups_separate_shared_subjects():
    students = [StudentRec("a", "D", ["M", "P"]), StudentRec("b", "D", ["M", "C"]), StudentRec("c", "D", ["X"])]
    groups = conflict_groups(students)
    flat = {s for g in groups for s in g}
    assert flat == {"M", "P", "C", "X"}
    for g in groups:
        assert not ({"M", "P"} <= set(g)) and not ({"M", "C"} <= set(g))
    # P and C never share a student and X shares with nobody, so they can co-exist
    assert len(groups) == 2


def test_no_student_has_two_subjects_in_same_slot(params):
    students = [StudentRec(f"s{i}", "D", [f"SUB{j}" for j in range(7)]) for i in range(30)]
    sched = generate_schedule(students, date(2026, 3, 1), params)
    by_slot = {}
    for s in sched.sessions:
        by_slot.setdefault(s.slot, set()).add(s.subject_id)
    for st in students:
        for slot, subs in by_slot.items():
            assert len(set(st.subjects) & subs) <= 1
    assert len(sched.groups) == 7
    assert min(sched.sittings_per_subject.values()) >= 160 // 7


def test_two_stages_share_slots(params):
    stage1 = [StudentRec(f"a{i}", "D", ["A1", "A2"]) for i in range(5)]
    stage2 = [StudentRec(f"b{i}", "D", ["B1", "B2"]) for i in range(5)]
    sched = generate_schedule(stage1 + stage2, date(2026, 3, 1), params)
    assert len(sched.groups) == 2  # {A1,B1} and {A2,B2}
    assert all(len(g) == 2 for g in sched.groups)


def test_too_many_groups_for_slots_raises(params):
    p = params.with_overrides({"operating_days_per_round": 1, "sessions_per_day": 2})
    students = [StudentRec("a", "D", ["A", "B", "C"])]
    with pytest.raises(SchedulingError):
        generate_schedule(students, date(2026, 3, 1), p)


def test_capacity_warning_when_sittings_insufficient(params):
    p = params.with_overrides({"operating_days_per_round": 1, "sessions_per_day": 1})
    students = [StudentRec(f"s{i}", "D", ["A"]) for i in range(50)]
    sched = generate_schedule(students, date(2026, 3, 1), p, seats_per_slot=20)
    assert sched.warnings and "subject A" in sched.warnings[0]


def test_subject_demand():
    assert subject_demand([StudentRec("a", "D", ["A", "B"]), StudentRec("b", "D", ["A"])]) == {"A": 2, "B": 1}
