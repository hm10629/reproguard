"""Deterministic alignment checks between expected and recorded work."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .passport import Deviation, ReproductionPack, Review


class AlignmentError(ValueError):
    """Raised when a run cannot be aligned against the current passport."""


def _display(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalise(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().casefold()
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value).casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def detect_run_deviations(pack: ReproductionPack, run_id: str) -> list[Deviation]:
    """Rebuild deterministic deviations for one run and queue human review."""

    original = pack
    pack = deepcopy(pack)
    run = next((item for item in pack.runs if item.run_id == run_id), None)
    if run is None:
        raise AlignmentError(f"找不到实际运行：{run_id}")

    prefix = f"DEV-AUTO-{run.run_id}-"
    removed_ids = {
        item.deviation_id for item in pack.deviations if item.deviation_id.startswith(prefix)
    }
    pack.deviations = [
        item for item in pack.deviations if item.deviation_id not in removed_ids
    ]
    pack.reviews = [
        item
        for item in pack.reviews
        if not (item.target_type == "deviation" and item.target_id in removed_ids)
    ]

    expected_by_id = {item.step_id: item for item in pack.protocol_steps}
    issues: list[tuple[str, str, str, list[str]]] = []
    for actual in run.steps:
        expected = expected_by_id[actual.step_id]
        evidence_ids = list(dict.fromkeys(expected.evidence_ids + actual.evidence_ids))

        if run.status == "completed" and actual.status not in {"completed", "skipped"}:
            issues.append(
                (
                    f"{expected.title}在已完成运行中未完成",
                    "completed 或有明确跳过说明",
                    actual.status,
                    evidence_ids,
                )
            )
        if actual.status in {"failed", "skipped"}:
            issues.append(
                (
                    f"{expected.title}的实际状态需要解释",
                    "completed",
                    actual.status,
                    evidence_ids,
                )
            )
        if actual.status == "completed" and not actual.evidence_ids:
            issues.append(
                (
                    f"{expected.title}缺少实际过程证据",
                    "至少一条可回查的日志、实验记录或结果文件",
                    "未关联实际过程证据",
                    evidence_ids,
                )
            )

        for name, expected_value in expected.expected_parameters.items():
            if name not in actual.actual_parameters:
                issues.append(
                    (
                        f"{expected.title}缺少实际参数：{name}",
                        _display(expected_value),
                        "未记录",
                        evidence_ids,
                    )
                )
                continue
            observed_value = actual.actual_parameters[name]
            if _normalise(expected_value) != _normalise(observed_value):
                issues.append(
                    (
                        f"{expected.title}参数不一致：{name}",
                        _display(expected_value),
                        _display(observed_value),
                        evidence_ids,
                    )
                )

    generated: list[Deviation] = []
    for index, (summary, expected, observed, evidence_ids) in enumerate(issues, start=1):
        deviation = Deviation(
            deviation_id=f"{prefix}{index:03d}",
            summary=summary,
            expected=expected,
            observed=observed,
            evidence_ids=evidence_ids,
            status="needs_review",
            explanation="由确定性对齐规则生成，尚未确认原因或影响。",
            requires_review=True,
        )
        pack.deviations.append(deviation)
        generated.append(deviation)
        pack.reviews.append(
            Review(
                review_id=f"REVIEW-{deviation.deviation_id}",
                target_type="deviation",
                target_id=deviation.deviation_id,
                decision="pending",
                note="【必须人工复核】确认预期、实际记录和差异原因；规则结果不得直接作为科研结论。",
            )
        )

    pack.updated_at = datetime.now(timezone.utc).isoformat()
    pack.validate()
    original.__dict__.update(pack.__dict__)
    return generated
