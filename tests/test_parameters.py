from datetime import date

import pytest

from ecsa.parameters.store import MissingParameterError, ParameterSet, ParameterStore, load_default_definitions


def test_defaults_are_seeded(db):
    ps = ParameterStore(db).resolve("Any")
    assert ps.int("sessions_per_day") == 4
    assert ps.float("safe_utilization_rate") == pytest.approx(0.85)
    assert ps.float("reserve_center_ratio") == pytest.approx(0.20)
    assert len(ps.values) == len(load_default_definitions())


def test_governorate_override_wins_over_global(db):
    store = ParameterStore(db)
    store.set("sessions_per_day", 3, governorate="Basra", effective_from=date(2020, 1, 1))
    assert store.resolve("Basra").int("sessions_per_day") == 3
    assert store.resolve("Baghdad").int("sessions_per_day") == 4


def test_latest_effective_date_wins_and_future_is_ignored(db):
    store = ParameterStore(db)
    store.set("hall_capacity", 30, effective_from=date(2024, 1, 1))
    store.set("hall_capacity", 40, effective_from=date(2099, 1, 1))
    assert store.resolve("G", as_of=date(2025, 1, 1)).int("hall_capacity") == 30
    assert store.resolve("G", as_of=date(2023, 1, 1)).int("hall_capacity") == 25


def test_missing_parameter_raises():
    with pytest.raises(MissingParameterError):
        ParameterSet({}).get("nope")


def test_percent_strings_are_parsed():
    ps = ParameterSet({"rate": "85%"})
    assert ps.float("rate") == pytest.approx(0.85)


def test_overrides_do_not_mutate_original():
    base = ParameterSet({"a": "1"})
    other = base.with_overrides({"a": 2, "b": 3})
    assert base.get("a") == "1" and other.get("a") == "2" and other.get("b") == "3"
