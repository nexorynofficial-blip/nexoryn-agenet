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

No-hallucination rule, narrowed to what's actually unverifiable: a
live project URL (`caseStudy.livePreview`) must be "stated" only —
never derived or invented, since a wrong guess there is an actively
broken link, not just cautious editorial content. If not explicitly
present in the summary, it's left out of `payload` and its dotted
path goes into `missing` instead. This is enforced in code
(`_apply_sensitive_field_backstop`), not just prompted for: the model
must explicitly confirm the URL was genuinely stated, and it's
stripped regardless of what the model put in the main structure if
not confirmed.

Everything else — including `caseStudy.results.before/after/proof` —
is always filled with a reasonable derived value rather than left
blank, since the admin reviews and can edit anything before ever
clicking Save Project. The model is still instructed not to invent
*specific* unstated numbers, percentages, or quotes (those read as
verified facts); general qualitative narrative derived from context
is fine and expected.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from anthropic import Anthropic

from config import settings

SERVICES = ("Automation", "Web Development", "Brand & Graphic Design")

# Only a real URL is "exact-match" enough to require explicit
# statement — a wrong guess here is an actively broken link, unlike
# narrative fields where a reasonable derived description is fine.
SENSITIVE_PATHS = ("caseStudy.livePreview",)

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
            "resultsBefore": {"type": "string", "description": "Standard only. Always fill with a reasonable derived description of the situation before the project — never leave blank. Avoid inventing specific unstated numbers/percentages."},
            "resultsAfter": {"type": "string", "description": "Standard only. Always fill with a reasonable derived description of the outcome after the project — never leave blank. Avoid inventing specific unstated numbers/percentages."},
            "resultsProof": {"type": "string", "description": "Standard only. Always fill with a reasonable derived explanation of why this matters/what it demonstrates — never leave blank. Avoid inventing a specific unstated quote or statistic."},
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
                    "List 'caseStudy.livePreview' here ONLY if the summary genuinely, "
                    "explicitly gives a real project URL. If you fill in livePreview but "
                    "don't list it here, it will be discarded — this is the one field "
                    "that must never be guessed."
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

Hard rule, and the ONLY field this applies to: caseStudy.livePreview
may ONLY be filled in if the summary GENUINELY, EXPLICITLY states a
real URL. Never invent one. If the summary doesn't give one, leave it
null and do not add it to statedSensitivePaths.

Every other field must always be filled with a reasonable derived
value — do not leave a field blank just because the summary didn't
state it explicitly. This includes caseStudy.results.before/after/proof
and the design-process fields (engine/refinements/qa): derive a
plausible, general description from context (e.g. a slow, outdated
old site -> before = "An outdated site that was slow and hard to
navigate"; automating a manual process -> after = "Requests are now
classified and resolved automatically"). The one thing to avoid even
here is inventing a *specific* unstated number, percentage, dollar
figure, or quote — write qualitatively instead of fabricating a
precise statistic. Only add a field's path to `missing` if there is
truly nothing in the summary to reasonably derive from — this should
be rare.

`title`, `industry`, `description`, `category`, `summary`, and
`service` are structural fields needed for the record to exist at
all — derive your best reasonable value for these from context even
if not stated verbatim (e.g. a title from the client name + project
type)."""


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
    """Code-enforced backstop for the one field that must never be
    guessed: regardless of what the model filled in, caseStudy.livePreview
    is only kept if the model explicitly confirmed it was genuinely
    stated — never trust the main structure alone."""
    case_study = payload.get("caseStudy", {})
    path = "caseStudy.livePreview"

    if "livePreview" in case_study and path not in stated_sensitive:
        if case_study.get("livePreview") not in (None, ""):
            notes.append(
                f"Discarded non-stated value for '{path}' (no-hallucination safeguard)."
            )
        case_study["livePreview"] = None
        if path not in missing:
            missing.append(path)
