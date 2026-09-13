"""
Vercel serverless entry point. Vercel's Python runtime looks for a
module-level `app` (ASGI application) in this file — it's the same
FastAPI app as main.py, just re-exported from where Vercel expects
to find it.
"""
from main import app  # noqa: F401
