"""Runtime configuration. Only infrastructure settings live here — never
operational parameters (those are in the `parameters` table)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
# Serverless platforms only allow writes under /tmp.
DATA_DIR = Path(os.getenv("ECSA_DATA_DIR", "/tmp/ecsa" if IS_SERVERLESS else ROOT_DIR / "data"))
EXPORT_DIR = DATA_DIR / "exports"


def normalize_database_url(url: str) -> str:
    """Managed PostgreSQL providers hand out postgres:// or postgresql:// URLs;
    SQLAlchemy 2 with psycopg 3 needs postgresql+psycopg://."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _database_url_from_env() -> tuple[str, str]:
    """Return (url, source). Accepts our own variable first, then the names
    that hosted PostgreSQL integrations (Neon on Vercel, Render, Heroku) set."""
    for name in ("ECSA_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING"):
        v = os.getenv(name)
        if v:
            return normalize_database_url(v), name
    return f"sqlite:///{DATA_DIR / 'ecsa.db'}", "default-sqlite"


DATABASE_URL, DATABASE_URL_SOURCE = _database_url_from_env()
# True when running serverless on a throw-away SQLite file: data will not persist.
EPHEMERAL_STORAGE = IS_SERVERLESS and DATABASE_URL_SOURCE == "default-sqlite"
