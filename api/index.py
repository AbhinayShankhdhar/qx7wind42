"""Vercel entry point: Vercel runs files in /api as Python serverless functions.
We simply expose the same FastAPI app the Docker setup uses."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
