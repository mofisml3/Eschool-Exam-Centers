import pandas as pd
from sqlalchemy import select

from ecsa.db.models import School, Student, StudentSubject
from ecsa.importer import import_dataframe


def test_students_import_validates_and_upserts(db):
    df = pd.DataFrame([
        {"Student_ID": "S1", "full_name": "A", "governorate": "G", "district": "D", "lat": "33.1", "lng": "44.2"},
        {"Student_ID": "S2", "full_name": "B", "governorate": "G", "district": "D", "lat": "999", "lng": "1"},   # bad lat
        {"Student_ID": "", "full_name": "C", "governorate": "G", "district": "D"},                           # missing id
        {"Student_ID": "S1", "full_name": "dup", "governorate": "G", "district": "D"},                       # duplicate in file
    ])
    rep = import_dataframe(db, "students", df)
    assert rep.inserted == 1 and rep.skipped == 3 and len(rep.errors) == 3
    assert {e["row"] for e in rep.errors} == {3, 4, 5}
    rep2 = import_dataframe(db, "students", pd.DataFrame([{"student_id": "S1", "full_name": "A2", "governorate": "G", "district": "D2"}]))
    assert rep2.updated == 1 and db.get(Student, "S1").district == "D2"


def test_missing_required_column_reported(db):
    rep = import_dataframe(db, "schools", pd.DataFrame([{"school_id": "X"}]))
    assert not rep.ok and "missing required columns" in rep.errors[0]["error"]


def test_student_subjects_require_known_references(db):
    import_dataframe(db, "students", pd.DataFrame([{"student_id": "S1", "full_name": "A", "governorate": "G", "district": "D"}]))
    import_dataframe(db, "subjects", pd.DataFrame([{"subject_id": "M", "name": "Math"}]))
    rep = import_dataframe(db, "student_subjects", pd.DataFrame([
        {"student_id": "S1", "subject_id": "M", "exam_round": "1"},
        {"student_id": "S9", "subject_id": "M", "exam_round": "1"},
        {"student_id": "S1", "subject_id": "ZZ", "exam_round": "1"},
    ]))
    assert rep.inserted == 1 and len(rep.errors) == 2
    assert db.execute(select(StudentSubject)).scalars().one().exam_round == 1


def test_school_readiness_range(db):
    rep = import_dataframe(db, "schools", pd.DataFrame([
        {"school_id": "A", "name": "a", "governorate": "G", "district": "D", "halls_count": "10", "hall_capacity": "25", "readiness_score": "120"},
        {"school_id": "B", "name": "b", "governorate": "G", "district": "D", "halls_count": "10", "hall_capacity": "25", "readiness_score": ""},
    ]))
    assert rep.inserted == 1 and db.get(School, "B").readiness_score is None
