"""Runtime configuration. Only infrastructure settings live here — never
operational parameters (those are in the `parameters` table)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("ECSA_DATA_DIR", ROOT_DIR / "data"))
EXPORT_DIR = DATA_DIR / "exports"


def normalize_database_url(url: str) -> str:
    """Managed PostgreSQL providers hand out postgres:// or postgresql:// URLs;
    SQLAlchemy 2 with psycopg 3 needs postgresql+psycopg://."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalize_database_url(os.getenv("ECSA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'ecsa.db'}"))
