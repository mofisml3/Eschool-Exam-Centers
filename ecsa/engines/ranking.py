"""School ranking — step خ4 and decisions D3, D4.

score = w_cap × norm(capacity) + w_ready × norm(readiness) + w_prox × norm(closeness)
Each factor is min-max normalized to [0, 1] across the eligible candidates.
Closeness is the inverse of the student-weighted mean distance from the school
to the districts where students live.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ecsa.engines.geo import DistanceResolver, haversine_km
from ecsa.engines.types import SchoolRec, StudentRec
from ecsa.parameters.store import ParameterSet


@dataclass
class RankedSchool:
    school: SchoolRec
    eligible: bool
    exclusion_reason: str | None = None
    weighted_distance_km: float | None = None
    capacity_norm: float = 0.0
    readiness_norm: float = 0.0
    proximity_norm: float = 0.0
    score: float = 0.0
    rank: int | None = None
    factors: dict = field(default_factory=dict)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def school_to_district_km(school: SchoolRec, district: str, geo: DistanceResolver) -> float:
    """Distance from a school to a district: to the district centroid when both
    coordinates are known, otherwise the district-level fallback chain (D7)."""
    c = geo.centroids.get(district)
    if school.lat is not None and school.lng is not None and c:
        return haversine_km(school.lat, school.lng, c[0], c[1])
    return geo.district_distance(school.district, district)


def weighted_mean_distance(school: SchoolRec, district_counts: Counter, geo: DistanceResolver) -> float:
    """Student-weighted mean distance from the school to where students live."""
    total = sum(district_counts.values())
    if total == 0:
        return 0.0
    return sum(school_to_district_km(school, d, geo) * n for d, n in district_counts.items()) / total


def rank_schools(schools: list[SchoolRec], students: list[StudentRec], params: ParameterSet,
                 geo: DistanceResolver | None = None) -> list[RankedSchool]:
    geo = geo or DistanceResolver(params.float("unknown_distance_km"), [*students, *schools])
    min_ready = params.float("min_readiness_score")
    w_cap = params.float("rank_weight_capacity")
    w_ready = params.float("rank_weight_readiness")
    w_prox = params.float("rank_weight_proximity")
    district_counts = Counter(s.district for s in students)

    out: list[RankedSchool] = []
    for sc in schools:
        if sc.readiness_score is None:
            out.append(RankedSchool(sc, False, "readiness score missing"))
        elif sc.readiness_score < min_ready:
            out.append(RankedSchool(sc, False, f"readiness {sc.readiness_score:g} below minimum {min_ready:g}"))
        elif sc.halls_count <= 0 or sc.hall_capacity <= 0:
            out.append(RankedSchool(sc, False, "no usable halls"))
        else:
            out.append(RankedSchool(sc, True, weighted_distance_km=weighted_mean_distance(sc, district_counts, geo)))

    eligible = [r for r in out if r.eligible]
    caps = _minmax([float(r.school.raw_capacity_per_session) for r in eligible])
    ready = _minmax([float(r.school.readiness_score) for r in eligible])
    closeness = _minmax([-(r.weighted_distance_km or 0.0) for r in eligible])
    for r, c, rd, p in zip(eligible, caps, ready, closeness):
        r.capacity_norm, r.readiness_norm, r.proximity_norm = c, rd, p
        r.score = w_cap * c + w_ready * rd + w_prox * p
        r.factors = {"capacity": r.school.raw_capacity_per_session, "readiness": r.school.readiness_score,
                     "weighted_distance_km": round(r.weighted_distance_km or 0.0, 3),
                     "weights": {"capacity": w_cap, "readiness": w_ready, "proximity": w_prox}}
    eligible.sort(key=lambda r: (-r.score, -r.school.raw_capacity_per_session, r.school.school_id))
    for i, r in enumerate(eligible, start=1):
        r.rank = i
    ineligible = [r for r in out if not r.eligible]
    return eligible + ineligible
