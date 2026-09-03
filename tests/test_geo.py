import pytest

from ecsa.engines.geo import DistanceResolver, haversine_km
from ecsa.engines.types import SchoolRec, StudentRec


def test_haversine_known_distance():
    # Baghdad -> Basra is roughly 445 km
    assert haversine_km(33.3152, 44.3661, 30.5085, 47.7804) == pytest.approx(445, abs=10)


def test_coordinates_beat_district():
    a = StudentRec("s", "D1", lat=33.0, lng=44.0)
    b = SchoolRec("x", "x", "D1", 1, 1, 80, lat=33.0, lng=44.1)
    geo = DistanceResolver(50, [a, b])
    assert geo.distance(a, b) > 0


def test_same_district_without_coords_is_zero():
    a = StudentRec("s", "D1")
    b = SchoolRec("x", "x", "D1", 1, 1, 80)
    assert DistanceResolver(50).distance(a, b) == 0.0


def test_district_centroid_fallback():
    pts = [StudentRec("s1", "D1", lat=33.0, lng=44.0), StudentRec("s2", "D1", lat=33.2, lng=44.0),
           StudentRec("s3", "D2", lat=34.0, lng=44.0)]
    geo = DistanceResolver(50, pts)
    assert geo.centroids["D1"] == pytest.approx((33.1, 44.0))
    a = StudentRec("x", "D1")  # no coords
    b = SchoolRec("y", "y", "D2", 1, 1, 80)  # no coords
    assert geo.distance(a, b) == pytest.approx(haversine_km(33.1, 44.0, 34.0, 44.0))


def test_unknown_distance_parameter_used_when_nothing_known():
    geo = DistanceResolver(77)
    assert geo.distance(StudentRec("x", "D1"), SchoolRec("y", "y", "D2", 1, 1, 80)) == 77
