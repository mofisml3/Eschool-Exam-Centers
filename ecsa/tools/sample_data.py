"""Generate synthetic sample data (CSV) for a governorate.

    python -m ecsa.tools.sample_data --out data/samples --students 2000 --schools 12
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

SUBJECTS = [("ARAB", "Arabic"), ("ENGL", "English"), ("MATH", "Mathematics"), ("PHYS", "Physics"),
            ("CHEM", "Chemistry"), ("BIOL", "Biology"), ("ISLM", "Islamic Education")]


def generate(out: Path, governorate: str = "Basra", students: int = 2000, schools: int = 12, districts: int = 5,
             rounds: int = 1, seed: int = 7, coords: bool = True) -> dict[str, Path]:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    base_lat, base_lng = 30.50, 47.78
    district_names = [f"District-{i + 1}" for i in range(districts)]
    centroid = {d: (base_lat + rng.uniform(-0.25, 0.25), base_lng + rng.uniform(-0.25, 0.25)) for d in district_names}
    weights = [rng.uniform(0.5, 1.5) for _ in district_names]

    st_rows, ss_rows = [], []
    for i in range(1, students + 1):
        d = rng.choices(district_names, weights)[0]
        lat, lng = centroid[d]
        st_rows.append({"student_id": f"ST{i:06d}", "full_name": f"Student {i}", "governorate": governorate, "district": d,
                        "lat": round(lat + rng.gauss(0, 0.03), 5) if coords else None,
                        "lng": round(lng + rng.gauss(0, 0.03), 5) if coords else None,
                        "gender": rng.choice(["M", "F"]), "status": "active"})
        n_sub = rng.choice([6, 7, 7, 7, 7])
        for code, _ in rng.sample(SUBJECTS, n_sub):
            for r in range(1, rounds + 1):
                ss_rows.append({"student_id": f"ST{i:06d}", "subject_id": code, "exam_round": r})

    sc_rows = []
    for i in range(1, schools + 1):
        d = rng.choice(district_names)
        lat, lng = centroid[d]
        sc_rows.append({"school_id": f"SCH{i:03d}", "name": f"School {i}", "governorate": governorate, "district": d,
                        "lat": round(lat + rng.gauss(0, 0.02), 5) if coords else None,
                        "lng": round(lng + rng.gauss(0, 0.02), 5) if coords else None,
                        "halls_count": rng.choice([6, 8, 10, 12]), "hall_capacity": rng.choice([20, 25, 30]),
                        "readiness_score": rng.choice([45, 55, 65, 70, 75, 80, 85, 90, 95])})

    files = {}
    for name, rows in (("students", st_rows), ("student_subjects", ss_rows), ("schools", sc_rows),
                       ("subjects", [{"subject_id": c, "name": n, "stage": "Grade 12", "duration_minutes": 180} for c, n in SUBJECTS])):
        p = out / f"{name}.csv"
        pd.DataFrame(rows).to_csv(p, index=False)
        files[name] = p
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/samples")
    ap.add_argument("--governorate", default="Basra")
    ap.add_argument("--students", type=int, default=2000)
    ap.add_argument("--schools", type=int, default=12)
    ap.add_argument("--districts", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-coords", action="store_true")
    a = ap.parse_args(argv)
    files = generate(Path(a.out), a.governorate, a.students, a.schools, a.districts, a.rounds, a.seed, not a.no_coords)
    for k, v in files.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
