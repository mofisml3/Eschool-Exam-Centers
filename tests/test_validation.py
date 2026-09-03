from datetime import date

from ecsa.engines.types import AssignmentRec, Slot, StudentRec
from ecsa.engines.validation import validate
from tests.helpers import make_center

SLOT = Slot(date(2026, 3, 1), 1)


def _a(student, subject, hall="1-H1", seat=1, slot=SLOT):
    return AssignmentRec(student, 1, subject, slot, 1, hall, seat_no=seat)


def test_detects_missing_and_duplicate():
    students = [StudentRec("s1", "D", ["A", "B"])]
    rep = validate(students, [make_center(1, "D")], [_a("s1", "A", seat=1), _a("s1", "A", seat=2)])
    assert rep.missing == [("s1", "B")] and rep.duplicates == [("s1", "A")]


def test_detects_over_capacity():
    students = [StudentRec(f"s{i}", "D", ["A"]) for i in range(22)]
    rows = [_a(f"s{i}", "A", seat=i + 1) for i in range(22)]  # hall safe capacity is 21
    rep = validate(students, [make_center(1, "D", halls=1)], rows)
    assert len(rep.over_capacity) == 1 and rep.over_capacity[0]["assigned"] == 22


def test_detects_clash_and_seat_conflict():
    students = [StudentRec("s1", "D", ["A", "B"]), StudentRec("s2", "D", ["A"])]
    rows = [_a("s1", "A", seat=1), _a("s1", "B", seat=2), _a("s2", "A", seat=1)]
    rep = validate(students, [make_center(1, "D")], rows)
    assert rep.clashes == [("s1", str(SLOT))]
    assert len(rep.seat_conflicts) == 1


def test_ok_report():
    students = [StudentRec("s1", "D", ["A"])]
    rep = validate(students, [make_center(1, "D")], [_a("s1", "A")])
    assert rep.ok and rep.summary()["ok"]
