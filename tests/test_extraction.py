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
    assert "workflow" in cs and "breakdown" in cs and "techStack" in cs and "results" in cs
    assert "designProcess" not in cs
    assert "useCases" not in cs


def test_design_shape_has_no_standard_only_fields():
    extraction = _to_project_extraction(_design_raw())
    assert extraction.service == "Brand & Graphic Design"
    cs = extraction.payload["caseStudy"]
    assert "designProcess" in cs and "useCases" in cs and "keyFeatures" in cs
    assert "workflow" not in cs and "techStack" not in cs and "results" not in cs
    assert cs["designProcess"]["engine"] == "Designed in Figma through several rounds."


def test_sensitive_results_fields_discarded_when_not_stated():
    raw = _standard_raw(
        resultsBefore="Slow manual process",
        resultsAfter="40% faster",
        resultsProof="Client confirmed the improvement",
        statedSensitivePaths=[],  # model did NOT confirm these were genuinely stated
    )
    extraction = _to_project_extraction(raw)
    results = extraction.payload["caseStudy"]["results"]
    assert results["before"] is None
    assert results["after"] is None
    assert results["proof"] is None
    assert "caseStudy.results.before" in extraction.missing
    assert "caseStudy.results.after" in extraction.missing
    assert "caseStudy.results.proof" in extraction.missing
    assert any("no-hallucination safeguard" in note for note in extraction.notes)


def test_sensitive_results_fields_kept_when_explicitly_stated():
    raw = _standard_raw(
        resultsBefore="Manual triage took 3 days",
        resultsAfter="Now resolved in under an hour",
        resultsProof="Confirmed via support ticket logs",
        statedSensitivePaths=[
            "caseStudy.results.before",
            "caseStudy.results.after",
            "caseStudy.results.proof",
        ],
    )
    extraction = _to_project_extraction(raw)
    results = extraction.payload["caseStudy"]["results"]
    assert results["before"] == "Manual triage took 3 days"
    assert results["after"] == "Now resolved in under an hour"
    assert results["proof"] == "Confirmed via support ticket logs"
    assert "caseStudy.results.before" not in extraction.missing


def test_live_preview_discarded_when_not_stated():
    raw = _standard_raw(service="Web Development", livePreview="https://example.com")
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


def test_validator_flags_missing_results_as_blocking_for_standard():
    extraction = _to_project_extraction(_standard_raw())
    report = validate_payload(extraction)
    assert "caseStudy.results.before" in report.blocking
    assert "caseStudy.results.after" in report.blocking
    assert "caseStudy.results.proof" in report.blocking


def test_validator_ok_when_results_present():
    raw = _standard_raw(
        resultsBefore="Before state",
        resultsAfter="After state",
        resultsProof="Proof text",
        statedSensitivePaths=[
            "caseStudy.results.before",
            "caseStudy.results.after",
            "caseStudy.results.proof",
        ],
    )
    extraction = _to_project_extraction(raw)
    report = validate_payload(extraction)
    assert report.blocking == []


def test_validator_flags_missing_design_process_fields_as_blocking():
    raw = _design_raw(designEngine="", designRefinements="", designQa="")
    extraction = _to_project_extraction(raw)
    report = validate_payload(extraction)
    assert "caseStudy.designProcess.engine" in report.blocking
    assert "caseStudy.designProcess.refinements" in report.blocking
    assert "caseStudy.designProcess.qa" in report.blocking
