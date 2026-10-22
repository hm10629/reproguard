"""Mutation services for the human-entered reproduction workflow."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .passport import (
    RUN_STATUSES,
    STEP_STATUSES,
    EvidenceRecord,
    ProtocolStep,
    ReproductionPack,
    ReproductionRun,
    Result,
    Review,
    RunStep,
)


class WorkflowInputError(ValueError):
    """Raised when a human-entered workflow field is incomplete or invalid."""


def parse_json_object(raw: str, field_label: str) -> dict[str, Any]:
    """Parse an optional JSON object while returning actionable field errors."""

    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowInputError(f"{field_label}不是合法 JSON：{exc.msg}") from exc
    if not isinstance(value, dict):
        raise WorkflowInputError(f"{field_label}必须是 JSON 对象，例如 {{\"温度\": 25}}")
    return value


def _next_id(prefix: str, existing: set[str]) -> str:
    index = 1
    while f"{prefix}-{index:03d}" in existing:
        index += 1
    return f"{prefix}-{index:03d}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_evidence(
    pack: ReproductionPack,
    *,
    source_type: str,
    source_location: str,
    content: str,
) -> EvidenceRecord | None:
    location = source_location.strip()
    text = content.strip()
    if bool(location) != bool(text):
        raise WorkflowInputError("证据位置和证据内容必须同时填写")
    if not text:
        return None
    evidence = EvidenceRecord(
        evidence_id=_next_id("EV-USER", {item.evidence_id for item in pack.evidence}),
        source_type=source_type.strip() or "experiment_record",
        source_location=location,
        content=text,
        verification_level="user_supplied",
        status="needs_review",
        created_at=_now(),
        updated_at=_now(),
    )
    pack.evidence.append(evidence)
    return evidence


def add_protocol_step(
    pack: ReproductionPack,
    *,
    title: str,
    description: str = "",
    expected_parameters_json: str = "",
    source_location: str = "",
    evidence_content: str = "",
) -> ProtocolStep:
    """Add one researcher-supplied protocol step and a pending review task."""

    if not title.strip():
        raise WorkflowInputError("步骤标题不能为空")
    original = pack
    pack = deepcopy(pack)
    parameters = parse_json_object(expected_parameters_json, "预期参数")
    evidence = _new_evidence(
        pack,
        source_type="paper_or_protocol",
        source_location=source_location,
        content=evidence_content,
    )
    step = ProtocolStep(
        step_id=_next_id("STEP", {item.step_id for item in pack.protocol_steps}),
        title=title.strip(),
        description=description.strip(),
        sequence=max((item.sequence for item in pack.protocol_steps), default=0) + 1,
        expected_parameters=parameters,
        evidence_ids=[evidence.evidence_id] if evidence else [],
    )
    pack.protocol_steps.append(step)
    pack.reviews.append(
        Review(
            review_id=_next_id("REVIEW-STEP", {item.review_id for item in pack.reviews}),
            target_type="protocol_step",
            target_id=step.step_id,
            decision="pending",
            note="【必须人工复核】确认手工新增步骤、预期参数及来源证据。",
        )
    )
    pack.updated_at = _now()
    pack.validate()
    original.__dict__.update(pack.__dict__)
    return step


def record_reproduction_run(
    pack: ReproductionPack,
    *,
    title: str,
    status: str,
    step_entries: list[dict[str, str]],
    environment_json: str = "",
    started_at: str = "",
    ended_at: str = "",
    result: dict[str, str] | None = None,
) -> ReproductionRun:
    """Record actual work without treating user-entered facts as confirmed."""

    original = pack
    pack = deepcopy(pack)
    if not title.strip():
        raise WorkflowInputError("运行标题不能为空")
    if status not in RUN_STATUSES:
        raise WorkflowInputError(f"不支持的运行状态：{status}")
    if not pack.protocol_steps:
        raise WorkflowInputError("请先添加至少一个复现步骤")

    known_steps = {item.step_id for item in pack.protocol_steps}
    seen_steps: set[str] = set()
    run_steps: list[RunStep] = []
    for entry in step_entries:
        step_id = entry.get("step_id", "").strip()
        if step_id not in known_steps:
            raise WorkflowInputError(f"实际记录引用了不存在的步骤：{step_id}")
        if step_id in seen_steps:
            raise WorkflowInputError(f"实际记录重复引用步骤：{step_id}")
        seen_steps.add(step_id)
        step_status = entry.get("status", "not_started")
        if step_status not in STEP_STATUSES:
            raise WorkflowInputError(f"步骤 {step_id} 的状态不受支持：{step_status}")
        actual_parameters = parse_json_object(
            entry.get("actual_parameters_json", ""), f"步骤 {step_id} 的实际参数"
        )
        evidence = _new_evidence(
            pack,
            source_type=entry.get("source_type", "experiment_record"),
            source_location=entry.get("source_location", ""),
            content=entry.get("evidence_content", ""),
        )
        run_steps.append(
            RunStep(
                step_id=step_id,
                status=step_status,
                notes=entry.get("notes", "").strip(),
                actual_parameters=actual_parameters,
                evidence_ids=[evidence.evidence_id] if evidence else [],
            )
        )

    if seen_steps != known_steps:
        missing = "、".join(sorted(known_steps - seen_steps))
        raise WorkflowInputError(f"以下步骤缺少实际状态：{missing}")

    run = ReproductionRun(
        run_id=_next_id("RUN", {item.run_id for item in pack.runs}),
        title=title.strip(),
        status=status,
        steps=run_steps,
        started_at=started_at.strip(),
        ended_at=ended_at.strip(),
        environment=parse_json_object(environment_json, "运行环境"),
    )
    pack.runs.append(run)
    pack.reviews.append(
        Review(
            review_id=_next_id("REVIEW-RUN", {item.review_id for item in pack.reviews}),
            target_type="reproduction_run",
            target_id=run.run_id,
            decision="pending",
            note="【必须人工复核】确认实际过程记录、参数和证据确实来自本次复现。",
        )
    )

    if result and result.get("name", "").strip():
        result_evidence = _new_evidence(
            pack,
            source_type=result.get("source_type", "result_record"),
            source_location=result.get("source_location", ""),
            content=result.get("evidence_content", ""),
        )
        item = Result(
            result_id=_next_id("RESULT", {entry.result_id for entry in pack.results}),
            name=result["name"].strip(),
            value=result.get("value", "").strip(),
            expected_value=result.get("expected_value", "").strip() or None,
            unit=result.get("unit", "").strip(),
            evidence_ids=[result_evidence.evidence_id] if result_evidence else [],
            status="needs_review",
        )
        pack.results.append(item)
        pack.reviews.append(
            Review(
                review_id=_next_id(
                    "REVIEW-RESULT", {entry.review_id for entry in pack.reviews}
                ),
                target_type="result",
                target_id=item.result_id,
                decision="pending",
                note="【必须人工复核】确认结果数值、单位、预期值及来源证据。",
            )
        )

    pack.updated_at = _now()
    pack.validate()
    original.__dict__.update(pack.__dict__)
    return run
