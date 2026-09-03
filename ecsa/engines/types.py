"""Plain data records exchanged between the scenario service and the engines.
Engines never import SQLAlchemy models; this keeps them pure and testable."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class StudentRec:
    student_id: str
    district: str
    subjects: list[str] = field(default_factory=list)  # subject_ids taken in the round
    lat: float | None = None
    lng: float | None = None
    gender: str | None = None


@dataclass
class SchoolRec:
    school_id: str
    name: str
    district: str
    halls_count: int
    hall_capacity: int
    readiness_score: float | None
    lat: float | None = None
    lng: float | None = None

    @property
    def raw_capacity_per_session(self) -> int:
        return self.halls_count * self.hall_capacity


@dataclass
class HallRec:
    hall_id: int | str
    hall_name: str
    capacity: int
    safe_capacity: int


@dataclass
class CenterRec:
    center_id: int | str
    school_id: str
    name: str
    district: str
    category: str  # primary | supporting | reserve
    active: bool
    halls: list[HallRec] = field(default_factory=list)
    lat: float | None = None
    lng: float | None = None

    @property
    def safe_seats_per_slot(self) -> int:
        return sum(h.safe_capacity for h in self.halls)


@dataclass(frozen=True)
class Slot:
    exam_date: date
    session_no: int


@dataclass
class SessionRec:
    session_id: int | str
    slot: Slot
    subject_id: str


@dataclass
class AssignmentRec:
    student_id: str
    session_id: int | str
    subject_id: str
    slot: Slot
    center_id: int | str
    hall_id: int | str
    seat_no: int = 0
    distance_km: float | None = None
    note: str | None = None
