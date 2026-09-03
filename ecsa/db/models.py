"""SQLAlchemy models for ECSA.

Mandatory constraints are enforced at the database level (rule 3 in
CLAUDE.md), not only in code:
  * assignments: unique (student_id, session_id)  — a student sits once per session
  * assignments: unique (hall_id, session_id, seat_no) — a seat is used once
  * halls: safe_capacity <= capacity
  * schools: readiness_score between 0 and 100
Every operational table carries `governorate` so the system generalizes to
all governorates by key (decision D12).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"
    student_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    governorate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    gender: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    subjects: Mapped[list["StudentSubject"]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"
    subject_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)


class StudentSubject(Base):
    __tablename__ = "student_subjects"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "exam_round", name="uq_student_subject_round"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.subject_id"), nullable=False, index=True)
    exam_round: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    student: Mapped["Student"] = relationship(back_populates="subjects")
    subject: Mapped["Subject"] = relationship()


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (CheckConstraint("readiness_score IS NULL OR (readiness_score >= 0 AND readiness_score <= 100)", name="ck_readiness_range"),)
    school_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    governorate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    halls_count: Mapped[int] = mapped_column(Integer, nullable=False)
    hall_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    readiness_score: Mapped[float | None] = mapped_column(Float)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SchoolHall(Base):
    """Optional real per-hall data for a school (decision D8). When present it
    overrides the halls_count × hall_capacity seed when the school becomes a center."""
    __tablename__ = "school_halls"
    __table_args__ = (UniqueConstraint("school_id", "hall_name", name="uq_school_hall_name"),
                      CheckConstraint("capacity > 0", name="ck_school_hall_capacity_positive"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.school_id", ondelete="CASCADE"), nullable=False, index=True)
    hall_name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class Center(Base):
    """A school approved as an exam center inside a scenario."""
    __tablename__ = "centers"
    __table_args__ = (
        UniqueConstraint("scenario_id", "school_id", name="uq_center_scenario_school"),
        CheckConstraint("category IN ('primary','supporting','reserve')", name="ck_center_category"),
        CheckConstraint("activation_status IN ('active','inactive')", name="ck_center_activation"),
    )
    center_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.scenario_id", ondelete="CASCADE"), nullable=False, index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.school_id"), nullable=False)
    governorate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    activation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    rank: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)

    school: Mapped["School"] = relationship()
    halls: Mapped[list["Hall"]] = relationship(back_populates="center", cascade="all, delete-orphan")


class Hall(Base):
    __tablename__ = "halls"
    __table_args__ = (
        CheckConstraint("safe_capacity <= capacity", name="ck_hall_safe_le_capacity"),
        CheckConstraint("capacity > 0", name="ck_hall_capacity_positive"),
    )
    hall_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.center_id", ondelete="CASCADE"), nullable=False, index=True)
    hall_name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    center: Mapped["Center"] = relationship(back_populates="halls")


class Session(Base):
    """One subject sitting in one (exam_date, session_no) slot of a round."""
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("scenario_id", "exam_round", "exam_date", "session_no", "subject_id", name="uq_session_slot_subject"),)
    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.scenario_id", ondelete="CASCADE"), nullable=False, index=True)
    exam_round: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_no: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.subject_id"), nullable=False)

    subject: Mapped["Subject"] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("student_id", "session_id", name="uq_assignment_student_session"),
        UniqueConstraint("hall_id", "session_id", "seat_no", name="uq_assignment_seat"),
    )
    assignment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.scenario_id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.center_id", ondelete="CASCADE"), nullable=False, index=True)
    hall_id: Mapped[int] = mapped_column(ForeignKey("halls.hall_id", ondelete="CASCADE"), nullable=False, index=True)
    seat_no: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(200))


class Staff(Base):
    """Head-counts only. No financial data (decision D13)."""
    __tablename__ = "staff"
    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    governorate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    center_id: Mapped[int | None] = mapped_column(ForeignKey("centers.center_id", ondelete="SET NULL"))
    is_reserve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Parameter(Base):
    """The single source of every operational value.

    governorate NULL means a global default; a governorate-specific row
    overrides it. The row with the latest effective_from <= as-of date wins.
    """
    __tablename__ = "parameters"
    __table_args__ = (UniqueConstraint("param_key", "governorate", "effective_from", name="uq_param_scope_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    param_value: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    governorate: Mapped[str | None] = mapped_column(String(100), index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (CheckConstraint("status IN ('draft','completed','approved','failed')", name="ck_scenario_status"),)
    scenario_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    governorate: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    exam_round: Mapped[int] = mapped_column(Integer, nullable=False)
    round_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    params_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    kpi_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_log: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
