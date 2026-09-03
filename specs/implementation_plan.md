# ECSA — Implementation Plan & Decision Log

Source documents: `docs/Overview.md`, `docs/Requirements.md`.
This file records the architecture, the phased plan, and every decision taken
where the source documents were silent or ambiguous.

## 1. Decisions on gaps in the specification

| # | Gap in the documents | Decision | Where it lives |
|---|---|---|---|
| D1 | Reserve-center rule ("one reserve center when utilization exceeds a limit") | **Owner decision:** reserve centers = `CEIL(reserve_center_ratio × main centers)`, default ratio 20%. Reserve centers are approved but `activation_status = inactive`. | parameter `reserve_center_ratio` |
| D2 | Meaning of the three categories primary / supporting / reserve (أساسي / مساند / احتياط) | *primary* = the centers given by `CEIL(exam_cases ÷ avg capacity)`, then trimmed from the bottom while the actual capacity of the remaining schools keeps utilization ≤ `target_utilization_max` (chosen schools are usually larger than the average the formula uses). *supporting* = extra centers added one at a time until projected utilization ≤ `target_utilization_max`. *reserve* = D1, computed on primary + supporting. | parameters `target_utilization_min`, `target_utilization_max` |
| D3 | Composite ranking weights | Defaults 0.40 capacity, 0.40 readiness, 0.20 proximity. Each factor is min-max normalized to 0–1 across candidates before weighting. | parameters `rank_weight_capacity`, `rank_weight_readiness`, `rank_weight_proximity` |
| D4 | Minimum acceptable readiness score | Score scale 0–100, minimum 60. Schools below it are excluded from candidacy (hard constraint). | parameter `min_readiness_score` |
| D5 | How subjects map to sessions | The capacity formula (halls × sessions/day × days) only holds if every subject is offered in **many sittings** across the round. Therefore: subjects that share at least one student are placed in a conflict graph and greedily colored; each color class is a group of subjects that may share a slot. Groups are assigned round-robin to the `(exam_date, session_no)` slots of the round, so every subject gets ≈ `slots ÷ groups` sittings. One `sessions` row = one subject in one slot. | `engines/scheduling.py` |
| D6 | Student time-clash rule | Hard: a student never has two sessions in the same slot. Soft, parameterized: at most `max_exams_per_student_per_day` exams per day (default 1). | parameter `max_exams_per_student_per_day` |
| D7 | Proximity when lat/lng is missing | Priority: haversine distance if both sides have coordinates; else 0 km if same district; else distance between district centroids (mean of known coordinates in each district); else `unknown_distance_km` (default 50). | `engines/geo.py` |
| D8 | Seeding halls from a school | When a school is approved, `halls_count` rows are created with `capacity = hall_capacity` and `safe_capacity = FLOOR(capacity × safe_utilization_rate)`. Real per-hall data can be imported into the added `school_halls` table and overrides the seed. | `scenarios/service.py`, table `school_halls` |
| D9 | Seat numbering | Seats are numbered sequentially per (hall, slot) after allocation; students in the same hall are re-ordered round-robin across districts so neighbors come from different districts as far as possible. | `engines/seating.py` |
| D10 | Load-balancing between centers | The greedy picks the nearest center; ties and near-ties (distance difference ≤ `load_balance_tolerance_km`, default 5 km) are resolved toward the center with lower current fill. Within a center the least-filled slot is chosen. | parameter `load_balance_tolerance_km` |
| D11 | Emergency seat margin | Soft: `emergency_margin_rate` (default 3%) of safe seats per hall-slot are left empty when possible; the greedy uses them only when no other seat exists, and the KPI report flags every hall-slot that used its margin. | parameter `emergency_margin_rate` |
| D12 | Multi-governorate | Every operational table carries `governorate` from day one. Parameters are resolved governorate-specific first, then global. Phase 8 becomes a UI switch, not a schema change. | all models |
| D13 | Cost | Not in the MVP (owner confirmation). Data model keeps staff head-counts, operating days and per-scenario KPI JSON so a later cost engine can attach without schema changes. | `scenarios.kpi_summary` is free-form JSON |
| D14 | `docs/business-rules.md` referenced by CLAUDE.md does not exist | Business rules are taken from sections 4–5 of `docs/Requirements.md`. | — |
| D15 | Default parameter values | Loaded from `ecsa/parameters/defaults.json` into the `parameters` table on first run. Engines never read this file; they only read the table. | `parameters/defaults.json` |

## 2. Architecture

```
ecsa/
  config.py            DB URL and paths from environment
  db/models.py         SQLAlchemy models + DB-level constraints
  db/session.py        engine / session factory / init
  parameters/          ParameterStore (single source of operational values) + defaults.json
  importer/            Excel/CSV readers with validation → DB
  engines/
    geo.py             distance resolution (D7)
    capacity.py        exam cases, center capacity, centers needed (خ1–خ3)
    ranking.py         composite score, categorization (خ4, D2)
    scheduling.py      slots, conflict groups, sessions (خ5, D5)
    allocation.py      constrained greedy (خ6, D10, D11)
    seating.py         seat numbering (خ7, D9)
    validation.py      post-run checks (خ8)
  scenarios/service.py run pipeline, snapshot params, KPIs, compare, approve
  reports/             attendance sheets, distribution sheets, utilization, Excel export
  api/                 FastAPI routers
  ui/app.py            Streamlit screens (6 screens)
tests/                 pytest, one module per engine
```

Engines are pure functions over plain Python objects (dataclasses). They do not
touch the database. The scenario service loads data, calls engines, and
persists results. This keeps every rule unit-testable and lets OR-Tools be
plugged in later as an alternative allocation engine.

## 3. Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| 1 | Repo scaffold, packaging, plan | `pytest` runs |
| 2 | Data model, DB constraints, ParameterStore, defaults seeding | uniqueness constraints rejected by DB; parameter resolution tests |
| 3 | Capacity & decision engine + ranking | formulas match spec examples; reserve = ceil(20%) |
| 4 | Scheduling engine | zero same-slot clash for any student |
| 5 | Allocation + seating + validation | 100% students seated, no hall over safe capacity, no clash |
| 6 | Importer, scenarios, reports & Excel export | end-to-end run on sample data |
| 7 | FastAPI + Streamlit UI | six screens usable |
| 8 | Multi-governorate | switch governorate, rerun, isolated results |
