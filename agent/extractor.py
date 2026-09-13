"""
Extraction Engine — targets the REAL Nexoryn project schema exactly
(see PORTFOLIO_FORM_REFERENCE.md §4.2 for the ground-truth Zod
schema this mirrors), so the widget can hand its output straight to
the dashboard's own form state with no separate field-mapping layer.

Turns the administrator's free-text project summary into a payload
shaped like `projectInputSchema` (minus `slug`/`photoId`/gallery
images, which are handled client-side — see widget/FloatingAgentWidget.tsx)
— WITHOUT inventing facts.

Contract:

    extract_project_info(summary: str) -> ProjectExtraction

    ProjectExtraction:
        service: "Automation" | "Web Development" | "Brand & Graphic Design"
        payload: dict            # shaped like caseStudy + top-level fields
        missing: list[str]       # dotted paths we could not determine
        notes: list[str]

No-hallucination rule: results (`caseStudy.results.before/after/proof`)
and a live project URL (`caseStudy.livePreview`) must be "stated"
only — never derived or invented. If not explicitly present in the
summary, they're left out of `payload` and their dotted path goes
into `missing` instead. This is enforced in code
(`_apply_sensitive_field_backstop`), not just prompted for: the model
must explicitly list which of these paths were genuinely stated, and
anything not on that list is stripped regardless of what the model
put in the main structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from anthropic import Anthropic

from config import settings

SERVICES = ("Automation", "Web Development", "Brand & Graphic Design")

# These map 1:1 to the "never invent" categories from the project spec
# (claimed results/outcomes, project URLs). Zod also requires
# before/after/proof to be non-empty strings when present — so if the
# summary doesn't state them, the payload is genuinely incomplete
# (not just cautious), and that's surfaced as `missing`.
SENSITIVE_PATHS = (
    "caseStudy.results.before",
    "caseStudy.results.after",
    "caseStudy.results.proof",
    "caseStudy.livePreview",
)

_TITLED = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "description"],
}

_WORKFLOW_STEP = {
    "type": "object",
    "properties": {
        "icon": {"type": "string", "description": "A lucide-react icon name, e.g. MessageSquare"},
        "label": {"type": "string"},
    },
    "required": ["icon", "label"],
}

_TECH_ICON = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "icon": {"type": "string", "description": "A lucide-react icon name"},
    },
    "required": ["name", "icon"],
}

_TECH_STACK_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "icon": {"type": "string", "description": "A lucide-react icon name"},
    },
    "required": ["name", "role", "icon"],
}

_EXTRACTION_TOOL = {
    "name": "record_project_extraction",
    "description": (
        "Record the project data extracted from the administrator's summary, "
        "shaped to match the Nexoryn dashboard's real project schema exactly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "enum": list(SERVICES),
                "description": "Which of the 3 real categories this project is. Always pick one.",
            },
            "title": {"type": "string", "description": "Project title, max 200 chars."},
            "industry": {"type": "string", "description": "Free text, e.g. 'Fintech', 'Construction'."},
            "description": {"type": "string", "description": "Card summary shown on the portfolio list, max 1000 chars."},
            "tags": {"type": "array", "items": {"type": "string"}},
            "category": {"type": "string", "description": "Small label shown at the top of the case study page, e.g. 'AI AUTOMATION'."},
            "summary": {"type": "string", "description": "Case study overview summary paragraph."},
            "techIcons": {"type": "array", "items": _TECH_ICON},
            "problem": {"type": "array", "items": {"type": "string"}, "description": "Bullet points, 'The Problem' section."},
            "solution": {"type": "array", "items": {"type": "string"}, "description": "Bullet points, 'The Solution' section."},
            # Standard (Automation / Web Development) only:
            "workflow": {"type": "array", "items": _WORKFLOW_STEP, "description": "Standard only: 'Workflow Steps'."},
            "breakdown": {"type": "array", "items": _TITLED, "description": "Standard only: 'Technical Breakdown'."},
            "keyFeatures": {"type": "array", "items": _TITLED, "description": "Both: 'Key Features' (Standard: inside Results tab; Design: its own tab)."},
            "resultsBefore": {"type": ["string", "null"], "description": "Standard only. Null unless explicitly stated — never invent an outcome."},
            "resultsAfter": {"type": ["string", "null"], "description": "Standard only. Null unless explicitly stated — never invent an outcome."},
            "resultsProof": {"type": ["string", "null"], "description": "Standard only. Null unless explicitly stated — never invent an outcome."},
            "techStack": {
                "type": "object",
                "description": "Standard only. Map of group name (e.g. 'AI Layer') -> list of items.",
                "additionalProperties": {"type": "array", "items": _TECH_STACK_ITEM},
            },
            "livePreview": {"type": ["string", "null"], "description": "Web Development only. Null unless an explicit real URL is stated — never invent one."},
            "scalability": {"type": "array", "items": _TITLED, "description": "Both: 'Scalability & Flexibility' (Standard) / 'Customization & Scalability' (Design)."},
            # Design (Brand & Graphic Design) only:
            "designInput": {"type": "array", "items": {"type": "string"}, "description": "Design only: 'What The Client Provided'."},
            "designWorkflow": {"type": "array", "items": _WORKFLOW_STEP, "description": "Design only: 'Process Steps'."},
            "designEngine": {"type": "string", "description": "Design only: 'How the design was produced'."},
            "designRefinements": {"type": "string", "description": "Design only: 'How feedback was incorporated'."},
            "designQa": {"type": "string", "description": "Design only: 'How quality was verified'."},
            "useCases": {"type": "array", "items": _TITLED, "description": "Design only: its own 'Use Cases' tab."},
            "statedSensitivePaths": {
                "type": "array",
                "items": {"type": "string", "enum": list(SENSITIVE_PATHS)},
                "description": (
                    "List exactly which of these dotted paths were GENUINELY, EXPLICITLY "
                    "stated in the summary: caseStudy.results.before, caseStudy.results.after, "
                    "caseStudy.results.proof, caseStudy.livePreview. Anything not listed here "
                    "will be discarded even if you filled it in above — so only list a path "
                    "if the summary truly states it."
                ),
            },
            "missing": {"type": "array", "items": {"type": "string"}, "description": "Dotted paths you could not confidently fill."},
            "notes": {"type": "array", "items": {"type": "string"}, "description": "Judgment calls, ambiguity, anything the reviewer should double check."},
        },
        "required": ["service", "title", "industry", "description", "tags", "category", "summary", "problem", "solution", "statedSensitivePaths", "missing", "notes"],
    },
}

_SYSTEM_PROMPT = f"""You are the extraction engine for the Nexoryn portfolio agent.

Read the administrator's free-text project summary and call
record_project_extraction exactly once. The output must match the
real Nexoryn dashboard's project schema — populate ONLY the fields
that apply to the `service` you chose:

- "Automation" or "Web Development" (the "standard" shape): use
  workflow, breakdown, keyFeatures, resultsBefore/After/Proof,
  techStack. For "Web Development" specifically, livePreview may
  apply. Leave design-only fields (designInput, designWorkflow,
  designEngine, designRefinements, designQa, useCases) empty/omitted.
- "Brand & Graphic Design" (the "design" shape): use designInput,
  designWorkflow, designEngine, designRefinements, designQa,
  useCases, keyFeatures. Leave standard-only fields (workflow,
  breakdown, resultsBefore/After/Proof, techStack, livePreview)
  empty/omitted.

Hard rule: caseStudy.results.before, caseStudy.results.after,
caseStudy.results.proof, and caseStudy.livePreview may ONLY be
filled in if the summary GENUINELY, EXPLICITLY states them. Never
invent a business outcome, a metric, or a URL. If the summary doesn't
give one of these, leave the corresponding field null and do not add
its path to statedSensitivePaths — it will be treated as missing and
the admin will fill it in by hand.

For every other field, you may derive a reasonable value from what's
stated (e.g. "built with Next.js and Tailwind" -> a techStack group
with those entries; a description of a slow, outdated old site ->
"The Problem" bullets). Never guess wildly — if you can't derive a
value responsibly, omit it and add its path to `missing` instead.

`title`, `industry`, `description`, `category`, `summary`, and
`service` are structural fields needed for the record to exist at
all — derive your best reasonable value for these from context even
if not stated verbatim (e.g. a title from the client name + project
type), but never invent specifics for anything sensitive as
described above."""


@dataclass
class ProjectExtraction:
    service: str
    payload: dict = field(default_factory=dict)
    missing: "list[str]" = field(default_factory=list)
    notes: "list[str]" = field(default_factory=list)


def extract_project_info(summary: str) -> ProjectExtraction:
    """Turn a free-text project summary into a ProjectExtraction.

    Raises ValueError for empty input, RuntimeError if the LLM call is
    misconfigured or fails to return a structured extraction.
    """
    if not summary or not summary.strip():
        raise ValueError("summary must be non-empty")

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to .env before running "
            "extraction."
        )

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_project_extraction"},
        messages=[{"role": "user", "content": summary}],
    )

    tool_use = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use is None:
        raise RuntimeError("LLM did not return a structured extraction.")

    return _to_project_extraction(tool_use.input)


def _to_project_extraction(raw: dict) -> ProjectExtraction:
    service = raw.get("service")
    missing = list(raw.get("missing") or [])
    notes = list(raw.get("notes") or [])
    stated_sensitive = set(raw.get("statedSensitivePaths") or [])

    is_design = service == "Brand & Graphic Design"

    case_study: dict = {
        "category": raw.get("category"),
        "summary": raw.get("summary"),
        "techIcons": raw.get("techIcons") or [],
        "problem": raw.get("problem") or [],
        "solution": raw.get("solution") or [],
        "scalability": raw.get("scalability") or [],
    }

    if is_design:
        case_study["designProcess"] = {
            "input": raw.get("designInput") or [],
            "workflow": raw.get("designWorkflow") or [],
            "engine": raw.get("designEngine"),
            "refinements": raw.get("designRefinements"),
            "qa": raw.get("designQa"),
        }
        case_study["keyFeatures"] = raw.get("keyFeatures") or []
        case_study["useCases"] = raw.get("useCases") or []
    else:
        case_study["workflow"] = raw.get("workflow") or []
        case_study["breakdown"] = raw.get("breakdown") or []
        case_study["techStack"] = raw.get("techStack") or {}
        case_study["results"] = {
            "keyFeatures": raw.get("keyFeatures") or [],
            "before": raw.get("resultsBefore"),
            "after": raw.get("resultsAfter"),
            "proof": raw.get("resultsProof"),
        }
        if service == "Web Development":
            case_study["livePreview"] = raw.get("livePreview")

    payload = {
        "title": raw.get("title"),
        "industry": raw.get("industry"),
        "service": service,
        "description": raw.get("description"),
        "tags": raw.get("tags") or [],
        "caseStudy": case_study,
    }

    _apply_sensitive_field_backstop(payload, stated_sensitive, missing, notes)

    return ProjectExtraction(service=service, payload=payload, missing=missing, notes=notes)


def _apply_sensitive_field_backstop(
    payload: dict, stated_sensitive: set, missing: "list[str]", notes: "list[str]"
) -> None:
    """Code-enforced backstop: regardless of what the model filled in,
    a sensitive path is only kept if the model explicitly listed it
    as genuinely stated. Everything else gets nulled and moved to
    `missing` — never trust the main structure alone."""
    case_study = payload.get("caseStudy", {})

    def strip(path: str, getter, setter) -> None:
        if path in SENSITIVE_PATHS and path not in stated_sensitive:
            if getter() not in (None, ""):
                notes.append(
                    f"Discarded non-stated value for sensitive field '{path}' "
                    "(no-hallucination safeguard)."
                )
            setter(None)
            if path not in missing:
                missing.append(path)

    results = case_study.get("results")
    if results is not None:
        strip("caseStudy.results.before", lambda: results.get("before"), lambda v: results.__setitem__("before", v))
        strip("caseStudy.results.after", lambda: results.get("after"), lambda v: results.__setitem__("after", v))
        strip("caseStudy.results.proof", lambda: results.get("proof"), lambda v: results.__setitem__("proof", v))

    if "livePreview" in case_study:
        strip(
            "caseStudy.livePreview",
            lambda: case_study.get("livePreview"),
            lambda v: case_study.__setitem__("livePreview", v),
        )
