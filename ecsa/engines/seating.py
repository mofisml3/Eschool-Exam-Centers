"""Seat numbering — step خ7 and decision D9.

Seats are numbered 1..n per (hall, slot). Students are interleaved across
districts (round-robin over district groups, largest group first) so that
neighbors come from different districts wherever possible.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import zip_longest

from ecsa.engines.types import AssignmentRec, Slot, StudentRec


def interleave_by_district(items: list[tuple[str, AssignmentRec]]) -> list[AssignmentRec]:
    groups: dict[str, list[AssignmentRec]] = defaultdict(list)
    for district, rec in items:
        groups[district].append(rec)
    ordered = sorted(groups.values(), key=lambda g: (-len(g), g[0].student_id))
    out: list[AssignmentRec] = []
    for layer in zip_longest(*ordered):
        out.extend(r for r in layer if r is not None)
    return out


def number_seats(assignments: list[AssignmentRec], students: list[StudentRec]) -> None:
    """Mutates seat_no in place."""
    district_of = {s.student_id: s.district for s in students}
    by_hall_slot: dict[tuple[int | str, Slot], list[tuple[str, AssignmentRec]]] = defaultdict(list)
    for a in assignments:
        by_hall_slot[(a.hall_id, a.slot)].append((district_of.get(a.student_id, ""), a))
    for key, items in by_hall_slot.items():
        for seat, rec in enumerate(interleave_by_district(items), start=1):
            rec.seat_no = seat
