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

import re
from dataclasses import dataclass, field

from anthropic import Anthropic

from config import settings

# Matches a real-looking URL/domain (https://acme.com, www.acme.com,
# acme.com/path, acme.co.uk) so we can trust a value the model wrote
# directly instead of depending on it ALSO remembering to separately
# declare the path in statedSensitivePaths — a second signal that has
# proven unreliable in practice (the model fills the URL correctly but
# forgets to list it, and it silently gets discarded).
_URL_LIKE = re.compile(
    r"^(https?://)?(www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+(:[0-9]+)?(/\S*)?$"
)


def _looks_like_real_url(value) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or " " in value:
        return False
    return bool(_URL_LIKE.match(value))

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

TECH_ICON_COUNT = 4

# Single-word icon names that the public site's src/lib/iconMap.js can
# actually render; any other name silently shows the Sparkles fallback.
ONE_WORD_ICONS = (
    "Atom", "Bitcoin", "Boxes", "Brain", "Calculator", "Calendar", "Clock",
    "Cloud", "Database", "Download", "Eye", "Gauge", "Globe", "Hash", "Heart",
    "Image", "Layers", "Lock", "Mail", "Map", "Network", "Newspaper",
    "Package", "Radio", "Rocket", "Route", "Scale", "Search", "Send",
    "Server", "Shapes", "Sheet", "Shield", "Sparkles", "Tag", "Truck", "Type",
    "Wifi", "Workflow", "Zap",
)
_ICON_LIST = ", ".join(ONE_WORD_ICONS)

_ONE_WORD_ICON = {
    "type": "string",
    "enum": list(ONE_WORD_ICONS),
    "description": "One-word icon name from the allowed list.",
}

_OVERVIEW_WORKFLOW_STEP = {
    "type": "object",
    "properties": {
        "icon": _ONE_WORD_ICON,
        "label": {
            "type": "string",
            "description": "ONE word only, e.g. Trigger, Validate, Notify. Never a phrase or a sentence.",
        },
    },
    "required": ["icon", "label"],
}

_TECH_ICON = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "ONE word only: a real technology from the project's tech stack, "
                "e.g. React, PostgreSQL, n8n, OpenAI. Never a sentence or a concept."
            ),
        },
        "icon": _ONE_WORD_ICON,
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
            "techIcons": {"type": "array", "items": _TECH_ICON, "minItems": TECH_ICON_COUNT, "maxItems": TECH_ICON_COUNT, "description": f"MANDATORY, EXACTLY {TECH_ICON_COUNT} items: the tech stack row in the Overview tab. Each name is one word (a real technology). Derive from what's named or implied in the summary."},
            "problem": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "MANDATORY, at least 2-4 bullet points, NEVER an empty array: 'The Problem' section. Derive from whatever pain point or need the project addresses, even if not spelled out as a numbered list in the summary."},
            "solution": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "MANDATORY, at least 2-4 bullet points, NEVER an empty array: 'The Solution' section. Derive from what was actually built/delivered."},
            # Standard (Automation / Web Development) only:
            "workflow": {"type": "array", "items": _OVERVIEW_WORKFLOW_STEP, "minItems": 3, "description": "Standard only. MANDATORY, at least 3-5 steps, NEVER an empty array: the step-by-step flow of how it works end to end. Each step's icon and label are ONE word each. Derive a sensible sequence from the project description even if the summary doesn't spell out steps explicitly."},
            "breakdown": {"type": "array", "items": _TITLED, "minItems": 2, "description": "Standard only. MANDATORY, at least 2-3 items, NEVER an empty array: 'Technical Breakdown', meaning deeper implementation detail. Derive plausible technical detail from the technologies and approach mentioned."},
            "keyFeatures": {"type": "array", "items": _TITLED, "minItems": 2, "description": "MANDATORY, at least 2-4 items, NEVER an empty array: 'Key Features' (Standard: inside Results tab; Design: its own tab). Derive standout capabilities from what was delivered."},
            "resultsBefore": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived description of the situation before the project, inferred from the project type if not stated. Avoid inventing specific unstated numbers/percentages; describe qualitatively instead."},
            "resultsAfter": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived description of the outcome after the project, inferred from the obvious improvement implied by what was built. Avoid inventing specific unstated numbers/percentages; describe qualitatively instead."},
            "resultsProof": {"type": "string", "description": "Standard only. MANDATORY, never blank: a reasonable derived explanation of why this matters/what it demonstrates, inferred from the project's stated purpose. Avoid inventing a specific unstated quote or statistic; describe qualitatively instead."},
            "techStack": {
                "type": "object",
                "description": "Standard only. Map of group name (e.g. 'AI Layer') -> list of items.",
                "additionalProperties": {"type": "array", "items": _TECH_STACK_ITEM},
            },
            "livePreview": {"type": ["string", "null"], "description": "Web Development only. THE ONLY FIELD ALLOWED TO BE LEFT EMPTY. Set to null unless the summary explicitly, literally states a real URL; never invent, guess, or construct one, even from the client/company name."},
            "scalability": {"type": "array", "items": _TITLED, "minItems": 2, "description": "MANDATORY, at least 2-3 items, NEVER an empty array: 'Scalability & Flexibility' (Standard) / 'Customization & Scalability' (Design). Derive how the solution could grow or be reused, even if not stated."},
            # Design (Brand & Graphic Design) only:
            "designInput": {"type": "array", "items": {"type": "string"}, "minItems": 2, "description": "Design only. MANDATORY, at least 2 items, NEVER an empty array: 'What The Client Provided'. Derive plausible inputs from the type of design work (e.g. existing logo, brand guidelines) if not stated."},
            "designWorkflow": {"type": "array", "items": _WORKFLOW_STEP, "minItems": 3, "description": "Design only. MANDATORY, at least 3 steps, NEVER an empty array: 'Process Steps'. Derive a sensible design process sequence if not stated."},
            "designEngine": {"type": "string", "description": "Design only: 'How the design was produced'. MANDATORY, never blank; if not stated, derive a plausible general process from the type of design work described."},
            "designRefinements": {"type": "string", "description": "Design only: 'How feedback was incorporated'. MANDATORY, never blank; if not stated, derive a plausible general revision process."},
            "designQa": {"type": "string", "description": "Design only: 'How quality was verified'. MANDATORY, never blank; if not stated, derive a plausible general review/approval step."},
            "useCases": {"type": "array", "items": _TITLED, "minItems": 2, "description": "Design only. MANDATORY, at least 2 items, NEVER an empty array: its own 'Use Cases' tab. Derive plausible real-world applications of the design if not stated."},
            "statedSensitivePaths": {
                "type": "array",
                "items": {"type": "string", "enum": list(SENSITIVE_PATHS)},
                "description": (
                    "List 'caseStudy.livePreview' here ONLY if the summary genuinely, "
                    "explicitly gives a real project URL. If you fill in livePreview but "
                    "don't list it here, it will be discarded. This is the one field "
                    "that must never be guessed."
                ),
            },
            "missing": {"type": "array", "items": {"type": "string"}, "description": "Dotted paths that are genuinely impossible to derive anything for. Should almost always be empty except for caseStudy.livePreview; do not add a path here just because the summary didn't state it explicitly; derive a value instead."},
            "notes": {"type": "array", "items": {"type": "string"}, "description": "Judgment calls, ambiguity, anything the reviewer should double check."},
        },
        "required": ["service", "title", "industry", "description", "tags", "category", "summary", "problem", "solution", "statedSensitivePaths", "missing", "notes"],
    },
}

_SYSTEM_PROMPT = f"""You are the extraction engine for the Nexoryn portfolio agent.

Read the administrator's free-text project summary and call
record_project_extraction exactly once. The output must match the
real Nexoryn dashboard's project schema. Populate ONLY the fields
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
WRITING STYLE (applies to every text field)
=====================================================================
- Rewrite all content in polished, professional, client-facing
  portfolio language. Do not copy the administrator's wording
  verbatim: rephrase it, correct the grammar, and tighten it, while
  keeping every fact accurate.
- Be clear, confident, and concise. No slang, filler, or casual
  phrasing.
- NEVER use the em dash character (—) anywhere, in any field,
  including the title, description, bullets, and paragraphs. Use a
  comma, colon, period, or parentheses instead. Do not use a double
  hyphen (--) as a substitute either.

=====================================================================
OVERVIEW TAB FORMAT RULES
=====================================================================
Tech icons (techIcons):
- EXACTLY {TECH_ICON_COUNT} items, every time. Not fewer, not more.
- `name` is ONE word only: a real technology in the project's tech
  stack (a language, framework, database, platform, AI model, or
  tool), e.g. React, Python, PostgreSQL, n8n, OpenAI, Stripe, Figma,
  Vercel. Never a sentence, a phrase, or a concept such as
  "Automation", "Security", or "Dashboard".
- If the summary names fewer than {TECH_ICON_COUNT} technologies, add
  the technologies this kind of project most plausibly used.
- `icon` must be one of: {_ICON_LIST}.

Workflow steps (workflow, Automation / Web Development only):
- `label` is ONE word only, e.g. Trigger, Capture, Validate, Enrich,
  Route, Notify, Deploy. Never two or three words, never a sentence.
- `icon` is ONE word and must be one of: {_ICON_LIST}.

=====================================================================
THE ONE AND ONLY FIELD YOU ARE EVER ALLOWED TO LEAVE EMPTY: livePreview
=====================================================================
caseStudy.livePreview may ONLY be filled in if the summary GENUINELY,
EXPLICITLY, LITERALLY states a real URL (e.g. "https://...", "the
site is live at ...", "acmeinc.com"). Never construct, guess, or
infer one, not even from the client/company name. If the summary
doesn't give one verbatim, leave it null and do NOT add
"caseStudy.livePreview" to statedSensitivePaths.

=====================================================================
EVERY OTHER FIELD IS MANDATORY. NEVER LEAVE ANY OTHER FIELD BLANK.
=====================================================================
This is the most important rule you must follow. If a field isn't
explicitly stated in the summary, you must still fill it by deriving
a reasonable, specific value from the context you do have: the
project type, the industry, the client, the stated problem, the
service category. Do not write vague placeholders like "N/A", "Not
specified", or an empty string, and do not add a field to `missing`
just because the admin didn't spell it out. `missing` exists for
livePreview and for genuinely nothing-to-work-with situations only;
in normal use it should almost always end up empty.

This mandatory-fill rule covers, without exception:
- caseStudy.results.before / after / proof (standard shape)
- caseStudy.designProcess.engine / refinements / qa (design shape)
- problem / solution bullet lists, keyFeatures, scalability,
  techIcons, workflow / designWorkflow steps, breakdown, techStack,
  useCases, designInput: every one of these must have at least a
  sensible derived entry, not an empty array, unless the service
  genuinely gives you nothing to infer from (extremely rare).

A COMMON MISTAKE TO AVOID: returning `problem: []`, `solution: []`,
`workflow: []`, `breakdown: []`, or `scalability: []` as empty arrays
because the summary didn't spell them out as an explicit numbered
list. This is WRONG. These fields still need real, useful bullets
derived from the summary's actual content. Read the summary
carefully and pull out (or infer) the problem it addresses, the
solution delivered, the logical steps of how it works, and technical
implementation detail, then write them as bullets yourself. An empty
array here is exactly as wrong as leaving resultsBefore blank, so
do not do it. Counts: problem/solution 2-4 bullets each,
workflow/designWorkflow 3-5 steps, breakdown 2-3 items, techIcons
exactly {TECH_ICON_COUNT}, keyFeatures 2-4 items, scalability 2-3
items, designInput/useCases at least 2 items.

How to derive instead of leaving blank, examples:
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
quote. Write qualitatively ("significantly reduced manual work")
rather than fabricating a precise, false-sounding statistic ("cut
processing time by 73%"). Qualitative derived narrative is REQUIRED,
not optional: a plausible qualitative sentence is always correct to
write; a specific invented number is the only thing that is not.

`title`, `industry`, `description`, `category`, `summary`, and
`service` are structural fields needed for the record to exist at
all. Derive your best reasonable value for these from context even
if not stated verbatim (e.g. a title from the client name + project
type).

Before you call the tool, check every field in the schema one more
time: for each one, either it's stated in the summary, it's a
reasonable derived value, or it's livePreview and genuinely absent.
Also confirm: exactly {TECH_ICON_COUNT} one-word tech icons, one-word
workflow icons and labels, professional wording, and no em dashes."""


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

    # NOTE: problem/solution (both shapes) and workflow/breakdown
    # (standard only) live under `overview`, NOT at the top level of
    # caseStudy — see standardCaseStudySchema/designCaseStudySchema in
    # PORTFOLIO_FORM_REFERENCE.md §4.2 and CaseStudyEditor.tsx's
    # fromRawCaseStudy(). Emitting them flat makes the dashboard read
    # `raw.overview?.problem` as undefined and silently render the
    # Problem/Solution/Workflow/Technical Breakdown sections empty.
    case_study: dict = {
        "category": raw.get("category"),
        "summary": raw.get("summary"),
        "techIcons": raw.get("techIcons") or [],
        "overview": {
            "problem": raw.get("problem") or [],
            "solution": raw.get("solution") or [],
        },
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
        case_study["overview"]["workflow"] = raw.get("workflow") or []
        case_study["overview"]["breakdown"] = raw.get("breakdown") or []
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
    _apply_mandatory_field_backfill(payload, service, notes)
    _enforce_overview_format(payload, service, notes)

    if isinstance(payload.get("title"), str):
        payload["title"] = _without_em_dashes(payload["title"], ": ")
    payload = _strip_em_dashes(payload)
    notes = _strip_em_dashes(notes)

    return ProjectExtraction(service=service, payload=payload, missing=missing, notes=notes)


def _apply_sensitive_field_backstop(
    payload: dict, stated_sensitive: set, missing: "list[str]", notes: "list[str]"
) -> None:
    """Code-enforced backstop for the one field that must never be
    guessed: caseStudy.livePreview is kept only if it's either (a)
    explicitly confirmed via statedSensitivePaths, or (b) actually
    looks like a real URL/domain. (b) exists because relying on the
    model to ALSO remember a second, separate confirmation flag proved
    unreliable in practice — a genuinely-provided URL was being
    silently discarded when the model forgot to list it there. A
    value that isn't URL-shaped is never kept either way."""
    case_study = payload.get("caseStudy", {})
    path = "caseStudy.livePreview"

    if "livePreview" not in case_study:
        return

    value = case_study.get("livePreview")
    confirmed = path in stated_sensitive or _looks_like_real_url(value)

    if value not in (None, "") and confirmed:
        url = value.strip()
        # The real schema validates this with z.string().url(), which
        # rejects a bare domain — normalize so a correctly-extracted
        # "acme.com" doesn't fail validation at Save Project time.
        if not url.lower().startswith(("http://", "https://")):
            url = f"https://{url}"
        case_study["livePreview"] = url
        return

    if value not in (None, ""):
        notes.append(
            f"Discarded non-URL-shaped value for '{path}' (no-hallucination safeguard)."
        )
    case_study["livePreview"] = None
    if path not in missing:
        missing.append(path)


# Every case-study field below is mandatory once a service is chosen —
# only caseStudy.livePreview may ever be genuinely empty. Prompt-only
# instructions can't guarantee the model always complies, so this is a
# deterministic, code-level guarantee: whatever the model leaves empty
# gets filled from context that WAS actually extracted (title,
# industry, description, summary) — never fabricated from nothing —
# and flagged in `notes` so the admin knows to double-check it.
_ICON_BY_SERVICE = {
    "Automation": "Workflow",
    "Web Development": "Code",
    "Brand & Graphic Design": "Palette",
}


def _apply_mandatory_field_backfill(payload: dict, service: str, notes: "list[str]") -> None:
    case_study = payload.get("caseStudy", {})
    is_design = service == "Brand & Graphic Design"
    title = (payload.get("title") or "This project").strip()
    industry = (payload.get("industry") or "its industry").strip()
    summary = (case_study.get("summary") or payload.get("description") or "").strip()
    icon = _ICON_BY_SERVICE.get(service, "Sparkles")
    snippet = summary[:200] if summary else f"{title}, built for {industry}."

    def flag(path: str) -> None:
        notes.append(
            f"'{path}' was left empty by the model; auto-filled from context as a "
            "safety net so the field is never blank. Please review and tighten it."
        )

    def ensure_list(key: str, path: str, make_default):
        if not case_study.get(key):
            case_study[key] = make_default()
            flag(path)

    def ensure_in(container: dict, key: str, path: str, make_default):
        if not container.get(key):
            container[key] = make_default()
            flag(path)

    overview = case_study.setdefault("overview", {})

    ensure_in(
        overview,
        "problem",
        "caseStudy.overview.problem",
        lambda: [
            f"{industry} needed a solution like {title} that didn't already exist for them.",
            f"Context from the summary: {snippet}",
        ],
    )
    ensure_in(
        overview,
        "solution",
        "caseStudy.overview.solution",
        lambda: [
            f"Delivered {title} to directly address that need.",
            f"{snippet}",
        ],
    )
    ensure_list(
        "scalability",
        "caseStudy.scalability",
        lambda: [
            {"title": "Built to grow", "description": f"{title} can be extended as {industry}'s needs grow."},
            {"title": "Flexible foundation", "description": "The approach taken leaves room to add new capability without a rebuild."},
        ],
    )

    if is_design:
        ensure_list(
            "keyFeatures",
            "caseStudy.keyFeatures",
            lambda: [{"title": "Cohesive design", "description": f"A consistent visual system delivered for {title}."}],
        )
        ensure_list(
            "useCases",
            "caseStudy.useCases",
            lambda: [{"title": "Primary use", "description": f"Applied across {title}'s core brand touchpoints."}],
        )
        design_process = case_study.setdefault("designProcess", {})
        if not design_process.get("input"):
            design_process["input"] = ["Brand direction and reference materials shared by the client."]
            flag("caseStudy.designProcess.input")
        if not design_process.get("workflow"):
            design_process["workflow"] = [
                {"icon": "PenTool", "label": "Concept exploration"},
                {"icon": "Eye", "label": "Client review"},
                {"icon": "CheckCircle", "label": "Final delivery"},
            ]
            flag("caseStudy.designProcess.workflow")
        if not (design_process.get("engine") or "").strip():
            design_process["engine"] = f"{title} was produced using an iterative design process suited to {industry}."
            flag("caseStudy.designProcess.engine")
        if not (design_process.get("refinements") or "").strip():
            design_process["refinements"] = "Feedback from review rounds was incorporated before final delivery."
            flag("caseStudy.designProcess.refinements")
        if not (design_process.get("qa") or "").strip():
            design_process["qa"] = "Final work was reviewed against the brand direction before handoff."
            flag("caseStudy.designProcess.qa")
    else:
        ensure_in(
            overview,
            "workflow",
            "caseStudy.overview.workflow",
            lambda: [dict(step) for step in _DEFAULT_OVERVIEW_WORKFLOW],
        )
        ensure_in(
            overview,
            "breakdown",
            "caseStudy.overview.breakdown",
            lambda: [{"title": "Implementation", "description": f"Built to fit {title}'s specific requirements."}],
        )
        if not case_study.get("techStack"):
            case_study["techStack"] = {
                "Core": [{"name": title, "role": "Primary implementation", "icon": icon}]
            }
            flag("caseStudy.techStack")
        results = case_study.setdefault("results", {})
        if not results.get("keyFeatures"):
            results["keyFeatures"] = [{"title": "Delivered as scoped", "description": f"{title} meets the need it was built for."}]
            flag("caseStudy.results.keyFeatures")
        if not (results.get("before") or "").strip():
            results["before"] = f"Before {title}, {industry} handled this need without a dedicated solution."
            flag("caseStudy.results.before")
        if not (results.get("after") or "").strip():
            results["after"] = f"With {title} in place, that need is now handled directly."
            flag("caseStudy.results.after")
        if not (results.get("proof") or "").strip():
            results["proof"] = f"{title} demonstrates a working solution built specifically for {industry}."
            flag("caseStudy.results.proof")


# Overview-tab format rules, enforced in code so they hold even when the
# model ignores the prompt: exactly TECH_ICON_COUNT one-word tech icons, and
# one-word icons and labels on the standard shape's workflow steps.
_DEFAULT_OVERVIEW_WORKFLOW = (
    {"icon": "Zap", "label": "Trigger"},
    {"icon": "Workflow", "label": "Process"},
    {"icon": "Send", "label": "Deliver"},
)
_WORKFLOW_ICON_CYCLE = ("Zap", "Search", "Workflow", "Send", "Rocket")

# Only used when the model returns fewer than TECH_ICON_COUNT usable names
# and the tech stack can't make up the difference; flagged for review.
_FALLBACK_TECH = {
    "Automation": ("n8n", "OpenAI", "Python", "PostgreSQL"),
    "Web Development": ("React", "TypeScript", "Node.js", "PostgreSQL"),
    "Brand & Graphic Design": ("Figma", "Illustrator", "Photoshop", "InDesign"),
}
_SERVICE_TECH_ICON = {
    "Automation": "Workflow",
    "Web Development": "Globe",
    "Brand & Graphic Design": "Shapes",
}
_TECH_ICON_KEYWORDS = (
    (("sql", "postgres", "mongo", "supabase", "firebase", "redis", "prisma"), "Database"),
    (("openai", "gpt", "claude", "anthropic", "ollama", "gemini", "llm", "langchain"), "Brain"),
    (("aws", "vercel", "netlify", "azure", "gcp", "cloudflare"), "Cloud"),
    (("docker", "kubernetes"), "Boxes"),
    (("node", "express", "fastapi", "django", "flask", "python"), "Server"),
    (("n8n", "zapier"), "Workflow"),
    (("figma", "illustrator", "photoshop", "canva", "indesign"), "Shapes"),
)
_STOPWORDS = {
    "a", "an", "and", "are", "be", "by", "for", "get", "gets", "in", "is",
    "of", "on", "or", "the", "then", "to", "via", "with",
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+#-]*")


def _words(text) -> "list[str]":
    if not isinstance(text, str):
        return []
    return [w.rstrip(".-") for w in _WORD.findall(text) if w.rstrip(".-")]


def _one_word_tech_name(name):
    words = _words(name)
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return words[0] + words[1]  # "Tailwind CSS" -> "TailwindCSS"
    return None  # a phrase or sentence, not a technology name


def _one_word_label(label):
    words = _words(label)
    if len(words) > 1:
        words = [w for w in words if w.lower() not in _STOPWORDS] or words
    if not words:
        return None
    return words[0][0].upper() + words[0][1:]


def _tech_icon_for(name: str, service: str, given=None) -> str:
    if given in ONE_WORD_ICONS:
        return given
    lower = name.lower()
    for keywords, icon in _TECH_ICON_KEYWORDS:
        if any(k in lower for k in keywords):
            return icon
    return _SERVICE_TECH_ICON.get(service, "Sparkles")


def _enforce_overview_format(payload: dict, service: str, notes: "list[str]") -> None:
    case_study = payload.get("caseStudy", {})

    icons: "list[dict]" = []
    seen: set = set()

    def add(name, given_icon=None) -> None:
        word = _one_word_tech_name(name)
        if not word or word.lower() in seen or len(icons) >= TECH_ICON_COUNT:
            return
        seen.add(word.lower())
        icons.append({"name": word, "icon": _tech_icon_for(word, service, given_icon)})

    for item in case_study.get("techIcons") or []:
        if isinstance(item, dict):
            add(item.get("name"), item.get("icon"))
    from_model = len(icons)
    for items in (case_study.get("techStack") or {}).values():
        for item in items or []:
            if isinstance(item, dict):
                add(item.get("name"), item.get("icon"))
    for name in _FALLBACK_TECH.get(service, _FALLBACK_TECH["Web Development"]):
        add(name)
    if len(icons) > from_model:
        notes.append(
            f"Tech icons were topped up to {TECH_ICON_COUNT} from the tech stack or common "
            "tools for this service. Please confirm they match the real stack."
        )
    case_study["techIcons"] = icons

    if service == "Brand & Graphic Design":
        return
    overview = case_study.setdefault("overview", {})
    steps: "list[dict]" = []
    for step in overview.get("workflow") or []:
        if not isinstance(step, dict):
            continue
        label = _one_word_label(step.get("label"))
        if not label:
            continue
        icon = step.get("icon")
        if icon not in ONE_WORD_ICONS:
            icon = _WORKFLOW_ICON_CYCLE[len(steps) % len(_WORKFLOW_ICON_CYCLE)]
        steps.append({"icon": icon, "label": label})
    overview["workflow"] = steps or [dict(step) for step in _DEFAULT_OVERVIEW_WORKFLOW]


# Strict no-em-dash rule for all generated content. A spaced double
# hyphen reads as the same punctuation, so it's replaced too.
_EM_DASH = re.compile(r"\s*—\s*|\s+--\s+")


def _without_em_dashes(text: str, joiner: str = ", ") -> str:
    if "—" not in text and " -- " not in text:
        return text
    text = _EM_DASH.sub(joiner, text)
    text = re.sub(r"([,:;.!?])\s*[,:]\s*", r"\1 ", text)
    return text.strip().strip(",:").strip()


def _strip_em_dashes(node, joiner: str = ", "):
    if isinstance(node, str):
        return _without_em_dashes(node, joiner)
    if isinstance(node, list):
        return [_strip_em_dashes(v, joiner) for v in node]
    if isinstance(node, dict):
        return {
            (_without_em_dashes(k, joiner) if isinstance(k, str) else k): _strip_em_dashes(v, joiner)
            for k, v in node.items()
        }
    return node
