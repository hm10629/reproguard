"""Application service that coordinates extraction, scanning, and rules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .model_assist import ModelConfig, run_model_assistance
from .models import Finding, Report
from .paper_extract import load_paper
from .repository_scan import scan_repository
from .rules import run_checks


ACTIONABLE_STATUSES = ("missing", "partial", "needs_review")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_action_items(findings: list[Finding]) -> list[dict]:
    """Turn unresolved findings into an ordered repair checklist.

    ``found`` and ``not_applicable`` findings need no repair, so they are
    excluded. Remaining items are sorted by risk level and then rule id, which
    keeps the checklist stable across runs.
    """

    actionable = [item for item in findings if item.status in ACTIONABLE_STATUSES]
    ordered = sorted(
        actionable,
        key=lambda item: (SEVERITY_ORDER[item.severity], item.rule_id),
    )
    return [
        {
            "task_id": f"T{index:02d}",
            "rule_id": item.rule_id,
            "title": item.title,
            "severity": item.severity,
            "status": item.status,
            "action": item.suggestion,
            "evidence_locations": [evidence.location for evidence in item.evidence],
        }
        for index, item in enumerate(ordered, start=1)
    ]


def summarize(findings: list[Finding]) -> dict:
    summary = {
        "total_findings": len(findings),
        "found_count": sum(item.status == "found" for item in findings),
        "partial_count": sum(item.status == "partial" for item in findings),
        "missing_count": sum(item.status == "missing" for item in findings),
        "needs_review_count": sum(item.status == "needs_review" for item in findings),
        "not_applicable_count": sum(item.status == "not_applicable" for item in findings),
        "high_risk_count": sum(item.severity == "high" and item.status in {"missing", "partial"} for item in findings),
        "medium_risk_count": sum(item.severity == "medium" and item.status in {"missing", "partial"} for item in findings),
        "low_risk_count": sum(item.severity == "low" and item.status in {"missing", "partial"} for item in findings),
    }
    evidence_required = sum(item.status != "missing" for item in findings)
    evidence_found = sum(bool(item.evidence) for item in findings if item.status != "missing")
    summary["evidence_coverage"] = round(
        evidence_found / evidence_required if evidence_required else 1.0,
        3,
    )
    summary["action_items"] = build_action_items(findings)
    return summary


def analyze(
    paper_path: Path,
    repository_path: Path,
    *,
    model_config: ModelConfig | None = None,
) -> Report:
    """Run one reproducibility inspection.

    The rule engine always produces the authoritative findings. When an
    optional ``model_config`` is enabled, a locally hosted open model adds an
    auxiliary ``model_assistance`` block; it never changes a finding.
    """

    paper_path = Path(paper_path)
    repository_path = Path(repository_path)
    paper = load_paper(paper_path)
    repository = scan_repository(repository_path)
    findings = run_checks(paper, repository)
    assistance = None
    if model_config is not None and model_config.enabled:
        assistance = run_model_assistance(paper, repository, model_config).to_dict()
    return Report(
        project_name=repository_path.name or str(repository_path),
        paper_path=str(paper_path.resolve()),
        repository_path=str(repository_path.resolve()),
        findings=findings,
        summary=summarize(findings),
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_assistance=assistance,
    )
