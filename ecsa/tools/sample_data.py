"""Generate synthetic sample data (CSV) for one or more governorates.

    python -m ecsa.tools.sample_data --out data/samples --students 2000 --schools 12
    python -m ecsa.tools.sample_data --out data/demo --preset iraq3 --students 20000

The four files (students, subjects, student_subjects, schools) match the import
specification and can be uploaded on screen 1 of the UI in that order.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

SUBJECTS = [("ARAB", "Arabic"), ("ENGL", "English"), ("MATH", "Mathematics"), ("PHYS", "Physics"),
            ("CHEM", "Chemistry"), ("BIOL", "Biology"), ("ISLM", "Islamic Education")]

FIRST_NAMES = ["Ahmed", "Ali", "Hassan", "Hussein", "Mohammed", "Omar", "Yusuf", "Mustafa", "Karrar", "Zaid",
               "Fatima", "Zainab", "Maryam", "Noor", "Sara", "Aya", "Hawraa", "Rania", "Dina", "Layla"]
FAMILY_NAMES = ["Al-Baghdadi", "Al-Basri", "Al-Mosuli", "Al-Tamimi", "Al-Jubouri", "Al-Saadi", "Al-Dulaimi", "Al-Obaidi",
                "Al-Zubaidi", "Al-Shammari", "Al-Khafaji", "Al-Rubaie", "Al-Janabi", "Al-Azzawi", "Al-Hamdani"]

# Preset: three Iraqi governorates with real districts and approximate centroids.
PRESETS: dict[str, list[dict]] = {
    "iraq3": [
        {"name": "Baghdad", "prefix": "BGD", "share": 0.45, "schools": 20,
         "districts": {"Karkh": (33.310, 44.360), "Rusafa": (33.335, 44.415), "Adhamiyah": (33.375, 44.375),
                       "Kadhimiyah": (33.380, 44.335), "Sadr City": (33.390, 44.455), "Mansour": (33.315, 44.320),
                       "Mahmudiyah": (33.055, 44.360), "Abu Ghraib": (33.300, 44.185)}},
        {"name": "Basra", "prefix": "BSR", "share": 0.30, "schools": 14,
         "districts": {"Basra City": (30.510, 47.810), "Zubair": (30.385, 47.705), "Abu Al-Khaseeb": (30.445, 48.005),
                       "Qurna": (31.010, 47.430), "Shatt Al-Arab": (30.560, 47.900), "Faw": (29.975, 48.475)}},
        {"name": "Nineveh", "prefix": "NNV", "share": 0.25, "schools": 12,
         "districts": {"Mosul Left Bank": (36.360, 43.155), "Mosul Right Bank": (36.335, 43.100), "Hamdaniya": (36.270, 43.375),
                       "Tal Afar": (36.375, 42.450), "Sinjar": (36.320, 41.865), "Sheikhan": (36.695, 43.355)}},
    ],
}


def _person_name(rng: random.Random, gender: str) -> str:
    first = rng.choice(FIRST_NAMES[:10] if gender == "M" else FIRST_NAMES[10:])
    father = rng.choice(FIRST_NAMES[:10])
    return f"{first} {father} {rng.choice(FAMILY_NAMES)}"


def _generate_governorate(rng: random.Random, name: str, prefix: str, students: int, schools: int,
                          districts: dict[str, tuple[float, float]], rounds: int, coords: bool):
    names = list(districts)
    weights = [rng.uniform(0.6, 1.6) for _ in names]
    st_rows, ss_rows, sc_rows = [], [], []
    for i in range(1, students + 1):
        d = rng.choices(names, weights)[0]
        lat, lng = districts[d]
        gender = rng.choice(["M", "F"])
        st_rows.append({"student_id": f"{prefix}{i:06d}", "full_name": _person_name(rng, gender), "governorate": name, "district": d,
                        "lat": round(lat + rng.gauss(0, 0.025), 5) if coords else None,
                        "lng": round(lng + rng.gauss(0, 0.025), 5) if coords else None,
                        "gender": gender, "status": "active"})
        n_sub = rng.choice([6, 7, 7, 7, 7])
        for code, _ in rng.sample(SUBJECTS, n_sub):
            for r in range(1, rounds + 1):
                ss_rows.append({"student_id": f"{prefix}{i:06d}", "subject_id": code, "exam_round": r})
    for i in range(1, schools + 1):
        d = rng.choices(names, weights)[0]
        lat, lng = districts[d]
        sc_rows.append({"school_id": f"{prefix}-SCH{i:03d}", "name": f"{d} Secondary School {i}", "governorate": name, "district": d,
                        "lat": round(lat + rng.gauss(0, 0.02), 5) if coords else None,
                        "lng": round(lng + rng.gauss(0, 0.02), 5) if coords else None,
                        "halls_count": rng.choice([6, 8, 10, 12, 14]), "hall_capacity": rng.choice([20, 25, 30]),
                        "readiness_score": rng.choice([45, 55, 65, 70, 75, 80, 85, 90, 95])})
    return st_rows, ss_rows, sc_rows


def _write(out: Path, st_rows, ss_rows, sc_rows) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, rows in (("students", st_rows), ("student_subjects", ss_rows), ("schools", sc_rows),
                       ("subjects", [{"subject_id": c, "name": n, "stage": "Grade 12", "duration_minutes": 180} for c, n in SUBJECTS])):
        p = out / f"{name}.csv"
        pd.DataFrame(rows).to_csv(p, index=False)
        files[name] = p
    return files


def generate(out: Path, governorate: str = "Basra", students: int = 2000, schools: int = 12, districts: int = 5,
             rounds: int = 1, seed: int = 7, coords: bool = True) -> dict[str, Path]:
    """Single synthetic governorate with generic district names."""
    rng = random.Random(seed)
    base_lat, base_lng = 30.50, 47.78
    dmap = {f"District-{i + 1}": (base_lat + rng.uniform(-0.25, 0.25), base_lng + rng.uniform(-0.25, 0.25)) for i in range(districts)}
    prefix = "".join(ch for ch in governorate.upper() if ch.isalpha())[:3] or "GOV"
    st, ss, sc = _generate_governorate(rng, governorate, prefix, students, schools, dmap, rounds, coords)
    # keep the historical id format for the single-governorate case
    for r in st:
        r["student_id"] = "ST" + r["student_id"][len(prefix):]
    for r in ss:
        r["student_id"] = "ST" + r["student_id"][len(prefix):]
    for r in sc:
        r["school_id"] = "SCH" + r["school_id"].split("SCH")[-1]
    return _write(out, st, ss, sc)


def generate_preset(out: Path, preset: str = "iraq3", students: int = 20000, rounds: int = 1, seed: int = 7,
                    coords: bool = True) -> dict[str, Path]:
    """Several governorates with real district names; `students` is the grand total."""
    spec = PRESETS[preset]
    rng = random.Random(seed)
    st_all, ss_all, sc_all = [], [], []
    remaining = students
    for i, g in enumerate(spec):
        n = remaining if i == len(spec) - 1 else round(students * g["share"])
        remaining -= n
        st, ss, sc = _generate_governorate(rng, g["name"], g["prefix"], n, g["schools"], g["districts"], rounds, coords)
        st_all += st
        ss_all += ss
        sc_all += sc
    return _write(out, st_all, ss_all, sc_all)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/samples")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="multi-governorate preset (overrides --governorate/--schools/--districts)")
    ap.add_argument("--governorate", default="Basra")
    ap.add_argument("--students", type=int, default=2000, help="total students")
    ap.add_argument("--schools", type=int, default=12)
    ap.add_argument("--districts", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-coords", action="store_true")
    a = ap.parse_args(argv)
    if a.preset:
        files = generate_preset(Path(a.out), a.preset, a.students, a.rounds, a.seed, not a.no_coords)
    else:
        files = generate(Path(a.out), a.governorate, a.students, a.schools, a.districts, a.rounds, a.seed, not a.no_coords)
    for k, v in files.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
