"""
Centralized configuration for the Nexoryn AI Portfolio Agent.

All modules should import settings from here rather than reading
os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    # Runtime
    PORT: int = int(os.getenv("PORT", "8000"))

    # CORS — the widget runs in the browser on the dashboard's own
    # origin, which is a DIFFERENT origin from wherever this backend
    # is deployed, so the browser will block the /extract call unless
    # that origin is explicitly allowed here. Comma-separated list.
    CORS_ALLOWED_ORIGINS: "list[str]" = [
        o.strip()
        for o in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:5174",
        ).split(",")
        if o.strip()
    ]


settings = Settings()
