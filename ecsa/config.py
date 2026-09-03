"""Runtime configuration. Only infrastructure settings live here — never
operational parameters (those are in the `parameters` table)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("ECSA_DATA_DIR", ROOT_DIR / "data"))
EXPORT_DIR = DATA_DIR / "exports"
DATABASE_URL = os.getenv("ECSA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'ecsa.db'}")
