"""Scheduling engine — step خ5 and decision D5.

1. Build the round's slots: operating_days_per_round × sessions_per_day,
   starting at the round start date and skipping `rest_weekdays`.
2. Build subject conflict groups: two subjects conflict when at least one
   student takes both. A greedy coloring puts non-conflicting subjects in the
   same group so they can share a slot.
3. Assign groups to slots round-robin. Every subject therefore gets
   ≈ slots ÷ groups sittings, spread evenly across the round, and no student
   can ever have two subjects in the same slot.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from ecsa.engines.types import SessionRec, Slot, StudentRec
from ecsa.parameters.store import ParameterSet


class SchedulingError(ValueError):
    pass


def parse_rest_weekdays(value: str) -> set[int]:
    """'4,5' -> {4, 5} (Python weekday numbers: Monday=0 … Sunday=6)."""
    value = (value or "").strip()
    if not value:
        return set()
    return {int(x) for x in value.replace(";", ",").split(",") if x.strip() != ""}


def build_slots(start: date, params: ParameterSet) -> list[Slot]:
    days = params.int("operating_days_per_round")
    per_day = params.int("sessions_per_day")
    rest = parse_rest_weekdays(params.get("rest_weekdays")) if params.has("rest_weekdays") else set()
    if days <= 0 or per_day <= 0:
        raise SchedulingError("operating_days_per_round and sessions_per_day must be positive")
    if len(rest) >= 7:
        raise SchedulingError("rest_weekdays cannot cover the whole week")
    slots: list[Slot] = []
    d = start
    used_days = 0
    while used_days < days:
        if d.weekday() not in rest:
            slots.extend(Slot(d, n) for n in range(1, per_day + 1))
            used_days += 1
        d += timedelta(days=1)
    return slots


def subject_demand(students: list[StudentRec]) -> Counter:
    c: Counter = Counter()
    for s in students:
        c.update(s.subjects)
    return c


def conflict_groups(students: list[StudentRec]) -> list[list[str]]:
    """Greedy coloring of the subject conflict graph. Subjects with the largest
    demand are placed first; each is added to the first group that contains no
    conflicting subject."""
    demand = subject_demand(students)
    conflicts: dict[str, set[str]] = defaultdict(set)
    for s in students:
        for a in s.subjects:
            for b in s.subjects:
                if a != b:
                    conflicts[a].add(b)
    groups: list[list[str]] = []
    for subj, _ in sorted(demand.items(), key=lambda kv: (-kv[1], kv[0])):
        for g in groups:
            if not (conflicts[subj] & set(g)):
                g.append(subj)
                break
        else:
            groups.append([subj])
    return groups


@dataclass
class Schedule:
    slots: list[Slot]
    groups: list[list[str]]
    sessions: list[SessionRec]
    sittings_per_subject: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def sessions_for(self, subject_id: str) -> list[SessionRec]:
        return [s for s in self.sessions if s.subject_id == subject_id]


def generate_schedule(students: list[StudentRec], start: date, params: ParameterSet,
                      seats_per_slot: int | None = None) -> Schedule:
    slots = build_slots(start, params)
    groups = conflict_groups(students)
    if len(groups) > len(slots):
        raise SchedulingError(f"{len(groups)} subject groups but only {len(slots)} slots in the round")
    sessions: list[SessionRec] = []
    sid = 0
    for i, slot in enumerate(slots):
        if not groups:
            break
        for subj in groups[i % len(groups)]:
            sid += 1
            sessions.append(SessionRec(sid, slot, subj))
    sched = Schedule(slots, groups, sessions)
    sched.sittings_per_subject = Counter(s.subject_id for s in sessions)
    if seats_per_slot is not None:
        for subj, need in subject_demand(students).items():
            have = sched.sittings_per_subject.get(subj, 0) * seats_per_slot
            if have < need:
                sched.warnings.append(f"subject {subj}: {need} students but only {have} safe seats across "
                                      f"{sched.sittings_per_subject.get(subj, 0)} sittings")
    return sched


def min_sittings_needed(demand: int, seats_per_slot: int) -> int:
    if seats_per_slot <= 0:
        raise SchedulingError("seats per slot must be positive")
    return math.ceil(demand / seats_per_slot)
