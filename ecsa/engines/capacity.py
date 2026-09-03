"""Capacity & decision engine — steps خ1, خ2, خ3 and decisions D1, D2.

All operational values come from a ParameterSet. Nothing is hard-coded."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ecsa.engines.types import StudentRec
from ecsa.parameters.store import ParameterSet


# ---- خ1: exam cases ------------------------------------------------------

def exam_cases(students: list[StudentRec]) -> int:
    """Workload of the round = COUNT(student × subject)."""
    return sum(len(s.subjects) for s in students)


# ---- خ2: safe capacity ----------------------------------------------------

def hall_safe_capacity(capacity: int, safe_utilization_rate: float) -> int:
    return int(math.floor(capacity * safe_utilization_rate))


def center_round_capacity(total_hall_capacity: int, params: ParameterSet) -> float:
    """center_round_capacity = Σ halls.capacity × sessions_per_day × safe_rate × operating_days."""
    return (total_hall_capacity
            * params.int("sessions_per_day")
            * params.float("safe_utilization_rate")
            * params.int("operating_days_per_round"))


# ---- خ3: centers needed ----------------------------------------------------

def centers_needed(cases: int, avg_center_round_capacity: float) -> int:
    if cases <= 0:
        return 0
    if avg_center_round_capacity <= 0:
        raise ValueError("average center capacity must be positive")
    return math.ceil(cases / avg_center_round_capacity)


def reserve_centers_needed(main_centers: int, params: ParameterSet) -> int:
    """Decision D1: reserve = CEIL(ratio × main centers)."""
    if main_centers <= 0:
        return 0
    return math.ceil(main_centers * params.float("reserve_center_ratio") - 1e-9)


# ---- Decision: which candidates become which category ---------------------

@dataclass
class CandidateCapacity:
    school_id: str
    round_capacity: float
    score: float  # from the ranking engine; higher is better


@dataclass
class CenterDecision:
    exam_cases: int
    avg_center_round_capacity: float
    primary: list[str] = field(default_factory=list)
    supporting: list[str] = field(default_factory=list)
    reserve: list[str] = field(default_factory=list)
    main_capacity: float = 0.0
    projected_utilization: float = 0.0
    capacity_shortfall: bool = False
    reserve_shortfall: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def main_count(self) -> int:
        return len(self.primary) + len(self.supporting)


def decide_centers(cases: int, ranked: list[CandidateCapacity], params: ParameterSet) -> CenterDecision:
    """Select primary, supporting and reserve centers from an already-ranked,
    already-eligible candidate list (best first).

    primary    = CEIL(cases ÷ average candidate capacity)          (خ3)
    supporting = added one by one while utilization > target_max  (D2)
    reserve    = CEIL(reserve_center_ratio × (primary+supporting)) (D1)
    """
    if not ranked:
        return CenterDecision(exam_cases=cases, avg_center_round_capacity=0.0,
                              capacity_shortfall=cases > 0, notes=["no eligible candidate schools"])
    avg = sum(c.round_capacity for c in ranked) / len(ranked)
    d = CenterDecision(exam_cases=cases, avg_center_round_capacity=avg)
    if cases <= 0:
        d.notes.append("no exam cases; no centers required")
        return d

    n_primary = min(centers_needed(cases, avg), len(ranked))
    pool = list(ranked)
    d.primary = [c.school_id for c in pool[:n_primary]]
    pool = pool[n_primary:]
    d.main_capacity = sum(c.round_capacity for c in ranked[:n_primary])

    target_max = params.float("target_utilization_max")
    while d.main_capacity > 0 and cases / d.main_capacity > target_max and pool:
        c = pool.pop(0)
        d.supporting.append(c.school_id)
        d.main_capacity += c.round_capacity
    d.projected_utilization = cases / d.main_capacity if d.main_capacity else float("inf")
    if d.projected_utilization > 1.0:
        d.capacity_shortfall = True
        d.notes.append("eligible schools cannot absorb the exam cases; projected utilization above 100%")
    elif d.projected_utilization > target_max:
        d.notes.append("utilization above target maximum; no more eligible schools to add")
    if d.projected_utilization < params.float("target_utilization_min"):
        d.notes.append("utilization below target minimum; consider fewer centers or a lower safe rate")

    n_reserve = reserve_centers_needed(d.main_count, params)
    d.reserve = [c.school_id for c in pool[:n_reserve]]
    d.reserve_shortfall = n_reserve - len(d.reserve)
    if d.reserve_shortfall:
        d.notes.append(f"only {len(d.reserve)} of {n_reserve} reserve centers available")
    return d
