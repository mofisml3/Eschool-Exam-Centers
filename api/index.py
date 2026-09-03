"""Vercel serverless entry point. Vercel's Python runtime looks for an ASGI
`app` object in files under /api; vercel.json routes every path here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ecsa.api.app import create_app  # noqa: E402

app = create_app()
