"""
Offline regression tests for the extraction schema-shaping and the
no-hallucination safety backstop, plus the validator. These make NO
network/API calls — they test `_to_project_extraction` and
`_apply_sensitive_field_backstop` directly with hand-built raw tool
output, exactly as the LLM's response would be shaped.

Run with:
    pytest tests/test_extraction.py -v
"""
from agent.extractor import ProjectExtraction, _to_project_extraction
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
        "workflow": [{"icon": "MessageSquare", "label": "Chat"}],
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
    assert cs["overview"]["workflow"] == [{"icon": "MessageSquare", "label": "Chat"}]
    assert cs["overview"]["breakdown"] == [{"title": "Step 1", "description": "Does X."}]
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
