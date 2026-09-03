import pytest

from ecsa.engines.capacity import (CandidateCapacity, center_round_capacity, centers_needed, decide_centers,
                                   exam_cases, hall_safe_capacity, reserve_centers_needed)
from ecsa.engines.types import StudentRec
from ecsa.parameters.store import ParameterSet, load_default_definitions


@pytest.fixture()
def params():
    return ParameterSet({d["param_key"]: d["param_value"] for d in load_default_definitions()})


def test_exam_cases_counts_student_by_subject():
    students = [StudentRec("a", "D", ["m", "p"]), StudentRec("b", "D", ["m"]), StudentRec("c", "D", [])]
    assert exam_cases(students) == 3


def test_hall_safe_capacity_floors():
    assert hall_safe_capacity(25, 0.85) == 21
    assert hall_safe_capacity(30, 0.85) == 25


def test_center_round_capacity_matches_spec_formula(params):
    # 10 halls × 25 = 250 × 4 sessions × 0.85 × 40 days = 34,000
    assert center_round_capacity(250, params) == pytest.approx(34_000)


def test_centers_needed_ceils():
    assert centers_needed(70_000, 34_000) == 3
    assert centers_needed(68_000, 34_000) == 2
    assert centers_needed(0, 34_000) == 0


def test_reserve_is_ceil_of_20_percent(params):
    assert reserve_centers_needed(1, params) == 1
    assert reserve_centers_needed(5, params) == 1
    assert reserve_centers_needed(6, params) == 2
    assert reserve_centers_needed(10, params) == 2
    assert reserve_centers_needed(11, params) == 3
    assert reserve_centers_needed(0, params) == 0


def test_reserve_ratio_is_read_from_parameters(params):
    assert reserve_centers_needed(10, params.with_overrides({"reserve_center_ratio": 0.5})) == 5


def _cands(n, cap=34_000):
    return [CandidateCapacity(f"S{i}", cap, score=1 - i / 100) for i in range(n)]


def test_decide_centers_primary_only(params):
    d = decide_centers(60_000, _cands(10), params)
    assert d.primary == ["S0", "S1"]         # 60,000 / 34,000 -> 2, utilization 0.88 <= 0.95
    assert d.supporting == []
    assert d.reserve == ["S2"]               # ceil(0.2 × 2) = 1
    assert d.projected_utilization == pytest.approx(60_000 / 68_000)
    assert not d.capacity_shortfall


def test_decide_centers_adds_supporting_when_utilization_too_high(params):
    # 67,000 / 34,000 -> 2 primary, utilization 0.985 > 0.95 -> add one supporting
    d = decide_centers(67_000, _cands(10), params)
    assert d.primary == ["S0", "S1"]
    assert d.supporting == ["S2"]
    assert d.reserve == ["S3"]               # ceil(0.2 × 3) = 1
    assert d.projected_utilization == pytest.approx(67_000 / 102_000)


def test_decide_centers_reserve_uses_main_count(params):
    d = decide_centers(200_000, _cands(20), params)  # 200k/34k -> 6 primary, util 0.98 -> +1 supporting = 7 main
    assert d.main_count == 7
    assert len(d.reserve) == 2               # ceil(0.2 × 7) = 2


def test_decide_centers_shortfall_flagged(params):
    d = decide_centers(200_000, _cands(3), params)
    assert d.capacity_shortfall
    assert d.reserve == [] and d.reserve_shortfall == 1


def test_decide_centers_no_candidates(params):
    d = decide_centers(10, [], params)
    assert d.capacity_shortfall and d.primary == []
