from ecsa.engines.allocation import allocate
from ecsa.engines.kpi import compute_kpis
from ecsa.engines.scheduling import generate_schedule
from tests.helpers import START, default_params, make_center, make_students


def test_kpis_reflect_run():
    params = default_params(operating_days_per_round=2, sessions_per_day=2)
    students = make_students(40, ["D1"], ["A", "B"])
    centers = [make_center(1, "D1", halls=2), make_center(9, "D1", halls=2, active=False, category="reserve")]
    sched = generate_schedule(students, START, params)
    res = allocate(students, centers, sched, params)
    k = compute_kpis(students, centers, sched, res, params)
    assert k["exam_cases"] == 80 and k["assigned"] == 80 and k["coverage"] == 1.0
    assert k["active_centers"] == 1 and k["reserve_centers"] == 1
    assert k["total_safe_seats"] == 42 * 4
    assert k["overall_utilization"] == round(80 / 168, 4)
    assert len(k["centers"]) == 1 and k["centers"][0]["assigned"] == 80
    assert len(k["slots_detail"]) == 4
