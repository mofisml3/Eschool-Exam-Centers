from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from ecsa.db.models import Assignment, Center, Hall, School, Scenario, Session as ExamSession, Student, Subject


def _fixture_world(db):
    db.add(Student(student_id="S1", full_name="A", governorate="G", district="D1"))
    db.add(Student(student_id="S2", full_name="B", governorate="G", district="D1"))
    db.add(Subject(subject_id="MATH", name="Math"))
    db.add(School(school_id="SC1", name="School", governorate="G", district="D1", halls_count=1, hall_capacity=25, readiness_score=80))
    sc = Scenario(name="t", governorate="G", exam_round=1, round_start_date=date(2026, 1, 1))
    db.add(sc)
    db.flush()
    c = Center(scenario_id=sc.scenario_id, school_id="SC1", governorate="G", category="primary")
    db.add(c)
    db.flush()
    h = Hall(center_id=c.center_id, hall_name="H1", capacity=25, safe_capacity=21)
    db.add(h)
    ses = ExamSession(scenario_id=sc.scenario_id, exam_round=1, exam_date=date(2026, 1, 1), session_no=1, subject_id="MATH")
    db.add(ses)
    db.flush()
    return sc, c, h, ses


def test_student_cannot_sit_twice_in_same_session(db):
    sc, c, h, ses = _fixture_world(db)
    db.add(Assignment(scenario_id=sc.scenario_id, student_id="S1", session_id=ses.session_id, center_id=c.center_id, hall_id=h.hall_id, seat_no=1))
    db.flush()
    db.add(Assignment(scenario_id=sc.scenario_id, student_id="S1", session_id=ses.session_id, center_id=c.center_id, hall_id=h.hall_id, seat_no=2))
    with pytest.raises(IntegrityError):
        db.flush()


def test_seat_cannot_be_used_twice(db):
    sc, c, h, ses = _fixture_world(db)
    db.add(Assignment(scenario_id=sc.scenario_id, student_id="S1", session_id=ses.session_id, center_id=c.center_id, hall_id=h.hall_id, seat_no=1))
    db.flush()
    db.add(Assignment(scenario_id=sc.scenario_id, student_id="S2", session_id=ses.session_id, center_id=c.center_id, hall_id=h.hall_id, seat_no=1))
    with pytest.raises(IntegrityError):
        db.flush()


def test_safe_capacity_cannot_exceed_capacity(db):
    sc, c, h, ses = _fixture_world(db)
    db.add(Hall(center_id=c.center_id, hall_name="H2", capacity=20, safe_capacity=21))
    with pytest.raises(IntegrityError):
        db.flush()


def test_readiness_score_range_enforced(db):
    db.add(School(school_id="X", name="x", governorate="G", district="D", halls_count=1, hall_capacity=1, readiness_score=101))
    with pytest.raises(IntegrityError):
        db.flush()


def test_center_category_restricted(db):
    sc, c, h, ses = _fixture_world(db)
    db.add(Center(scenario_id=sc.scenario_id, school_id="SC1", governorate="G", category="bogus"))
    with pytest.raises(IntegrityError):
        db.flush()
