"""Portable evidence-chain records for cross-disciplinary reproductions.

The passport is deliberately independent from the legacy rule report.  It can
describe computational and non-code reproductions while preserving where each
claim, action, result, and deviation came from.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1.0"
EVIDENCE_STATUSES = {
    "confirmed",
    "partial",
    "missing",
    "deviation",
    "needs_review",
    "not_applicable",
}
VERIFICATION_LEVELS = {
    "machine_extracted",
    "user_supplied",
    "machine_verified",
    "human_confirmed",
}
RUN_STATUSES = {"planned", "in_progress", "completed", "failed", "stopped"}
STEP_STATUSES = {"not_started", "in_progress", "completed", "failed", "skipped"}
REVIEW_DECISIONS = {"accepted", "rejected", "revised", "pending"}
DEVIATION_STATUSES = {"unexplained", "explained", "accepted", "needs_review"}


class PassportValidationError(ValueError):
    """Raised when a reproduction passport violates its data contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("复现档案校验失败：\n- " + "\n- ".join(errors))


@dataclass
class Study:
    study_id: str
    title: str
    source_citation: str
    discipline: str = ""
    source_url: str = ""
    summary: str = ""


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_location: str
    content: str
    verification_level: str
    status: str = "needs_review"
    source_uri: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Claim:
    claim_id: str
    text: str
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "needs_review"


@dataclass
class ProtocolStep:
    step_id: str
    title: str
    description: str = ""
    sequence: int = 0
    expected_parameters: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    artifact_id: str
    artifact_type: str
    name: str
    location: str = ""
    version: str = ""
    license: str = ""
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class RunStep:
    step_id: str
    status: str
    notes: str = ""
    actual_parameters: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ReproductionRun:
    run_id: str
    title: str
    status: str
    steps: list[RunStep] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    environment: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    result_id: str
    name: str
    value: Any
    evidence_ids: list[str] = field(default_factory=list)
    expected_value: Any = None
    unit: str = ""
    status: str = "needs_review"


@dataclass
class Deviation:
    deviation_id: str
    summary: str
    expected: str
    observed: str
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "needs_review"
    explanation: str = ""
    requires_review: bool = True


@dataclass
class Review:
    review_id: str
    target_type: str
    target_id: str
    decision: str
    reviewer: str = ""
    note: str = ""
    reviewed_at: str = ""


@dataclass
class ReproductionPack:
    pack_id: str
    title: str
    study: Study
    evidence: list[EvidenceRecord] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    protocol_steps: list[ProtocolStep] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    runs: list[ReproductionRun] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    deviations: list[Deviation] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""
    license: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReproductionPack":
        errors: list[str] = []
        if not isinstance(payload, dict):
            raise PassportValidationError(["档案根节点必须是 JSON 对象"])

        def object_list(name: str) -> list[dict[str, Any]]:
            value = payload.get(name, [])
            if not isinstance(value, list):
                errors.append(f"{name} 必须是数组")
                return []
            result = []
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    result.append(item)
                else:
                    errors.append(f"{name}[{index}] 必须是对象")
            return result

        study_data = payload.get("study")
        if not isinstance(study_data, dict):
            errors.append("study 必须是对象")
            study_data = {}

        try:
            study = Study(**study_data)
            pack = cls(
                pack_id=payload.get("pack_id", ""),
                title=payload.get("title", ""),
                study=study,
                evidence=[EvidenceRecord(**item) for item in object_list("evidence")],
                claims=[Claim(**item) for item in object_list("claims")],
                protocol_steps=[ProtocolStep(**item) for item in object_list("protocol_steps")],
                artifacts=[Artifact(**item) for item in object_list("artifacts")],
                runs=[
                    ReproductionRun(
                        **{key: value for key, value in item.items() if key != "steps"},
                        steps=[RunStep(**step) for step in item.get("steps", [])],
                    )
                    for item in object_list("runs")
                ],
                results=[Result(**item) for item in object_list("results")],
                deviations=[Deviation(**item) for item in object_list("deviations")],
                reviews=[Review(**item) for item in object_list("reviews")],
                schema_version=payload.get("schema_version", SCHEMA_VERSION),
                created_at=payload.get("created_at", ""),
                updated_at=payload.get("updated_at", ""),
                license=payload.get("license", ""),
            )
        except (TypeError, ValueError) as exc:
            errors.append(f"字段结构错误：{exc}")
            raise PassportValidationError(errors) from exc

        errors.extend(pack.validation_errors())
        if errors:
            raise PassportValidationError(errors)
        return pack

    def validation_errors(self) -> list[str]:
        errors: list[str] = []

        def require_text(value: Any, path: str) -> None:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{path} 不能为空")

        require_text(self.pack_id, "pack_id")
        require_text(self.title, "title")
        require_text(self.study.study_id, "study.study_id")
        require_text(self.study.title, "study.title")
        require_text(self.study.source_citation, "study.source_citation")
        if self.schema_version != SCHEMA_VERSION:
            errors.append(
                f"schema_version 必须为 {SCHEMA_VERSION}，当前为 {self.schema_version}"
            )

        groups: dict[str, list[Any]] = {
            "evidence": self.evidence,
            "claims": self.claims,
            "protocol_steps": self.protocol_steps,
            "artifacts": self.artifacts,
            "runs": self.runs,
            "results": self.results,
            "deviations": self.deviations,
            "reviews": self.reviews,
        }
        id_fields = {
            "evidence": "evidence_id",
            "claims": "claim_id",
            "protocol_steps": "step_id",
            "artifacts": "artifact_id",
            "runs": "run_id",
            "results": "result_id",
            "deviations": "deviation_id",
            "reviews": "review_id",
        }
        all_ids: dict[str, str] = {}
        for group_name, items in groups.items():
            id_field = id_fields[group_name]
            for index, item in enumerate(items):
                item_id = getattr(item, id_field, "")
                require_text(item_id, f"{group_name}[{index}].{id_field}")
                if item_id in all_ids:
                    errors.append(
                        f"ID {item_id} 重复出现在 {all_ids[item_id]} 和 {group_name}[{index}]"
                    )
                elif item_id:
                    all_ids[item_id] = f"{group_name}[{index}]"

        evidence_ids = {item.evidence_id for item in self.evidence}
        step_ids = {item.step_id for item in self.protocol_steps}

        for index, item in enumerate(self.evidence):
            require_text(item.source_type, f"evidence[{index}].source_type")
            require_text(item.source_location, f"evidence[{index}].source_location")
            require_text(item.content, f"evidence[{index}].content")
            if item.status not in EVIDENCE_STATUSES:
                errors.append(f"evidence[{index}].status 不受支持：{item.status}")
            if item.verification_level not in VERIFICATION_LEVELS:
                errors.append(
                    f"evidence[{index}].verification_level 不受支持：{item.verification_level}"
                )

        referenced: list[tuple[str, list[str]]] = []
        referenced.extend((f"claims[{i}]", item.evidence_ids) for i, item in enumerate(self.claims))
        referenced.extend(
            (f"protocol_steps[{i}]", item.evidence_ids)
            for i, item in enumerate(self.protocol_steps)
        )
        referenced.extend(
            (f"artifacts[{i}]", item.evidence_ids) for i, item in enumerate(self.artifacts)
        )
        referenced.extend((f"results[{i}]", item.evidence_ids) for i, item in enumerate(self.results))
        referenced.extend(
            (f"deviations[{i}]", item.evidence_ids)
            for i, item in enumerate(self.deviations)
        )
        for run_index, run in enumerate(self.runs):
            if run.status not in RUN_STATUSES:
                errors.append(f"runs[{run_index}].status 不受支持：{run.status}")
            seen_run_steps: set[str] = set()
            for step_index, step in enumerate(run.steps):
                path = f"runs[{run_index}].steps[{step_index}]"
                if step.step_id not in step_ids:
                    errors.append(f"{path}.step_id 引用了不存在的步骤：{step.step_id}")
                if step.step_id in seen_run_steps:
                    errors.append(f"{path}.step_id 在同一次运行中重复：{step.step_id}")
                seen_run_steps.add(step.step_id)
                if step.status not in STEP_STATUSES:
                    errors.append(f"{path}.status 不受支持：{step.status}")
                referenced.append((path, step.evidence_ids))

        for path, references in referenced:
            for evidence_id in references:
                if evidence_id not in evidence_ids:
                    errors.append(f"{path} 引用了不存在的证据：{evidence_id}")

        for index, claim in enumerate(self.claims):
            if claim.status not in EVIDENCE_STATUSES:
                errors.append(f"claims[{index}].status 不受支持：{claim.status}")
        for index, result in enumerate(self.results):
            if result.status not in EVIDENCE_STATUSES:
                errors.append(f"results[{index}].status 不受支持：{result.status}")
        for index, deviation in enumerate(self.deviations):
            if deviation.status not in DEVIATION_STATUSES:
                errors.append(f"deviations[{index}].status 不受支持：{deviation.status}")

        reviewable = set(all_ids) | {self.study.study_id, self.pack_id}
        for index, review in enumerate(self.reviews):
            if review.decision not in REVIEW_DECISIONS:
                errors.append(f"reviews[{index}].decision 不受支持：{review.decision}")
            if review.target_id not in reviewable:
                errors.append(
                    f"reviews[{index}].target_id 引用了不存在的对象：{review.target_id}"
                )
            if review.decision != "pending" and not review.reviewer.strip():
                errors.append(f"reviews[{index}].reviewer 在非 pending 状态时不能为空")

        return errors

    def validate(self) -> None:
        errors = self.validation_errors()
        if errors:
            raise PassportValidationError(errors)


def passport_to_json(pack: ReproductionPack) -> str:
    pack.validate()
    return json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n"


def passport_to_markdown(pack: ReproductionPack) -> str:
    pack.validate()
    lines = [
        f"# 复现档案：{pack.title}",
        "",
        f"- 档案编号：`{pack.pack_id}`",
        f"- Schema 版本：`{pack.schema_version}`",
        f"- 研究：{pack.study.title}",
        f"- 来源：{pack.study.source_citation}",
        f"- 学科：{pack.study.discipline or '未填写'}",
        f"- 档案许可证：{pack.license or '未填写'}",
        "",
        "## 证据概览",
        "",
        f"- 研究主张：{len(pack.claims)}",
        f"- 复现步骤：{len(pack.protocol_steps)}",
        f"- 证据记录：{len(pack.evidence)}",
        f"- 实际运行：{len(pack.runs)}",
        f"- 结果：{len(pack.results)}",
        f"- 偏差：{len(pack.deviations)}",
        f"- 人工复核：{len(pack.reviews)}",
        "",
        "## 复现步骤",
        "",
    ]
    for step in sorted(pack.protocol_steps, key=lambda item: (item.sequence, item.step_id)):
        lines.extend(
            [
                f"### {step.step_id} {step.title}",
                "",
                step.description or "未填写步骤说明。",
                "",
                "- 证据：" + ("、".join(step.evidence_ids) if step.evidence_ids else "待补充"),
                "",
            ]
        )

    lines.extend(["## 实际复现过程", ""])
    if pack.runs:
        step_title = {item.step_id: item.title for item in pack.protocol_steps}
        for run in pack.runs:
            lines.extend(
                [
                    f"### {run.run_id} {run.title}",
                    "",
                    f"- 状态：`{run.status}`",
                    f"- 开始：{run.started_at or '未填写'}",
                    f"- 结束：{run.ended_at or '未填写'}",
                    f"- 环境：`{json.dumps(run.environment, ensure_ascii=False)}`",
                    "",
                ]
            )
            for step in run.steps:
                lines.extend(
                    [
                        f"#### {step.step_id} {step_title.get(step.step_id, '')}",
                        "",
                        f"- 实际状态：`{step.status}`",
                        f"- 实际参数：`{json.dumps(step.actual_parameters, ensure_ascii=False)}`",
                        f"- 过程证据：{'、'.join(step.evidence_ids) if step.evidence_ids else '待补充'}",
                        f"- 备注：{step.notes or '未填写'}",
                        "",
                    ]
                )
    else:
        lines.extend(["当前没有实际复现过程记录。", ""])

    lines.extend(["## 实际结果", ""])
    if pack.results:
        for item in pack.results:
            lines.extend(
                [
                    f"### {item.result_id} {item.name}",
                    "",
                    f"- 实际值：{item.value}{(' ' + item.unit) if item.unit else ''}",
                    f"- 预期值：{item.expected_value if item.expected_value is not None else '未填写'}",
                    f"- 状态：`{item.status}`",
                    f"- 证据：{'、'.join(item.evidence_ids) if item.evidence_ids else '待补充'}",
                    "",
                ]
            )
    else:
        lines.extend(["当前没有结果记录。", ""])

    lines.extend(["## 偏差与人工复核", ""])
    if pack.deviations:
        for item in pack.deviations:
            lines.extend(
                [
                    f"### {item.deviation_id} {item.summary}",
                    "",
                    f"- 预期：{item.expected}",
                    f"- 实际：{item.observed}",
                    f"- 状态：`{item.status}`",
                    f"- 解释：{item.explanation or '待人工补充'}",
                    f"- 需要人工复核：{'是' if item.requires_review else '否'}",
                    "",
                ]
            )
    else:
        lines.extend(["当前没有记录偏差。", ""])

    pending = [item for item in pack.reviews if item.decision == "pending"]
    lines.extend(
        [
            "## 人工复核状态",
            "",
            f"- 待处理：{len(pending)}",
            f"- 已处理：{len(pack.reviews) - len(pending)}",
            "",
            "> AI 提取和对齐结果不等于科研事实；最终结论以人工复核记录为准。",
            "",
        ]
    )
    return "\n".join(lines)


def load_passport(path: Path) -> ReproductionPack:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PassportValidationError([f"JSON 格式错误：{exc}"]) from exc
    return ReproductionPack.from_dict(payload)


def write_passport(pack: ReproductionPack, output_prefix: Path) -> list[Path]:
    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    markdown_path = output_prefix.with_suffix(".md")
    json_path.write_text(passport_to_json(pack), encoding="utf-8")
    markdown_path.write_text(passport_to_markdown(pack), encoding="utf-8")
    return [json_path, markdown_path]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验并导出开放科研复现档案。")
    parser.add_argument("--input", required=True, help="复现档案 JSON 路径")
    parser.add_argument("--output", help="输出前缀；不填写时只校验")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pack = load_passport(Path(args.input))
        paths = write_passport(pack, Path(args.output)) if args.output else []
    except (OSError, PassportValidationError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"档案校验通过：{pack.pack_id}")
    for path in paths:
        print(f"已生成：{path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
