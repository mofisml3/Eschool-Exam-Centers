# ECSA — Exam Centers & Student Allocation System

Decides how many exam centers a governorate needs, ranks and approves schools
as centers, builds the session timetable, and seats every student
(center → hall → session → seat) for every subject. Purely operational: no
financial data (a cost module is planned for a later phase).

Specifications: `docs/Overview.md`, `docs/Requirements.md`.
Architecture, phases and every decision taken on gaps in the spec:
`specs/implementation_plan.md`.

## Quick start

```bash
pip install -e ".[dev,ui]"
python -m ecsa.tools.sample_data --out data/samples --students 10000 --schools 15
python -m ecsa.cli init-db
for k in students subjects student_subjects schools; do python -m ecsa.cli import $k data/samples/$k.csv; done
python -m ecsa.cli run --name base --governorate Basra --round 1 --start 2026-03-01
python -m ecsa.cli run --name tighter --governorate Basra --round 1 --start 2026-03-01 --set safe_utilization_rate=0.75
python -m ecsa.cli compare 1 2
python -m ecsa.cli export 1 data/exports/base.xlsx --attendance
```

UI (six screens): `streamlit run ecsa/ui/app.py`
API: `uvicorn ecsa.api.main:app --reload` then open `/docs`
Tests: `pytest`

Database defaults to SQLite at `data/ecsa.db`; set `ECSA_DATABASE_URL` for PostgreSQL.

## Import file columns

| table | required columns | optional |
|---|---|---|
| students | student_id, full_name, governorate, district | lat, lng, gender, status |
| subjects | subject_id, name | stage, duration_minutes |
| student_subjects | student_id, subject_id, exam_round | |
| schools | school_id, name, governorate, district, halls_count, hall_capacity | lat, lng, readiness_score |
| school_halls | school_id, hall_name, capacity | |

## How a run works

1. **Parameters** are resolved from the `parameters` table (governorate row beats global, latest effective date wins) and snapshotted on the scenario.
2. **Ranking**: schools below `min_readiness_score` are excluded; the rest get a weighted score of capacity, readiness and proximity to student density.
3. **Decision**: `centers = CEIL(exam_cases ÷ average center capacity)`, trimmed or extended so utilization falls within the target range; reserve centers = `CEIL(20% × main)`, kept inactive.
4. **Schedule**: subjects that share students never share a slot; each subject gets many sittings spread across the round.
5. **Allocation**: district by district, nearest center with a free seat, least-filled slot; hard limits on safe hall capacity and one exam per slot per student.
6. **Seats** are numbered per hall-slot with districts interleaved.
7. **Validation** and **KPIs** are stored with the scenario; every decision is in `decision_log`.

## Layout

```
ecsa/db          models + DB constraints          ecsa/engines     pure engines (capacity, ranking, scheduling, allocation, seating, validation, kpi, geo)
ecsa/parameters  ParameterStore + defaults.json   ecsa/scenarios   run / preview / approve / compare
ecsa/importer    validated CSV/Excel import       ecsa/reports     sheets, utilization, Excel export
ecsa/api         FastAPI                          ecsa/ui          Streamlit
ecsa/cli.py      command line                     ecsa/tools       sample data generator
```
