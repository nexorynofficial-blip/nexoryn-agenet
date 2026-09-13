"""
FastAPI backend for the Nexoryn AI Portfolio Agent.

This service does exactly one job: turn a free-text project summary
into structured data matching the real dashboard's project schema
(see PORTFOLIO_FORM_REFERENCE.md). It never touches the dashboard
itself — no login, no browser automation, no "save" or "publish"
capability exists anywhere in this codebase.

Everything else (uploading images, filling the live form's fields,
letting the admin review and manually click Save Project) happens
client-side in the widget, running in the admin's own already
authenticated browser tab — see widget/FloatingAgentWidget.tsx.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import extractor, validator
from config import settings

app = FastAPI(title="Nexoryn AI Portfolio Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class ExtractRequest(BaseModel):
    summary: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_model": settings.LLM_MODEL,
    }


@app.post("/extract")
def extract(request: ExtractRequest):
    """Turn a project summary into a structured payload the widget
    can apply to the real form's state, plus a review report of
    what's missing before the admin can save it."""
    try:
        extraction = extractor.extract_project_info(request.summary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    report = validator.validate_payload(extraction)

    return {
        "service": extraction.service,
        "payload": extraction.payload,
        "review": {
            "ok": report.ok,
            "warnings": report.warnings,
            "blocking": report.blocking,
        },
        "missing": extraction.missing,
        "notes": extraction.notes,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
