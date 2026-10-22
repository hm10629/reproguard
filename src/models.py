"""Data models shared by the analyzer, reports, CLI, and web UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ALLOWED_STATUSES = {
    "found",
    "partial",
    "missing",
    "not_applicable",
    "needs_review",
}

ALLOWED_SEVERITIES = {"high", "medium", "low"}


@dataclass(frozen=True)
class Evidence:
    source: str
    location: str
    quote: str
    line: int | None = None
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    rule_id: str
    title: str
    status: str
    severity: str
    finding: str
    evidence: list[Evidence] = field(default_factory=list)
    suggestion: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported finding status: {self.status}")
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"Unsupported severity: {self.severity}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


@dataclass
class Report:
    project_name: str
    paper_path: str
    repository_path: str
    findings: list[Finding]
    summary: dict[str, Any]
    generated_at: str = ""
    model_assistance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "project_name": self.project_name,
            "paper_path": self.paper_path,
            "repository_path": self.repository_path,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
        }
        # Optional block: omitted entirely when the rule-only mode runs, so old
        # JSON consumers keep working unchanged.
        if self.model_assistance is not None:
            result["model_assistance"] = self.model_assistance
        return result
