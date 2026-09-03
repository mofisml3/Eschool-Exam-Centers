"""Distance resolution (decision D7).

Priority:
  1. haversine between two coordinate pairs
  2. 0 km when both are in the same district
  3. distance between district centroids (mean of known coordinates)
  4. `unknown_distance_km` parameter
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Protocol

EARTH_RADIUS_KM = 6371.0088


class Located(Protocol):
    district: str
    lat: float | None
    lng: float | None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _has_coords(x) -> bool:
    return x is not None and getattr(x, "lat", None) is not None and getattr(x, "lng", None) is not None


class DistanceResolver:
    def __init__(self, unknown_distance_km: float, located: Iterable[Located] = ()):
        self.unknown_km = float(unknown_distance_km)
        self.centroids: dict[str, tuple[float, float]] = {}
        self.add_points(located)

    def add_points(self, located: Iterable[Located]) -> None:
        sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for k, (lat, lng) in self.centroids.items():
            sums[k] = [lat, lng, 1.0]  # keep existing centroid as one weighted point
        for x in located:
            if _has_coords(x):
                s = sums[x.district]
                s[0] += x.lat
                s[1] += x.lng
                s[2] += 1
        self.centroids = {k: (v[0] / v[2], v[1] / v[2]) for k, v in sums.items() if v[2] > 0}

    def distance(self, a: Located, b: Located) -> float:
        if _has_coords(a) and _has_coords(b):
            return haversine_km(a.lat, a.lng, b.lat, b.lng)
        if a.district == b.district:
            return 0.0
        return self.district_distance(a.district, b.district)

    def district_distance(self, d1: str, d2: str) -> float:
        if d1 == d2:
            return 0.0
        c1, c2 = self.centroids.get(d1), self.centroids.get(d2)
        if c1 and c2:
            return haversine_km(c1[0], c1[1], c2[0], c2[1])
        return self.unknown_km
