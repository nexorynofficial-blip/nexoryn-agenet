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

Everything else — every other field in the schema, including
`caseStudy.results.before/after/proof` and the design-process
fields — is MANDATORY and must always be filled with a reasonable
derived value rather than left blank, since the admin reviews and
can edit anything before ever clicking Save Project. The model is
still instructed not to invent *specific* unstated numbers,
percentages, or quotes (those read as verified facts); general
qualitative narrative derived from context is required, not merely
allowed.
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
            "techIcons": {"type": "array", "items": _TECH_ICON, "minItems": 1, "description": "MANDATORY, at least 1 item: the tools/technologies row. Derive from what's named or implied in the summary."},
            "problem": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "MANDATORY, at least 2-4 bullet points, NEVER an empty array: 'The Problem' section. Derive from whatever pain point or need the project addresses, even if not spelled out as a numbered list in the summary."},
            "solution": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "MANDATORY, at least 2-4 bullet points, NEVER an empty array: 'The Solution' section. Derive from what was actually built/delivered."},
            # Standard (Automation / Web Development) only:
            "workflow": {"type": "array", "items": _WORKFLOW_STEP, "minItems": 3, "description": "Standard only. MANDATORY, at least 3-5 steps, NEVER an empty array: the step-by-step flow of how it works end to end. Derive a sensible sequence from the project description even if the summary doesn't spell out steps explicitly."},
            "breakdown": {"type": "array", "items": _TITLED, "minItems": 2, "description": "Standard only. MANDATORY, at least 2-3 items, NEVER an empty array: 'Technical Breakdown' -- deeper implementation detail. Derive plausible technical detail from the technologies and approach mentioned."},
            "keyFeatures": {"type": "array", "items": _TITLED, "minItems": 2, "description": "MANDATORY, at least 2-4 items, NEVER an empty array: 'Key Features' (Standard: inside Results tab; Design: its own tab). Derive standout capabilities from what was delivered."},
            "resultsBefore": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived description of the situation before the project, inferred from the project type if not stated. Avoid inventing specific unstated numbers/percentages -- describe qualitatively instead."},
            "resultsAfter": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived description of the outcome after the project, inferred from the obvious improvement implied by what was built. Avoid inventing specific unstated numbers/percentages -- describe qualitatively instead."},
            "resultsProof": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived explanation of why this matters/what it demonstrates, inferred from the project's stated purpose. Avoid inventing a specific unstated quote or statistic -- describe qualitatively instead."},
            "techStack": {
                "type": "object",
                "description": "Standard only. Map of group name (e.g. 'AI Layer') -> list of items.",
                "additionalProperties": {"type": "array", "items": _TECH_STACK_ITEM},
            },
            "livePreview": {"type": ["string", "null"], "description": "Web Development only. THE ONLY FIELD ALLOWED TO BE LEFT EMPTY. Set to null unless the summary explicitly, literally states a real URL -- never invent, guess, or construct one, even from the client/company name."},
            "scalability": {"type": "array", "items": _TITLED, "minItems": 2, "description": "MANDATORY, at least 2-3 items, NEVER an empty array: 'Scalability & Flexibility' (Standard) / 'Customization & Scalability' (Design). Derive how the solution could grow or be reused, even if not stated."},
            # Design (Brand & Graphic Design) only:
            "designInput": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "Design only. MANDATORY, at least 2 items, NEVER an empty array: 'What The Client Provided'. Derive plausible inputs from the type of design work (e.g. existing logo, brand guidelines) if not stated."},
            "designWorkflow": {"type": "array", "items": _WORKFLOW_STEP, "minItems": 3, "description": "Design only. MANDATORY, at least 3 steps, NEVER an empty array: 'Process Steps'. Derive a sensible design process sequence if not stated."},
            "designEngine": {"type": "string", "description": "Design only: 'How the design was produced'. MANDATORY, never blank -- if not stated, derive a plausible general process from the type of design work described."},
            "designRefinements": {"type": "string", "description": "Design only: 'How feedback was incorporated'. MANDATORY, never blank -- if not stated, derive a plausible general revision process."},
            "designQa": {"type": "string", "description": "Design only: 'How quality was verified'. MANDATORY, never blank -- if not stated, derive a plausible general review/approval step."},
            "useCases": {"type": "array", "items": _TITLED, "minItems": 2, "description": "Design only. MANDATORY, at least 2 items, NEVER an empty array: its own 'Use Cases' tab. Derive plausible real-world applications of the design if not stated."},
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
            "missing": {"type": "array", "items": {"type": "string"}, "description": "Dotted paths that are genuinely impossible to derive anything for. Should almost always be empty except for caseStudy.livePreview -- do not add a path here just because the summary didn't state it explicitly; derive a value instead."},
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

=====================================================================
THE ONE AND ONLY FIELD YOU ARE EVER ALLOWED TO LEAVE EMPTY: livePreview
=====================================================================
caseStudy.livePreview may ONLY be filled in if the summary GENUINELY,
EXPLICITLY, LITERALLY states a real URL (e.g. "https://...", "the
site is live at ...", "acmeinc.com"). Never construct, guess, or
infer one — not even from the client/company name. If the summary
doesn't give one verbatim, leave it null and do NOT add
"caseStudy.livePreview" to statedSensitivePaths.

=====================================================================
EVERY OTHER FIELD IS MANDATORY. NEVER LEAVE ANY OTHER FIELD BLANK.
=====================================================================
This is the most important rule you must follow. If a field isn't
explicitly stated in the summary, you must still fill it by deriving
a reasonable, specific value from the context you do have — the
project type, the industry, the client, the stated problem, the
service category. Do not write vague placeholders like "N/A", "Not
specified", or an empty string, and do not add a field to `missing`
just because the admin didn't spell it out. `missing` exists for
livePreview and for genuinely nothing-to-work-with situations only —
in normal use it should almost always end up empty.

This mandatory-fill rule covers, without exception:
- caseStudy.results.before / after / proof (standard shape)
- caseStudy.designProcess.engine / refinements / qa (design shape)
- problem / solution bullet lists, keyFeatures, scalability,
  techIcons, workflow / designWorkflow steps, breakdown, techStack,
  useCases, designInput — every one of these must have at least a
  sensible derived entry, not an empty array, unless the service
  genuinely gives you nothing to infer from (extremely rare).

A COMMON MISTAKE TO AVOID: returning `problem: []`, `solution: []`,
`workflow: []`, `breakdown: []`, or `scalability: []` as empty arrays
because the summary didn't spell them out as an explicit numbered
list. This is WRONG. These fields still need real, useful bullets
derived from the summary's actual content — read the summary
carefully and pull out (or infer) the problem it addresses, the
solution delivered, the logical steps of how it works, and technical
implementation detail, then write them as bullets yourself. An empty
array here is exactly as wrong as leaving resultsBefore blank — do
not do it. Minimum counts: problem/solution 2-4 bullets each,
workflow/designWorkflow 3-5 steps, breakdown 2-3 items, techIcons at
least 1, keyFeatures 2-4 items, scalability 2-3 items, designInput/
useCases at least 2 items.

How to derive instead of leaving blank — examples:
- Automating a manual process -> before = "The process was handled
  manually, which was slow and error-prone."; after = "The workflow
  now runs automatically with no manual intervention."
- A new marketing website replacing an old one -> before = "The
  previous site was outdated and difficult to navigate."; after =
  "The new site presents the brand clearly and performs well on all
  devices."
- No prior state mentioned at all, just "built a booking site for a
  salon" -> before = "The business had no online way for clients to
  book appointments."; after = "Clients can now book appointments
  directly through the new website."

The only thing to avoid even in derived text is inventing a
*specific* unstated number, percentage, dollar figure, or verbatim
quote — write qualitatively ("significantly reduced manual work")
rather than fabricating a precise, false-sounding statistic ("cut
processing time by 73%"). Qualitative derived narrative is REQUIRED,
not optional — a plausible qualitative sentence is always correct to
write; a specific invented number is the only thing that is not.

`title`, `industry`, `description`, `category`, `summary`, and
`service` are structural fields needed for the record to exist at
all — derive your best reasonable value for these from context even
if not stated verbatim (e.g. a title from the client name + project
type).

Before you call the tool, mentally check every field in the schema
one more time: for each one, either it's stated in the summary, it's
a reasonable derived value, or it's livePreview and genuinely absent.
There should be no other reason for a field to be empty."""


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
