"""Allocation engine — step خ6 and decisions D6, D10, D11.

Constrained greedy:
  * students are processed district by district (spec خ6);
  * for each (student, subject) the candidate centers are ordered by distance,
    with near-ties (within `load_balance_tolerance_km`) broken by lower load;
  * inside a center the least-filled slot of the subject is preferred;
  * hard constraints: never exceed a hall's safe capacity, never two sessions
    in the same slot for one student;
  * soft constraints, relaxed in order only when nothing else fits:
      1. keep the emergency seat margin (`emergency_margin_rate`) free,
      2. at most `max_exams_per_student_per_day` exams per day.
Every relaxation and every non-nearest placement is recorded on the
assignment note so the distribution report can explain it.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from ecsa.engines.geo import DistanceResolver
from ecsa.engines.scheduling import Schedule
from ecsa.engines.types import AssignmentRec, CenterRec, HallRec, SessionRec, Slot, StudentRec
from ecsa.parameters.store import ParameterSet


@dataclass
class Unassigned:
    student_id: str
    subject_id: str
    reason: str


@dataclass
class AllocationResult:
    assignments: list[AssignmentRec] = field(default_factory=list)
    unassigned: list[Unassigned] = field(default_factory=list)
    margin_used: int = 0
    day_limit_relaxed: int = 0
    not_nearest: int = 0

    @property
    def assigned_count(self) -> int:
        return len(self.assignments)


class _HallSlotState:
    __slots__ = ("hall", "used")

    def __init__(self, hall: HallRec):
        self.hall = hall
        self.used = 0


class Allocator:
    def __init__(self, students: list[StudentRec], centers: list[CenterRec], schedule: Schedule,
                 params: ParameterSet, geo: DistanceResolver | None = None):
        self.students = students
        self.centers = [c for c in centers if c.active and c.halls]
        self.schedule = schedule
        self.params = params
        self.geo = geo or DistanceResolver(params.float("unknown_distance_km"), [*students, *centers])
        self.margin_rate = params.float("emergency_margin_rate")
        self.max_per_day = params.int("max_exams_per_student_per_day")
        self.tolerance_km = params.float("load_balance_tolerance_km")

        self.sessions_by_subject: dict[str, list[SessionRec]] = defaultdict(list)
        for s in schedule.sessions:
            self.sessions_by_subject[s.subject_id].append(s)

        # state
        self.hall_state: dict[tuple[int | str, Slot], list[_HallSlotState]] = {}
        self.center_slot_used: dict[tuple[int | str, Slot], int] = defaultdict(int)
        self.center_used: dict[int | str, int] = defaultdict(int)
        self.center_total: dict[int | str, int] = {c.center_id: c.safe_seats_per_slot * len(schedule.slots) for c in self.centers}
        self._dist_cache: dict[tuple[str, int | str], float] = {}

    # ---- helpers ---------------------------------------------------------
    def _halls(self, center: CenterRec, slot: Slot) -> list[_HallSlotState]:
        key = (center.center_id, slot)
        st = self.hall_state.get(key)
        if st is None:
            st = [_HallSlotState(h) for h in center.halls]
            self.hall_state[key] = st
        return st

    def _hall_limit(self, hall: HallRec, allow_margin: bool) -> int:
        if allow_margin:
            return hall.safe_capacity
        return hall.safe_capacity - int(math.floor(hall.safe_capacity * self.margin_rate))

    def _distance(self, student: StudentRec, center: CenterRec) -> float:
        if student.lat is None or student.lng is None:
            key = (student.district, center.center_id)
            d = self._dist_cache.get(key)
            if d is None:
                d = self._dist_cache[key] = self.geo.distance(student, center)
            return d
        return self.geo.distance(student, center)

    def _center_load(self, center: CenterRec) -> float:
        tot = self.center_total.get(center.center_id) or 1
        return self.center_used[center.center_id] / tot

    def ordered_centers(self, student: StudentRec) -> list[tuple[CenterRec, float]]:
        """Nearest first; centers within the tolerance of the nearest are ordered by load (D10)."""
        ranked = sorted(((c, self._distance(student, c)) for c in self.centers), key=lambda x: (x[1], x[0].center_id))
        if not ranked:
            return []
        d0 = ranked[0][1]
        near = [x for x in ranked if x[1] <= d0 + self.tolerance_km]
        far = ranked[len(near):]
        near.sort(key=lambda x: (self._center_load(x[0]), x[1], x[0].center_id))
        return near + far

    def _free_hall(self, center: CenterRec, slot: Slot, allow_margin: bool) -> _HallSlotState | None:
        for st in self._halls(center, slot):
            if st.used < self._hall_limit(st.hall, allow_margin):
                return st
        return None

    def _student_can_take(self, used_slots: set[Slot], per_day: dict, slot: Slot, relax_day_limit: bool) -> bool:
        if slot in used_slots:
            return False  # hard: one session per slot
        if not relax_day_limit and per_day[slot.exam_date] >= self.max_per_day:
            return False
        return True

    # ---- main --------------------------------------------------------------
    def run(self) -> AllocationResult:
        result = AllocationResult()
        order = sorted(self.students, key=lambda s: (s.district, s.student_id))
        for student in order:
            used_slots: set[Slot] = set()
            per_day: dict = defaultdict(int)
            centers = self.ordered_centers(student)
            nearest_id = centers[0][0].center_id if centers else None
            # scarce subjects first
            subjects = sorted(student.subjects, key=lambda sid: (len(self.sessions_by_subject.get(sid, [])), sid))
            for subject in subjects:
                sessions = self.sessions_by_subject.get(subject)
                if not sessions:
                    result.unassigned.append(Unassigned(student.student_id, subject, "subject has no sessions in the schedule"))
                    continue
                placed = None
                for allow_margin, relax_day in ((False, False), (True, False), (False, True), (True, True)):
                    placed = self._try_place(student, subject, sessions, centers, used_slots, per_day, allow_margin, relax_day)
                    if placed:
                        rec, center, hall_state, session, dist, rank = placed
                        notes = []
                        if allow_margin and hall_state.used > self._hall_limit(hall_state.hall, False):
                            notes.append("emergency margin used")
                            result.margin_used += 1
                        if relax_day and per_day[session.slot.exam_date] > self.max_per_day:
                            notes.append("daily exam limit exceeded")
                            result.day_limit_relaxed += 1
                        if center.center_id != nearest_id:
                            notes.append(f"not nearest center (rank {rank + 1})")
                            result.not_nearest += 1
                        rec.note = "; ".join(notes) or None
                        result.assignments.append(rec)
                        break
                if not placed:
                    result.unassigned.append(Unassigned(student.student_id, subject, "no free seat in any center for any free slot"))
        return result

    def _try_place(self, student, subject, sessions, centers, used_slots, per_day, allow_margin, relax_day):
        for rank, (center, dist) in enumerate(centers):
            cand = [s for s in sessions if self._student_can_take(used_slots, per_day, s.slot, relax_day)]
            # least-filled slot of this subject in this center first
            cand.sort(key=lambda s: (self.center_slot_used[(center.center_id, s.slot)], s.slot.exam_date, s.slot.session_no))
            for session in cand:
                hs = self._free_hall(center, session.slot, allow_margin)
                if hs is None:
                    continue
                hs.used += 1
                self.center_slot_used[(center.center_id, session.slot)] += 1
                self.center_used[center.center_id] += 1
                used_slots.add(session.slot)
                per_day[session.slot.exam_date] += 1
                rec = AssignmentRec(student.student_id, session.session_id, subject, session.slot,
                                    center.center_id, hs.hall.hall_id, distance_km=round(dist, 3))
                return rec, center, hs, session, dist, rank
        return None


def allocate(students: list[StudentRec], centers: list[CenterRec], schedule: Schedule,
             params: ParameterSet, geo: DistanceResolver | None = None) -> AllocationResult:
    return Allocator(students, centers, schedule, params, geo).run()
