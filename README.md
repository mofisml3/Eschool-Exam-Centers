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

Database defaults to SQLite at `data/ecsa.db`; set `ECSA_DATABASE_URL` for PostgreSQL
(`postgres://…`, `postgresql://…` and `postgresql+psycopg://…` are all accepted).

## Deployment

The app needs a long-running Python process and a persistent database, so it is
hosted on **Render** (not Vercel, which only runs short serverless functions).

**One-click on Render:** in the Render dashboard choose *New → Blueprint*, pick this
repository and the `main` branch. `render.yaml` creates three resources:

| resource | what it is | URL |
|---|---|---|
| `ecsa-db` | managed PostgreSQL | injected as `ECSA_DATABASE_URL` |
| `ecsa-api` | FastAPI (Docker) | `https://ecsa-api-<id>.onrender.com/docs` |
| `ecsa-ui` | Streamlit, six screens (Docker) | `https://ecsa-ui-<id>.onrender.com` |

Notes on the free plan: web services sleep after 15 minutes idle and take ~30 s to wake;
the free PostgreSQL expires after 30 days, so change `plan: free` under `databases`
to `basic-256mb` for production. Tables and default parameters are created on first start.

**UI on Streamlit Community Cloud (free, no code):** at https://share.streamlit.io choose
*Create app*, pick this repository, branch `main`, main file `ecsa/ui/app.py`. Under
*Advanced settings → Secrets* paste one line with the same Neon connection string Vercel uses:

```toml
ECSA_DATABASE_URL = "postgresql://user:password@host/dbname?sslmode=require"
```

The UI and the Vercel API then share one database. The Home screen has a one-click demo
data loader for exploring the whole journey.

**API on Vercel (serverless):** `vercel.json` routes every path to `api/index.py`, which
exposes the FastAPI app; Vercel installs from `pyproject.toml` (with `requirements.txt` as a fallback), so keep both in sync. Vercel cannot run the
Streamlit UI (no long-running processes) — use the Swagger page at `/docs`, or the UI on Render.

1. In the Vercel project open *Storage → Create Database → Neon* (free) and connect it to the
   project. The integration sets `DATABASE_URL`, which the app picks up automatically
   (`ECSA_DATABASE_URL` takes precedence if you set it yourself).
2. Redeploy. `GET /health` shows which database is in use; if no database is attached it
   falls back to a throw-away SQLite file under `/tmp` and reports a `warning`.
3. `maxDuration` is 60 s in `vercel.json`; raise it if Fluid Compute is enabled and exports
   of very large scenarios time out.

**Locally with PostgreSQL:** `docker compose up --build` then open
http://localhost:8501 (UI) and http://localhost:8000/docs (API).

**Tests against PostgreSQL:** `ECSA_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db pytest`

## Demo data

`data/demo/` holds a ready-to-upload set: 20,000 students across Baghdad, Basra and Nineveh
with real district names and coordinates, 46 candidate schools, 7 subjects. Upload on screen 1
in the order students → subjects → student_subjects → schools. Regenerate or resize with:

```bash
python -m ecsa.tools.sample_data --out data/demo --preset iraq3 --students 20000
```

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
