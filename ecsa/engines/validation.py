"""Post-allocation checks — step خ8.

  * every (student, subject) has exactly one assignment
  * no hall exceeds its safe capacity in any slot
  * no student has two sessions in the same slot
  * no seat is used twice in a hall-slot
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ecsa.engines.types import AssignmentRec, CenterRec, StudentRec


@dataclass
class ValidationReport:
    missing: list[tuple[str, str]] = field(default_factory=list)       # (student, subject)
    duplicates: list[tuple[str, str]] = field(default_factory=list)    # (student, subject) assigned more than once
    over_capacity: list[dict] = field(default_factory=list)            # hall/slot rows
    clashes: list[tuple[str, str]] = field(default_factory=list)       # (student, slot)
    seat_conflicts: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.duplicates or self.over_capacity or self.clashes or self.seat_conflicts)

    def summary(self) -> dict:
        return {"ok": self.ok, "missing": len(self.missing), "duplicates": len(self.duplicates),
                "over_capacity": len(self.over_capacity), "clashes": len(self.clashes),
                "seat_conflicts": len(self.seat_conflicts)}


def validate(students: list[StudentRec], centers: list[CenterRec], assignments: list[AssignmentRec]) -> ValidationReport:
    rep = ValidationReport()
    per_pair = Counter((a.student_id, a.subject_id) for a in assignments)
    for s in students:
        for subj in s.subjects:
            n = per_pair.get((s.student_id, subj), 0)
            if n == 0:
                rep.missing.append((s.student_id, subj))
            elif n > 1:
                rep.duplicates.append((s.student_id, subj))

    safe = {h.hall_id: h.safe_capacity for c in centers for h in c.halls}
    hall_slot = Counter((a.hall_id, a.slot) for a in assignments)
    for (hall_id, slot), n in hall_slot.items():
        cap = safe.get(hall_id)
        if cap is None or n > cap:
            rep.over_capacity.append({"hall_id": hall_id, "slot": str(slot), "assigned": n, "safe_capacity": cap})

    student_slot = Counter((a.student_id, a.slot) for a in assignments)
    rep.clashes = [(sid, str(slot)) for (sid, slot), n in student_slot.items() if n > 1]

    seats = Counter((a.hall_id, a.slot, a.seat_no) for a in assignments if a.seat_no)
    rep.seat_conflicts = [{"hall_id": h, "slot": str(sl), "seat_no": seat, "count": n} for (h, sl, seat), n in seats.items() if n > 1]
    return rep
