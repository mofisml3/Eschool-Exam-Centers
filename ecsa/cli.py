"""Command-line entry point.

    python -m ecsa.cli init-db
    python -m ecsa.cli import students data/samples/students.csv
    python -m ecsa.cli run --name base --governorate Basra --round 1 --start 2026-03-01 [--set key=value ...]
    python -m ecsa.cli list
    python -m ecsa.cli export <scenario_id> out.xlsx [--attendance]
    python -m ecsa.cli approve <scenario_id>
    python -m ecsa.cli compare 1 2 3
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from ecsa.db.session import init_db, session_scope
from ecsa.importer import import_file
from ecsa.reports import export_scenario_excel
from ecsa.scenarios import RunRequest, approve_scenario, compare_scenarios, list_scenarios, run_scenario


def _parse_sets(items: list[str]) -> dict:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        out[k.strip()] = v.strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ecsa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p = sub.add_parser("import"); p.add_argument("kind"); p.add_argument("path"); p.add_argument("--sheet")
    p = sub.add_parser("run")
    p.add_argument("--name", required=True); p.add_argument("--governorate", required=True)
    p.add_argument("--round", type=int, default=1); p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--set", action="append", default=[], help="parameter override key=value")
    p.add_argument("--include", action="append", default=[]); p.add_argument("--exclude", action="append", default=[])
    p = sub.add_parser("list"); p.add_argument("--governorate")
    p = sub.add_parser("export"); p.add_argument("scenario_id", type=int); p.add_argument("path"); p.add_argument("--attendance", action="store_true")
    p = sub.add_parser("approve"); p.add_argument("scenario_id", type=int)
    p = sub.add_parser("compare"); p.add_argument("ids", type=int, nargs="+")
    a = ap.parse_args(argv)

    init_db()
    with session_scope() as s:
        if a.cmd == "init-db":
            print("database ready")
        elif a.cmd == "import":
            rep = import_file(s, a.kind, a.path, a.sheet)
            print(json.dumps(rep.summary()))
            for e in rep.errors[:50]:
                print("  ", e)
        elif a.cmd == "run":
            sc = run_scenario(s, RunRequest(a.name, a.governorate, a.round, a.start, _parse_sets(a.set), a.include, a.exclude))
            print(json.dumps({"scenario_id": sc.scenario_id, "status": sc.status,
                              **{k: v for k, v in sc.kpi_summary.items() if not isinstance(v, (list, dict))}}, indent=2))
            for n in sc.decision_log.get("decision", {}).get("notes", []):
                print("note:", n)
        elif a.cmd == "list":
            for sc in list_scenarios(s, a.governorate):
                print(sc.scenario_id, sc.status, sc.governorate, sc.exam_round, sc.name, sc.kpi_summary.get("overall_utilization"))
        elif a.cmd == "export":
            print(export_scenario_excel(s, a.scenario_id, a.path, a.attendance))
        elif a.cmd == "approve":
            print("approved", approve_scenario(s, a.scenario_id).scenario_id)
        elif a.cmd == "compare":
            print(json.dumps(compare_scenarios(s, a.ids), indent=2, default=str))


if __name__ == "__main__":
    main()
