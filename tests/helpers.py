from datetime import date

from ecsa.engines.capacity import hall_safe_capacity
from ecsa.engines.types import CenterRec, HallRec, StudentRec
from ecsa.parameters.store import ParameterSet, load_default_definitions

START = date(2026, 3, 1)


def default_params(**overrides) -> ParameterSet:
    return ParameterSet({d["param_key"]: d["param_value"] for d in load_default_definitions()}).with_overrides(overrides)


def make_center(cid, district, halls=2, cap=25, rate=0.85, active=True, category="primary", lat=None, lng=None) -> CenterRec:
    return CenterRec(cid, f"SCH{cid}", f"Center {cid}", district, category, active,
                     [HallRec(f"{cid}-H{i}", f"H{i}", cap, hall_safe_capacity(cap, rate)) for i in range(1, halls + 1)],
                     lat=lat, lng=lng)


def make_students(n, districts, subjects, prefix="s") -> list[StudentRec]:
    return [StudentRec(f"{prefix}{i}", districts[i % len(districts)], list(subjects)) for i in range(n)]
