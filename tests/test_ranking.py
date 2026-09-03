import pytest

from ecsa.engines.ranking import rank_schools
from ecsa.engines.types import SchoolRec, StudentRec
from ecsa.parameters.store import ParameterSet, load_default_definitions


@pytest.fixture()
def params():
    return ParameterSet({d["param_key"]: d["param_value"] for d in load_default_definitions()})


def test_low_readiness_is_excluded(params):
    schools = [SchoolRec("A", "A", "D1", 10, 25, 59), SchoolRec("B", "B", "D1", 10, 25, 60), SchoolRec("C", "C", "D1", 10, 25, None)]
    ranked = rank_schools(schools, [StudentRec("s", "D1", ["m"])], params)
    by_id = {r.school.school_id: r for r in ranked}
    assert not by_id["A"].eligible and "below minimum" in by_id["A"].exclusion_reason
    assert by_id["B"].eligible and by_id["B"].rank == 1
    assert not by_id["C"].eligible and "missing" in by_id["C"].exclusion_reason


def test_weights_drive_order(params):
    big_far = SchoolRec("BIG", "big", "D2", 20, 25, 70)
    small_near = SchoolRec("NEAR", "near", "D1", 5, 25, 70)
    students = [StudentRec(f"s{i}", "D1", ["m"]) for i in range(100)]
    default = rank_schools([big_far, small_near], students, params)
    assert default[0].school.school_id == "BIG"          # capacity weight 0.4 beats proximity 0.2
    prox_first = params.with_overrides({"rank_weight_capacity": 0.1, "rank_weight_proximity": 0.8})
    assert rank_schools([big_far, small_near], students, prox_first)[0].school.school_id == "NEAR"


def test_scores_are_normalized_between_zero_and_one(params):
    schools = [SchoolRec(f"S{i}", "s", "D1", 5 + i, 25, 60 + i * 5) for i in range(5)]
    for r in rank_schools(schools, [StudentRec("s", "D1", ["m"])], params):
        assert 0.0 <= r.score <= 1.0 + 1e-9


def test_rank_is_dense_and_eligible_first(params):
    schools = [SchoolRec("bad", "b", "D1", 5, 25, 10), SchoolRec("ok1", "o", "D1", 5, 25, 90), SchoolRec("ok2", "o", "D1", 6, 25, 90)]
    ranked = rank_schools(schools, [StudentRec("s", "D1", ["m"])], params)
    assert [r.school.school_id for r in ranked] == ["ok2", "ok1", "bad"]
    assert [r.rank for r in ranked] == [1, 2, None]
