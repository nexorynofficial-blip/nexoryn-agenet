"""
Validator — cross-checks an extracted project payload against what
the real schema actually requires (PORTFOLIO_FORM_REFERENCE.md §4.2),
and produces the human-readable review report the admin sees in the
widget before touching Save Project themselves, e.g.:

    v Title: ABC Construction Website
    ! caseStudy.results.before: Missing
    X caseStudy.results.proof: Missing (required — payload can't be submitted without it)

Contract:

    validate_payload(extraction: ProjectExtraction) -> ReviewReport

    ReviewReport:
        ok: list[str]
        warnings: list[str]
        blocking: list[str]   # required-by-the-real-schema fields still empty
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.extractor import ProjectExtraction

# Required non-empty per projectInputSchema / standardCaseStudySchema /
# designCaseStudySchema (see PORTFOLIO_FORM_REFERENCE.md §4.2). Dotted
# paths are resolved against the payload dict built by extractor.py.
_ALWAYS_REQUIRED = ("title", "industry", "description")
_CASE_STUDY_ALWAYS_REQUIRED = ("category", "summary")
_STANDARD_REQUIRED = (
    "caseStudy.results.before",
    "caseStudy.results.after",
    "caseStudy.results.proof",
)
_DESIGN_REQUIRED = (
    "caseStudy.designProcess.engine",
    "caseStudy.designProcess.refinements",
    "caseStudy.designProcess.qa",
)


@dataclass
class ReviewReport:
    ok: "list[str]" = field(default_factory=list)
    warnings: "list[str]" = field(default_factory=list)
    blocking: "list[str]" = field(default_factory=list)

    def render(self) -> str:
        lines = []
        for entry in self.ok:
            lines.append(f"  v {entry}")
        for entry in self.warnings:
            lines.append(f"  ! {entry}")
        for entry in self.blocking:
            lines.append(f"  X {entry}  (required — can't save without it)")
        return "\n".join(lines)


def _get(payload: dict, dotted_path: str):
    node = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def validate_payload(extraction: ProjectExtraction) -> ReviewReport:
    report = ReviewReport()
    payload = extraction.payload
    is_design = extraction.service == "Brand & Graphic Design"

    required_paths = list(_ALWAYS_REQUIRED) + [
        f"caseStudy.{p}" for p in _CASE_STUDY_ALWAYS_REQUIRED
    ]
    required_paths += list(_DESIGN_REQUIRED if is_design else _STANDARD_REQUIRED)

    for path in required_paths:
        value = _get(payload, path)
        if value in (None, "", []):
            report.blocking.append(path)
        else:
            report.ok.append(f"{path}: {value}")

    for path in extraction.missing:
        if path not in required_paths:
            report.warnings.append(f"{path}: Missing")

    for note in extraction.notes:
        report.warnings.append(note)

    return report
