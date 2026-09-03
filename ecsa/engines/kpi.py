"""Utilization and quality indicators for a scenario run."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from ecsa.engines.allocation import AllocationResult
from ecsa.engines.scheduling import Schedule
from ecsa.engines.types import CenterRec, StudentRec
from ecsa.parameters.store import ParameterSet


def compute_kpis(students: list[StudentRec], centers: list[CenterRec], schedule: Schedule,
                 result: AllocationResult, params: ParameterSet) -> dict:
    active = [c for c in centers if c.active]
    n_slots = len(schedule.slots)
    cases = sum(len(s.subjects) for s in students)
    by_center = Counter(a.center_id for a in result.assignments)
    by_hall_slot = Counter((a.hall_id, a.slot) for a in result.assignments)
    by_slot = Counter(a.slot for a in result.assignments)
    safe_by_hall = {h.hall_id: h.safe_capacity for c in active for h in c.halls}
    total_safe_seats = sum(c.safe_seats_per_slot for c in active) * n_slots

    center_rows = []
    for c in active:
        seats = c.safe_seats_per_slot * n_slots
        used = by_center.get(c.center_id, 0)
        center_rows.append({"center_id": c.center_id, "school_id": c.school_id, "name": c.name, "category": c.category,
                            "safe_seats": seats, "assigned": used, "utilization": round(used / seats, 4) if seats else 0.0})
    slot_rows = [{"slot": f"{sl.exam_date} #{sl.session_no}", "assigned": by_slot.get(sl, 0),
                  "safe_seats": sum(c.safe_seats_per_slot for c in active),
                  "utilization": round(by_slot.get(sl, 0) / max(1, sum(c.safe_seats_per_slot for c in active)), 4)}
                 for sl in schedule.slots]
    hall_util = [n / safe_by_hall[h] for (h, _), n in by_hall_slot.items() if safe_by_hall.get(h)]
    distances = [a.distance_km for a in result.assignments if a.distance_km is not None]
    target_min, target_max = params.float("target_utilization_min"), params.float("target_utilization_max")
    overall = result.assigned_count / total_safe_seats if total_safe_seats else 0.0

    return {
        "exam_cases": cases,
        "students": len(students),
        "assigned": result.assigned_count,
        "unassigned": len(result.unassigned),
        "coverage": round(result.assigned_count / cases, 4) if cases else 1.0,
        "active_centers": len(active),
        "reserve_centers": sum(1 for c in centers if c.category == "reserve"),
        "slots": n_slots,
        "sessions": len(schedule.sessions),
        "total_safe_seats": total_safe_seats,
        "overall_utilization": round(overall, 4),
        "utilization_in_target": target_min <= overall <= target_max,
        "max_hall_slot_utilization": round(max(hall_util), 4) if hall_util else 0.0,
        "mean_distance_km": round(mean(distances), 3) if distances else None,
        "not_nearest_share": round(result.not_nearest / result.assigned_count, 4) if result.assigned_count else 0.0,
        "emergency_margin_used": result.margin_used,
        "day_limit_relaxed": result.day_limit_relaxed,
        "centers": center_rows,
        "slots_detail": slot_rows,
    }
