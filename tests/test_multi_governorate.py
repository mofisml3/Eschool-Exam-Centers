"""Phase 8: the same database serves several governorates in isolation."""
from datetime import date

import pandas as pd
from sqlalchemy import select

from ecsa.db.models import Center
from ecsa.importer import import_dataframe
from ecsa.parameters.store import ParameterStore
from ecsa.scenarios import RunRequest, data_summary, list_scenarios, run_scenario
from ecsa.tools.sample_data import generate


def test_governorates_are_isolated(db, tmp_path):
    for gov, seed in (("Basra", 1), ("Nineveh", 2)):
        files = generate(tmp_path / gov, governorate=gov, students=300, schools=6, districts=2, seed=seed)
        # ids must be unique across governorates: prefix them
        for kind in ("students", "subjects", "student_subjects", "schools"):
            df = pd.read_csv(files[kind], dtype=str)
            for col in ("student_id", "school_id"):
                if col in df.columns:
                    df[col] = gov[:3].upper() + "-" + df[col]
            rep = import_dataframe(db, kind, df)
            assert rep.ok, rep.errors
    db.commit()
    ParameterStore(db).set("sessions_per_day", 2, governorate="Nineveh", effective_from=date(2020, 1, 1))

    a = run_scenario(db, RunRequest("b", "Basra", 1, date(2026, 3, 1), {"operating_days_per_round": 10}))
    b = run_scenario(db, RunRequest("n", "Nineveh", 1, date(2026, 3, 1), {"operating_days_per_round": 10}))
    assert a.status == b.status == "completed"
    assert a.kpi_summary["students"] == b.kpi_summary["students"] == 300
    assert a.params_snapshot["sessions_per_day"] == "4" and b.params_snapshot["sessions_per_day"] == "2"
    assert a.decision_log["schedule"]["slots"] == 40 and b.decision_log["schedule"]["slots"] == 20
    for sc, prefix in ((a, "BAS-"), (b, "NIN-")):
        centers = db.execute(select(Center).where(Center.scenario_id == sc.scenario_id)).scalars().all()
        assert centers and all(c.school_id.startswith(prefix) and c.governorate == sc.governorate for c in centers)
    assert [x.scenario_id for x in list_scenarios(db, "Basra")] == [a.scenario_id]
    assert data_summary(db)["governorates"] == ["Basra", "Nineveh"]
    assert data_summary(db, "Nineveh")["students"] == 300
