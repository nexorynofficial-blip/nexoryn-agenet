"""
Offline regression tests for the extraction schema-shaping and the
no-hallucination safety backstop, plus the validator. These make NO
network/API calls — they test `_to_project_extraction` and
`_apply_sensitive_field_backstop` directly with hand-built raw tool
output, exactly as the LLM's response would be shaped.

Run with:
    pytest tests/test_extraction.py -v
"""
import json

from agent.extractor import (
    KEY_FEATURE_COUNT,
    MAX_RESULTS_WORDS,
    MAX_TEXT_CHARS,
    MIN_BREAKDOWN_ITEMS,
    MIN_SCALABILITY_ITEMS,
    ONE_WORD_ICONS,
    TECH_ICON_COUNT,
    _SYSTEM_PROMPT,
    _to_project_extraction,
)
from agent.validator import validate_payload


def _standard_raw(**overrides):
    raw = {
        "service": "Automation",
        "title": "ABC Construction Website",
        "industry": "Construction",
        "description": "A modern site for ABC Construction.",
        "tags": ["Automation", "n8n"],
        "category": "AI AUTOMATION",
        "summary": "An automation project for ABC Construction.",
        "techIcons": [{"name": "n8n", "icon": "Workflow"}],
        "problem": ["Manual process was slow."],
        "solution": ["Automated the workflow with n8n."],
        "workflow": [{"icon": "Mail", "label": "Chat"}],
        "breakdown": [{"title": "Step 1", "description": "Does X."}],
        "keyFeatures": [{"title": "Fast", "description": "Very fast."}],
        "resultsBefore": None,
        "resultsAfter": None,
        "resultsProof": None,
        "techStack": {"Automation": [{"name": "n8n", "role": "Orchestration", "icon": "Workflow"}]},
        "livePreview": None,
        "scalability": [{"title": "Flexible", "description": "Easy to extend."}],
        "statedSensitivePaths": [],
        "missing": [],
        "notes": [],
    }
    raw.update(overrides)
    return raw


def _design_raw(**overrides):
    raw = {
        "service": "Brand & Graphic Design",
        "title": "Rebrand for Acme",
        "industry": "Retail",
        "description": "A full rebrand for Acme.",
        "tags": ["Branding"],
        "category": "BRAND & GRAPHIC DESIGN",
        "summary": "Rebranded Acme's visual identity.",
        "techIcons": [],
        "problem": ["Outdated brand identity."],
        "solution": ["New logo and visual system."],
        "designInput": ["Old logo files", "Brand guidelines PDF"],
        "designWorkflow": [{"icon": "PenTool", "label": "Sketch"}],
        "designEngine": "Designed in Figma through several rounds.",
        "designRefinements": "Incorporated client feedback each round.",
        "designQa": "Reviewed against brand guidelines.",
        "keyFeatures": [{"title": "Modern", "description": "A modern look."}],
        "useCases": [{"title": "Packaging", "description": "Used on packaging."}],
        "scalability": [{"title": "Extensible", "description": "Works across media."}],
        "statedSensitivePaths": [],
        "missing": [],
        "notes": [],
    }
    raw.update(overrides)
    return raw


def test_standard_shape_has_no_design_only_fields():
    extraction = _to_project_extraction(_standard_raw())
    assert extraction.service == "Automation"
    cs = extraction.payload["caseStudy"]
    assert "overview" in cs and "techStack" in cs and "results" in cs
    assert "workflow" in cs["overview"] and "breakdown" in cs["overview"]
    assert "designProcess" not in cs
    assert "useCases" not in cs


def test_standard_overview_fields_are_nested_not_flat():
    """Regression test for the bug that caused every 'fields not
    filled' report: problem/solution/workflow/breakdown must sit under
    caseStudy.overview, exactly as standardCaseStudySchema and
    CaseStudyEditor's fromRawCaseStudy() expect. Emitted flat at the
    top level, the dashboard reads them as undefined and silently
    renders those four sections empty."""
    cs = _to_project_extraction(_standard_raw()).payload["caseStudy"]
    assert cs["overview"]["problem"] == ["Manual process was slow."]
    assert cs["overview"]["solution"] == ["Automated the workflow with n8n."]
    assert cs["overview"]["workflow"] == [{"icon": "Mail", "label": "Chat"}]
    assert cs["overview"]["breakdown"][0] == {"title": "Step 1", "description": "Does X."}
    # And must NOT also appear flat, which would be dead weight the
    # dashboard ignores.
    for key in ("problem", "solution", "workflow", "breakdown"):
        assert key not in cs


def test_design_shape_has_no_standard_only_fields():
    extraction = _to_project_extraction(_design_raw())
    assert extraction.service == "Brand & Graphic Design"
    cs = extraction.payload["caseStudy"]
    assert "designProcess" in cs and "useCases" in cs and "keyFeatures" in cs
    assert "techStack" not in cs and "results" not in cs
    assert cs["designProcess"]["engine"] == "Designed in Figma through several rounds."


def test_design_overview_fields_are_nested_not_flat():
    cs = _to_project_extraction(_design_raw()).payload["caseStudy"]
    assert cs["overview"]["problem"] == ["Outdated brand identity."]
    assert cs["overview"]["solution"] == ["New logo and visual system."]
    # Design's overview has no workflow/breakdown — those belong to
    # designProcess instead.
    assert "workflow" not in cs["overview"]
    assert cs["designProcess"]["workflow"] == [{"icon": "PenTool", "label": "Sketch"}]
    for key in ("problem", "solution"):
        assert key not in cs


def test_results_fields_are_kept_even_without_explicit_statement():
    """Results are narrative, not "exact match" like a URL — the admin
    always reviews before saving, so a reasonable derived value is
    kept rather than discarded, unlike caseStudy.livePreview."""
    raw = _standard_raw(
        resultsBefore="An outdated, slow manual process",
        resultsAfter="Requests are now handled automatically",
        resultsProof="Demonstrates the automation reliably handles routine volume",
        statedSensitivePaths=[],  # not explicitly stated, but that's fine for these fields now
    )
    extraction = _to_project_extraction(raw)
    results = extraction.payload["caseStudy"]["results"]
    assert results["before"] == "An outdated, slow manual process"
    assert results["after"] == "Requests are now handled automatically"
    assert results["proof"] == "Demonstrates the automation reliably handles routine volume"
    assert "caseStudy.results.before" not in extraction.missing
    assert not any("no-hallucination safeguard" in note for note in extraction.notes)


def test_live_preview_discarded_when_not_url_shaped():
    """A value that doesn't actually look like a URL is still
    discarded even without relying on statedSensitivePaths -- this is
    the only remaining hallucination guard for livePreview."""
    raw = _standard_raw(service="Web Development", livePreview="the client's website")
    extraction = _to_project_extraction(raw)
    assert extraction.payload["caseStudy"]["livePreview"] is None
    assert "caseStudy.livePreview" in extraction.missing


def test_live_preview_kept_when_stated():
    raw = _standard_raw(
        service="Web Development",
        livePreview="https://example.com",
        statedSensitivePaths=["caseStudy.livePreview"],
    )
    extraction = _to_project_extraction(raw)
    assert extraction.payload["caseStudy"]["livePreview"] == "https://example.com"


def test_live_preview_kept_when_url_shaped_even_without_stated_flag():
    """Regression test for a real bug: the model correctly wrote a
    real URL into livePreview but repeatedly forgot to ALSO list it in
    statedSensitivePaths, and the old code discarded a genuinely
    correct URL as a result. The URL must be trusted on its own shape,
    not solely on a second, easy-to-forget confirmation flag."""
    raw = _standard_raw(
        service="Web Development",
        livePreview="www.acme-construction.com",
        statedSensitivePaths=[],
    )
    extraction = _to_project_extraction(raw)
    # Normalized to include a scheme, since the real schema validates
    # this with z.string().url() and would reject a bare domain.
    assert extraction.payload["caseStudy"]["livePreview"] == "https://www.acme-construction.com"
    assert "caseStudy.livePreview" not in extraction.missing


def test_validator_ok_when_results_present():
    raw = _standard_raw(
        resultsBefore="Before state",
        resultsAfter="After state",
        resultsProof="Proof text",
    )
    extraction = _to_project_extraction(raw)
    report = validate_payload(extraction)
    assert report.blocking == []


def test_backfill_fills_empty_results_and_problem_solution_workflow():
    """Regression test for a real bug: the model has been observed
    returning empty arrays/strings for problem/solution/workflow/
    breakdown/scalability/results even after being told they're
    mandatory. Prompt-only compliance isn't reliable enough on its
    own, so _to_project_extraction must now guarantee these are never
    blank regardless of what the model returns, and must say so in
    `notes` so the admin knows to double check the auto-filled text."""
    raw = _standard_raw(
        problem=[], solution=[], workflow=[], breakdown=[], scalability=[],
        techIcons=[], keyFeatures=[],
        resultsBefore=None, resultsAfter=None, resultsProof=None,
    )
    extraction = _to_project_extraction(raw)
    cs = extraction.payload["caseStudy"]
    ov = cs["overview"]
    assert ov["problem"] and ov["solution"] and ov["workflow"] and ov["breakdown"]
    assert cs["scalability"] and cs["techIcons"]
    assert cs["results"]["before"] and cs["results"]["after"] and cs["results"]["proof"]
    assert cs["results"]["keyFeatures"]

    report = validate_payload(extraction)
    assert report.blocking == []
    assert any("auto-filled from context" in note for note in extraction.notes)


def test_backfill_fills_empty_design_fields():
    raw = _design_raw(
        problem=[], solution=[], scalability=[], keyFeatures=[], useCases=[],
        designInput=[], designWorkflow=[],
        designEngine="", designRefinements="", designQa="",
    )
    extraction = _to_project_extraction(raw)
    cs = extraction.payload["caseStudy"]
    assert cs["overview"]["problem"] and cs["overview"]["solution"]
    assert cs["scalability"] and cs["keyFeatures"] and cs["useCases"]
    dp = cs["designProcess"]
    assert dp["input"] and dp["workflow"] and dp["engine"] and dp["refinements"] and dp["qa"]

    report = validate_payload(extraction)
    assert report.blocking == []


def _assert_valid_tech_icons(icons):
    assert len(icons) == TECH_ICON_COUNT
    for item in icons:
        assert item["name"] and " " not in item["name"]
        assert item["icon"] in ONE_WORD_ICONS


def test_tech_icons_are_exactly_four_one_word_names():
    raw = _standard_raw(
        techIcons=[
            {"name": "n8n", "icon": "Workflow"},
            {"name": "Workflow orchestration with retries", "icon": "Workflow"},
            {"name": "Google Sheets", "icon": "Sheet"},
        ],
        techStack={
            "AI": [
                {"name": "OpenAI", "role": "Classification", "icon": "Brain"},
                {"name": "Supabase", "role": "Storage", "icon": "Database"},
            ]
        },
    )
    extraction = _to_project_extraction(raw)
    icons = extraction.payload["caseStudy"]["techIcons"]
    _assert_valid_tech_icons(icons)
    assert [i["name"] for i in icons] == ["n8n", "GoogleSheets", "OpenAI", "Supabase"]
    assert any("topped up" in note for note in extraction.notes)


def test_tech_icons_trimmed_to_four_and_icons_made_renderable():
    names = ["React", "Vite", "Tailwind", "Prisma", "PostgreSQL", "Vercel"]
    raw = _standard_raw(
        service="Web Development",
        techIcons=[{"name": n, "icon": "Code2"} for n in names],
    )
    icons = _to_project_extraction(raw).payload["caseStudy"]["techIcons"]
    _assert_valid_tech_icons(icons)
    assert [i["name"] for i in icons] == names[:TECH_ICON_COUNT]


def test_tech_icons_padded_to_four_when_model_returns_none():
    _assert_valid_tech_icons(
        _to_project_extraction(_design_raw(techIcons=[])).payload["caseStudy"]["techIcons"]
    )
    _assert_valid_tech_icons(
        _to_project_extraction(_standard_raw(techIcons=[], techStack={})).payload["caseStudy"]["techIcons"]
    )


def test_overview_workflow_icons_and_labels_are_one_word():
    raw = _standard_raw(
        workflow=[
            {"icon": "MessageSquare", "label": "Client submits a request via WhatsApp"},
            {"icon": "Brain", "label": "Classify"},
            {"icon": "Send", "label": "the reply is sent"},
        ]
    )
    steps = _to_project_extraction(raw).payload["caseStudy"]["overview"]["workflow"]
    assert len(steps) == 3
    for step in steps:
        assert " " not in step["label"]
        assert step["icon"] in ONE_WORD_ICONS
    assert steps[1] == {"icon": "Brain", "label": "Classify"}
    assert steps[2]["label"] == "Reply"


def test_design_process_workflow_is_left_as_is():
    steps = [{"icon": "PenTool", "label": "Initial concept sketches"}]
    cs = _to_project_extraction(_design_raw(designWorkflow=steps)).payload["caseStudy"]
    assert cs["designProcess"]["workflow"] == steps


def test_no_em_dashes_anywhere_in_output():
    raw = _standard_raw(
        title="PULSE — Project Intelligence Platform",
        description="Reads how work moves over time — not just task status.",
        problem=["Risk flags went stale — until the nightly job ran."],
        resultsBefore="Slow -- and manual.",
        notes=["Check the tech stack — it was inferred."],
    )
    extraction = _to_project_extraction(raw)
    dumped = json.dumps(extraction.payload, ensure_ascii=False)
    assert "—" not in dumped and " -- " not in dumped
    assert all("—" not in note for note in extraction.notes)
    assert extraction.payload["title"] == "PULSE: Project Intelligence Platform"
    assert extraction.payload["description"] == "Reads how work moves over time, not just task status."
    assert extraction.payload["caseStudy"]["results"]["before"] == "Slow, and manual."


def test_system_prompt_only_mentions_em_dash_inside_the_rule():
    assert _SYSTEM_PROMPT.count("—") == 1


def _titled(prefix, n):
    return [{"title": f"{prefix} {i}", "description": f"Detail {i}."} for i in range(n)]


def test_key_features_are_exactly_six():
    few = _to_project_extraction(_standard_raw(keyFeatures=_titled("Feature", 1)))
    feats = few.payload["caseStudy"]["results"]["keyFeatures"]
    assert len(feats) == KEY_FEATURE_COUNT
    assert feats[0] == {"title": "Feature 0", "description": "Detail 0."}
    assert any("filled out to" in note for note in few.notes)

    many = _to_project_extraction(_standard_raw(keyFeatures=_titled("Feature", 9)))
    assert many.payload["caseStudy"]["results"]["keyFeatures"] == _titled("Feature", 9)[:KEY_FEATURE_COUNT]

    design = _to_project_extraction(_design_raw(keyFeatures=_titled("Feature", 2)))
    assert len(design.payload["caseStudy"]["keyFeatures"]) == KEY_FEATURE_COUNT


def test_scalability_has_at_least_eight_and_keeps_extras():
    few = _to_project_extraction(_standard_raw(scalability=_titled("Scale", 1)))
    assert len(few.payload["caseStudy"]["scalability"]) == MIN_SCALABILITY_ITEMS

    many = _to_project_extraction(_standard_raw(scalability=_titled("Scale", 11)))
    assert many.payload["caseStudy"]["scalability"] == _titled("Scale", 11)

    design = _to_project_extraction(_design_raw(scalability=[]))
    assert len(design.payload["caseStudy"]["scalability"]) == MIN_SCALABILITY_ITEMS


def test_breakdown_has_at_least_six_and_keeps_extras():
    few = _to_project_extraction(_standard_raw(breakdown=_titled("Part", 2)))
    assert len(few.payload["caseStudy"]["overview"]["breakdown"]) == MIN_BREAKDOWN_ITEMS

    many = _to_project_extraction(_standard_raw(breakdown=_titled("Part", 7)))
    assert many.payload["caseStudy"]["overview"]["breakdown"] == _titled("Part", 7)


def test_padding_never_duplicates_a_title_the_model_already_used():
    raw = _standard_raw(scalability=[{"title": "Modular Architecture", "description": "Ours."}])
    titles = [i["title"] for i in _to_project_extraction(raw).payload["caseStudy"]["scalability"]]
    assert len(titles) == MIN_SCALABILITY_ITEMS
    assert len(set(t.lower() for t in titles)) == len(titles)


def test_description_and_summary_capped_at_500_characters():
    long_text = "This sentence describes the platform in detail. " * 30
    raw = _standard_raw(description=long_text, summary=long_text)
    extraction = _to_project_extraction(raw)
    for text in (extraction.payload["description"], extraction.payload["caseStudy"]["summary"]):
        assert len(text) <= MAX_TEXT_CHARS
        assert text.endswith(".")

    short = _to_project_extraction(_standard_raw()).payload
    assert short["description"] == "A modern site for ABC Construction."


def test_results_paragraphs_capped_at_500_words():
    long_text = "The team relied on manual steps that slowed every request down. " * 60
    raw = _standard_raw(resultsBefore=long_text, resultsAfter=long_text, resultsProof=long_text)
    results = _to_project_extraction(raw).payload["caseStudy"]["results"]
    for key in ("before", "after", "proof"):
        assert len(results[key].split()) <= MAX_RESULTS_WORDS
        assert results[key].endswith(".")

    ok = _to_project_extraction(_standard_raw(resultsBefore="Short before.")).payload
    assert ok["caseStudy"]["results"]["before"] == "Short before."
