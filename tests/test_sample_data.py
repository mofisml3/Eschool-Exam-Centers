import pandas as pd

from ecsa.tools.sample_data import PRESETS, generate, generate_preset


def test_single_governorate_generator_keeps_id_format(tmp_path):
    files = generate(tmp_path, students=50, schools=3, districts=2)
    st = pd.read_csv(files["students"])
    assert len(st) == 50 and st["student_id"].str.startswith("ST").all()
    assert pd.read_csv(files["schools"])["school_id"].str.startswith("SCH").all()


def test_iraq3_preset_totals_and_uniqueness(tmp_path):
    files = generate_preset(tmp_path, "iraq3", students=1000, seed=1)
    st = pd.read_csv(files["students"])
    sc = pd.read_csv(files["schools"])
    ss = pd.read_csv(files["student_subjects"])
    assert len(st) == 1000 and st["student_id"].is_unique
    assert set(st["governorate"]) == {"Baghdad", "Basra", "Nineveh"}
    assert st["governorate"].value_counts()["Baghdad"] == 450
    assert sc["school_id"].is_unique and len(sc) == sum(g["schools"] for g in PRESETS["iraq3"])
    assert set(ss["student_id"]) <= set(st["student_id"])
    assert ss.groupby("student_id").size().between(6, 7).all()
    # every district listed in the preset is a real district of that governorate
    for g in PRESETS["iraq3"]:
        assert set(st[st["governorate"] == g["name"]]["district"]) <= set(g["districts"])
