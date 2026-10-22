"""Review pull-request diffs for research reproducibility risks."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .model_assist import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NAME,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL_NAME,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    JsonModelClient,
    ModelAssistError,
    ModelConfig,
    build_model_client,
    model_setup_hint,
)
from .paper_extract import PaperDocument, PaperExtractionError, load_paper


PARAMETER_ALIASES = {
    "learning_rate": {"learning_rate", "learning-rate", "lr"},
    "batch_size": {"batch_size", "batch-size"},
    "seed": {"seed", "random_seed", "random-seed", "random_state"},
    "epochs": {"epochs", "epoch", "num_epochs", "max_epochs"},
    "weight_decay": {"weight_decay", "weight-decay"},
    "dropout": {"dropout", "dropout_rate", "dropout-rate"},
    "temperature": {"temperature", "温度"},
    "duration": {"duration", "incubation_time", "时长"},
    "concentration": {"concentration", "浓度"},
    "threshold": {"threshold", "阈值"},
    "image_size": {"image_size", "image-size", "input_size", "resolution"},
    "dataset": {"dataset", "dataset_name", "data_name"},
    "model": {"model", "model_name", "architecture", "arch"},
    "optimizer": {"optimizer", "optim"},
    "metric": {"metric", "metrics", "evaluation_metric"},
    "loss": {"loss", "loss_function", "criterion"},
    "reference_genome": {"reference_genome", "reference-genome", "genome_build"},
}

PARAMETER_LABELS = {
    "learning_rate": "学习率",
    "batch_size": "批大小",
    "seed": "随机种子",
    "epochs": "训练轮数",
    "weight_decay": "权重衰减",
    "dropout": "Dropout",
    "temperature": "温度",
    "duration": "实验时长",
    "concentration": "浓度",
    "threshold": "阈值",
    "image_size": "输入尺寸",
    "dataset": "数据集",
    "model": "模型",
    "optimizer": "优化器",
    "metric": "评价指标",
    "loss": "损失函数",
    "reference_genome": "参考基因组",
}

CONSTRAINT_TERMS = {
    "learning_rate": ("learning rate", "learning_rate", "学习率"),
    "batch_size": ("batch size", "batch_size", "批大小"),
    "seed": ("random seed", "random_seed", "随机种子", "seed"),
    "epochs": ("epochs", "epoch", "训练轮数"),
    "weight_decay": ("weight decay", "weight_decay", "权重衰减"),
    "dropout": ("dropout",),
    "temperature": ("temperature", "温度"),
    "duration": ("duration", "incubation time", "时长", "时间"),
    "concentration": ("concentration", "浓度"),
    "threshold": ("threshold", "阈值"),
    "image_size": ("image size", "input size", "resolution", "输入尺寸"),
    "dataset": ("dataset", "data set", "数据集"),
    "model": ("model", "architecture", "模型", "架构"),
    "optimizer": ("optimizer", "optimiser", "优化器"),
    "metric": ("metric", "accuracy", "f1", "评价指标"),
    "loss": ("loss", "criterion", "损失函数"),
    "reference_genome": ("reference genome", "genome build", "参考基因组"),
}

DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    "environment.yml",
    "environment.yaml",
    "conda-lock.yml",
    "package.json",
    "package-lock.json",
}

PIPELINE_TERMS = (
    "preprocess",
    "preprocessing",
    "normalize",
    "normalization",
    "augmentation",
    "dataloader",
    "drop_last",
    "from_numpy",
    "floattensor",
    "longtensor",
    "tokenizer",
    "train_test_split",
    "validation_split",
    "metric",
    "loss_function",
    "criterion",
    "sigmoid",
    "softmax",
    "cross_entropy",
    "dice_coeff",
    "数据预处理",
    "归一化",
    "数据增强",
    "数据划分",
    "评价指标",
)

ASSIGNMENT_RE = re.compile(
    r"^\s*[+\- ]?\s*[\"']?([A-Za-z_\u4e00-\u9fff][\w.\-\u4e00-\u9fff]*)[\"']?"
    r"\s*(?::|=)\s*(.+?)\s*(?:[,;]\s*)?$"
)
CLI_ARGUMENT_RE = re.compile(r"--([A-Za-z][\w-]*)(?:\s+|=)([^\s`]+)")
HUNK_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
LOADER_COUNT_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*=\s*len\(\s*([A-Za-z_]\w*)\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DiffLine:
    kind: str
    text: str
    old_line: int | None
    new_line: int | None
    hunk: int


@dataclass
class ChangedFile:
    old_path: str
    new_path: str
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path if self.new_path != "/dev/null" else self.old_path


@dataclass(frozen=True)
class ConstraintEvidence:
    location: str
    quote: str


@dataclass
class PRFinding:
    finding_id: str
    category: str
    severity: str
    title: str
    message: str
    suggestion: str
    file: str
    line: int | None
    evidence: list[dict[str, str]] = field(default_factory=list)
    needs_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PRReviewReport:
    findings: list[PRFinding]
    changed_files: list[str]
    generated_at: str
    constraints_path: str = ""
    model_assistance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        counts = {
            level: sum(item.severity == level for item in self.findings)
            for level in ("high", "medium", "low")
        }
        return {
            "schema_version": "1.0",
            "generated_at": self.generated_at,
            "constraints_path": self.constraints_path,
            "changed_files": self.changed_files,
            "summary": {
                "changed_file_count": len(self.changed_files),
                "finding_count": len(self.findings),
                "high_count": counts["high"],
                "medium_count": counts["medium"],
                "low_count": counts["low"],
            },
            "findings": [item.to_dict() for item in self.findings],
            **(
                {"model_assistance": self.model_assistance}
                if self.model_assistance is not None
                else {}
            ),
        }


def _strip_diff_path(value: str) -> str:
    value = value.strip().split("\t", 1)[0]
    if value.startswith('"'):
        try:
            value = shlex.split(value)[0]
        except (ValueError, IndexError):
            value = value.strip('"')
    if value.startswith(("a/", "b/")):
        return value[2:]
    return value


def parse_unified_diff(text: str) -> list[ChangedFile]:
    """Parse the file and line information needed by the PR checks."""

    files: list[ChangedFile] = []
    current: ChangedFile | None = None
    old_line = 0
    new_line = 0
    hunk = 0

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            try:
                parts = shlex.split(raw)
            except ValueError:
                parts = []
            if len(parts) == 4 and parts[0:2] == ["diff", "--git"]:
                current = ChangedFile(_strip_diff_path(parts[2]), _strip_diff_path(parts[3]))
                files.append(current)
            else:
                current = None
            continue
        if current is None:
            continue
        if raw.startswith("--- "):
            current.old_path = _strip_diff_path(raw[4:])
            continue
        if raw.startswith("+++ "):
            current.new_path = _strip_diff_path(raw[4:])
            continue
        match = HUNK_RE.match(raw)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(3))
            hunk += 1
            continue
        if not hunk or raw.startswith("\\ No newline"):
            continue
        if raw.startswith("+"):
            current.lines.append(DiffLine("added", raw[1:], None, new_line, hunk))
            new_line += 1
        elif raw.startswith("-"):
            current.lines.append(DiffLine("removed", raw[1:], old_line, None, hunk))
            old_line += 1
        else:
            content = raw[1:] if raw.startswith(" ") else raw
            current.lines.append(DiffLine("context", content, old_line, new_line, hunk))
            old_line += 1
            new_line += 1

    return files


def _canonical_parameter(key: str) -> str | None:
    raw = key.strip().lower().replace("-", "_")
    candidates = {raw.replace(".", "_"), raw.rsplit(".", 1)[-1]}
    for canonical, aliases in PARAMETER_ALIASES.items():
        if candidates & {item.replace("-", "_") for item in aliases}:
            return canonical
    return None


def _clean_value(value: str) -> str:
    value = re.split(r"\s+#|\s+//", value.strip(), maxsplit=1)[0].strip()
    return value.strip("\"'`, ")


def parse_parameter(line: DiffLine) -> tuple[str, str] | None:
    match = ASSIGNMENT_RE.match(line.text)
    if match:
        parameter = _canonical_parameter(match.group(1))
        if parameter:
            return parameter, _clean_value(match.group(2))
    match = CLI_ARGUMENT_RE.search(line.text)
    if match:
        parameter = _canonical_parameter(match.group(1))
        if parameter:
            return parameter, _clean_value(match.group(2))
    return None


def _find_constraint_evidence(
    document: PaperDocument | None,
    parameter: str,
    old_value: str,
) -> list[ConstraintEvidence]:
    if document is None:
        return []
    terms = tuple(item.lower() for item in CONSTRAINT_TERMS.get(parameter, (parameter,)))
    old_lower = old_value.lower()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", old_lower):
        value_pattern = re.compile(
            rf"(?<![\d.]){re.escape(old_lower)}(?![\d.])"
        )
        has_value = lambda line: bool(value_pattern.search(line))
    else:
        has_value = lambda line: old_lower in line
    evidence: list[ConstraintEvidence] = []
    for page, line_number, line in document.iter_lines():
        lowered = line.lower()
        if any(term in lowered for term in terms) and has_value(lowered):
            evidence.append(
                ConstraintEvidence(
                    location=f"page {page.page}, line {line_number}",
                    quote=line.strip()[:240],
                )
            )
            if len(evidence) == 3:
                break
    return evidence


def _changed_parameters(changed: ChangedFile) -> list[tuple[str, str, str, DiffLine]]:
    removed: dict[tuple[int, str], list[tuple[str, DiffLine]]] = {}
    added: dict[tuple[int, str], list[tuple[str, DiffLine]]] = {}
    for line in changed.lines:
        parsed = parse_parameter(line)
        if not parsed:
            continue
        parameter, value = parsed
        target = removed if line.kind == "removed" else added if line.kind == "added" else None
        if target is not None:
            target.setdefault((line.hunk, parameter), []).append((value, line))

    changes: list[tuple[str, str, str, DiffLine]] = []
    for key in sorted(set(removed) & set(added)):
        for (old_value, _), (new_value, new_line) in zip(removed[key], added[key]):
            if old_value != new_value:
                changes.append((key[1], old_value, new_value, new_line))
    return changes


def _evaluation_denominator_changes(changed: ChangedFile) -> list[tuple[DiffLine, DiffLine]]:
    """Find loader-batch counts that are used as an evaluation denominator.

    This deliberately requires both sides of the relationship: an added
    ``count = len(loader)``-style assignment and a division by that count in
    the same changed file. Merely calling ``len(loader)`` is not enough to
    produce a warning.
    """

    results: list[tuple[DiffLine, DiffLine]] = []
    evaluation_context = any(
        term in changed.path.lower()
        for term in ("eval", "evaluat", "metric", "valid", "test")
    ) or any(
        any(term in line.text.lower() for term in ("metric", "dice", "accuracy", "loss", "score"))
        for line in changed.lines
    )
    if not evaluation_context:
        return results

    for assignment in changed.lines:
        if assignment.kind != "added":
            continue
        match = LOADER_COUNT_ASSIGNMENT_RE.match(assignment.text)
        if not match or "loader" not in match.group(2).lower():
            continue
        variable = match.group(1)
        division_pattern = re.compile(rf"/\s*{re.escape(variable)}\b")
        denominator_use = next(
            (
                line
                for line in changed.lines
                if line.kind in {"added", "context"}
                and division_pattern.search(line.text)
            ),
            None,
        )
        if denominator_use is not None:
            results.append((assignment, denominator_use))
    return results


def run_pr_rules(
    files: list[ChangedFile],
    constraints: PaperDocument | None = None,
) -> list[PRFinding]:
    findings: list[PRFinding] = []
    counter = 0

    def add(**kwargs: Any) -> None:
        nonlocal counter
        counter += 1
        findings.append(PRFinding(finding_id=f"PR{counter:03d}", **kwargs))

    for changed in files:
        parameter_changes = _changed_parameters(changed)
        changed_parameters = {item[0] for item in parameter_changes}
        for parameter, old_value, new_value, line in parameter_changes:
            baseline = _find_constraint_evidence(constraints, parameter, old_value)
            label = PARAMETER_LABELS[parameter]
            if baseline:
                title = f"{label}变更可能与研究约束不一致"
                message = (
                    f"本次 PR 将{label}从 `{old_value}` 修改为 `{new_value}`，"
                    "而输入的论文或协议中仍可定位到旧值。"
                )
                severity = "high"
            else:
                title = f"{label}发生变化，需确认复现材料是否同步"
                message = (
                    f"本次 PR 将{label}从 `{old_value}` 修改为 `{new_value}`。"
                    "当前未建立可自动确认的新旧研究约束，需要人工核对。"
                )
                severity = "high" if parameter == "seed" else "medium"
            evidence = [
                {
                    "source": "diff",
                    "location": f"{changed.path}:{line.new_line or 1}",
                    "quote": line.text[:240],
                }
            ]
            evidence.extend(
                {"source": "constraint", "location": item.location, "quote": item.quote}
                for item in baseline
            )
            add(
                category="parameter_change",
                severity=severity,
                title=title,
                message=message,
                suggestion="同步更新复现档案和结果证据，或将该变化记录为有理由的复现偏差。",
                file=changed.path,
                line=line.new_line,
                evidence=evidence,
            )

        removed_seed = [
            line
            for line in changed.lines
            if line.kind == "removed"
            and (parse_parameter(line) or (None,))[0] == "seed"
        ]
        added_seed = [
            line
            for line in changed.lines
            if line.kind == "added"
            and (parse_parameter(line) or (None,))[0] == "seed"
        ]
        if removed_seed and not added_seed and "seed" not in changed_parameters:
            line = removed_seed[0]
            anchor = next(
                (
                    candidate.new_line
                    for candidate in changed.lines
                    if candidate.hunk == line.hunk and candidate.new_line is not None
                ),
                None,
            )
            add(
                category="seed_removed",
                severity="high",
                title="随机种子设置被删除",
                message="本次 PR 删除了可定位的随机种子设置，可能导致结果无法稳定复现。",
                suggestion="恢复并记录随机种子；若有意改用非确定性执行，请在复现档案中说明。",
                file=changed.path,
                line=anchor,
                evidence=[
                    {
                        "source": "diff",
                        "location": f"{changed.path}:{line.old_line or 1} (removed)",
                        "quote": line.text[:240],
                    }
                ],
            )

        name = PurePosixPath(changed.path).name.lower()
        if name in DEPENDENCY_FILES:
            changed_lines = [line for line in changed.lines if line.kind in {"added", "removed"}]
            if changed_lines:
                anchor = next((line for line in changed_lines if line.kind == "added"), changed_lines[0])
                add(
                    category="dependency_change",
                    severity="medium",
                    title="依赖或运行环境发生变化",
                    message="本次 PR 修改了依赖或环境声明，已有实验结果可能不再对应当前环境。",
                    suggestion="记录新环境版本，并补充最小运行日志或说明结果是否需要重新生成。",
                    file=changed.path,
                    line=anchor.new_line or anchor.old_line,
                    evidence=[
                        {
                            "source": "diff",
                            "location": f"{changed.path}:{anchor.new_line or anchor.old_line or 1}",
                            "quote": anchor.text[:240],
                        }
                    ],
                )

        for assignment, denominator_use in _evaluation_denominator_changes(changed):
            anchor = assignment.new_line or denominator_use.new_line or denominator_use.old_line
            add(
                category="evaluation_denominator_change",
                severity="high",
                title="评价结果的归一化分母改为数据加载批次数",
                message=(
                    "本次 PR 新增了按 `len(loader)` 计算的计数，并将该计数用于评价结果除法。"
                    "当批大小、尾批处理或样本数变化时，这可能改变指标口径。"
                ),
                suggestion=(
                    "确认指标应按样本数还是批次数归一化；记录尾批处理方式，并补充变更前后的数值对比测试。"
                ),
                file=changed.path,
                line=anchor,
                evidence=[
                    {
                        "source": "diff",
                        "location": f"{changed.path}:{assignment.new_line or 1}",
                        "quote": assignment.text[:240],
                    },
                    {
                        "source": "diff",
                        "location": f"{changed.path}:{denominator_use.new_line or denominator_use.old_line or 1}",
                        "quote": denominator_use.text[:240],
                    },
                ],
            )

        pipeline_lines = [
            line
            for line in changed.lines
            if line.kind in {"added", "removed"}
            and any(term in line.text.lower() for term in PIPELINE_TERMS)
            and (parse_parameter(line) or (None,))[0] not in changed_parameters
        ]
        if pipeline_lines:
            anchor = next((line for line in pipeline_lines if line.kind == "added"), pipeline_lines[0])
            add(
                category="pipeline_change",
                severity="high",
                title="数据处理或评价流程发生变化",
                message="本次 PR 修改了数据处理、数据划分、损失函数或评价指标相关内容。",
                suggestion="确认论文/协议、配置、测试和结果说明是否同步，并补充变化前后的结果对比。",
                file=changed.path,
                line=anchor.new_line or anchor.old_line,
                evidence=[
                    {
                        "source": "diff",
                        "location": (
                            f"{changed.path}:{item.new_line or item.old_line or 1}"
                            + (" (removed)" if item.kind == "removed" else "")
                        ),
                        "quote": item.text[:240],
                    }
                    for item in sorted(
                        pipeline_lines,
                        key=lambda candidate: candidate.kind != "added",
                    )[:3]
                ],
            )

    return findings


def _model_sources(
    files: list[ChangedFile],
    constraints: PaperDocument | None,
    *,
    limit: int = 240,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for changed in files:
        for line in changed.lines:
            if line.kind not in {"added", "removed"}:
                continue
            prefix = "+" if line.kind == "added" else "-"
            number = line.new_line if line.kind == "added" else line.old_line
            sources.append(
                {
                    "ref": f"D{len(sources) + 1:03d}",
                    "location": f"{changed.path}:{number or 1}",
                    "text": f"{prefix}{line.text[:280]}",
                }
            )
            if len(sources) >= limit:
                return sources
    if constraints is not None:
        for page, line_number, text in constraints.iter_lines():
            if not text.strip():
                continue
            sources.append(
                {
                    "ref": f"P{sum(item['ref'].startswith('P') for item in sources) + 1:03d}",
                    "location": f"page {page.page}, line {line_number}",
                    "text": text.strip()[:280],
                }
            )
            if len(sources) >= limit:
                break
    return sources


def _pr_model_prompt(sources: list[dict[str, str]]) -> str:
    context = "\n".join(
        f"[{item['ref']}] {item['location']} | {item['text']}" for item in sources
    )
    return f"""你是开放科研项目的 PR 复现风险审查助手。D 编号是 PR diff，P 编号是论文或协议来源。

只审查可能影响科研复现的变化，例如实验参数、随机性、数据处理、评价指标、依赖环境、协议参数和结果证据。不要报告普通代码风格问题。只依据提供的来源，不得猜测。

只输出以下 JSON 对象：
{{
  "risks": [
    {{
      "category": "风险类别",
      "severity": "high 或 medium 或 low",
      "title": "简短标题",
      "explanation": "为什么需要人工确认",
      "suggestion": "建议",
      "source_refs": ["D001", "P001"]
    }}
  ],
  "review_notes": ["其他需要人工确认的事项"]
}}

每条风险必须至少引用一个 D 编号。source_refs 只能使用下列编号：
{context}
"""


def run_pr_model_assistance(
    files: list[ChangedFile],
    constraints: PaperDocument | None,
    config: ModelConfig,
    *,
    client: JsonModelClient | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "provider": config.provider,
        "model": config.model_name,
        "base_url": config.base_url,
        "status": STATUS_OK,
        "risks": [],
        "review_notes": [],
        "dropped_source_refs": [],
        "message": "模型建议默认待人工复核，不改变确定性规则结论。",
    }
    sources = _model_sources(files, constraints)
    if not sources:
        base["status"] = STATUS_INVALID
        base["message"] = "没有可供模型审查的变更来源。"
        return base
    try:
        model = client or build_model_client(config)
        payload = model.generate_json(_pr_model_prompt(sources))
    except ModelAssistError as exc:
        base["status"] = STATUS_UNAVAILABLE
        base["message"] = f"{exc}。{model_setup_hint(config)}。"
        return base

    allowed = {item["ref"]: item for item in sources}
    dropped: list[str] = []
    risks: list[dict[str, Any]] = []
    raw_risks = payload.get("risks")
    if not isinstance(raw_risks, list):
        base["status"] = STATUS_INVALID
        base["message"] = "模型输出缺少 risks 数组。"
        return base
    for raw in raw_risks:
        if not isinstance(raw, dict):
            continue
        raw_refs = raw.get("source_refs")
        refs = []
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                if ref in allowed and ref not in refs:
                    refs.append(ref)
                elif isinstance(ref, str) and ref not in dropped:
                    dropped.append(ref)
        if not refs or not any(ref.startswith("D") for ref in refs):
            continue
        severity = raw.get("severity")
        if severity not in {"high", "medium", "low"}:
            severity = "medium"
        title = raw.get("title")
        explanation = raw.get("explanation")
        if not isinstance(title, str) or not title.strip():
            continue
        risks.append(
            {
                "category": str(raw.get("category", "model_review"))[:80],
                "severity": severity,
                "title": title.strip()[:160],
                "explanation": explanation.strip()[:800] if isinstance(explanation, str) else "",
                "suggestion": str(raw.get("suggestion", ""))[:500],
                "source_refs": refs,
                "sources": [allowed[ref] for ref in refs],
                "needs_human_review": True,
            }
        )
    notes = payload.get("review_notes")
    base["risks"] = risks
    base["review_notes"] = [item[:500] for item in notes if isinstance(item, str)] if isinstance(notes, list) else []
    base["dropped_source_refs"] = dropped
    return base


def review_pull_request(
    diff_text: str,
    *,
    constraints_path: Path | None = None,
    model_config: ModelConfig | None = None,
    model_client: JsonModelClient | None = None,
) -> PRReviewReport:
    files = parse_unified_diff(diff_text)
    constraints = load_paper(constraints_path) if constraints_path else None
    findings = run_pr_rules(files, constraints)
    assistance = None
    if model_config is not None and model_config.enabled:
        assistance = run_pr_model_assistance(
            files, constraints, model_config, client=model_client
        )
    return PRReviewReport(
        findings=findings,
        changed_files=[item.path for item in files],
        generated_at=datetime.now(timezone.utc).isoformat(),
        constraints_path=str(Path(constraints_path).resolve()) if constraints_path else "",
        model_assistance=assistance,
    )


def report_to_markdown(report: PRReviewReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    lines = [
        "# ReproGuard PR 复现风险报告",
        "",
        f"- 变更文件：{summary['changed_file_count']}",
        f"- 规则风险：{summary['finding_count']}",
        f"- 高 / 中 / 低：{summary['high_count']} / {summary['medium_count']} / {summary['low_count']}",
        "- 结论边界：所有风险均需项目维护者确认，不代表自动判定研究无效。",
        "",
        "## 规则检查",
        "",
    ]
    if not report.findings:
        lines.append("本次规则检查未发现可定位的复现风险。")
    for item in report.findings:
        location = f"{item.file}:{item.line}" if item.line else item.file
        lines.extend(
            [
                f"### {item.finding_id} [{item.severity.upper()}] {item.title}",
                "",
                f"- 位置：`{location}`",
                f"- 类型：`{item.category}`",
                f"- 判断：{item.message}",
                f"- 建议：{item.suggestion}",
                "- 状态：等待人工确认",
            ]
        )
        if item.evidence:
            lines.append("- 证据：")
            for evidence in item.evidence:
                lines.append(
                    f"  - `{evidence['location']}`：{evidence['quote']}"
                )
        lines.append("")

    if report.model_assistance is not None:
        model = report.model_assistance
        lines.extend(["## 模型辅助建议", ""])
        lines.append(
            f"状态：`{model.get('status', '')}`；模型：`{model.get('model', '')}`。"
        )
        if model.get("message"):
            lines.append(str(model["message"]))
        lines.append("")
        for index, risk in enumerate(model.get("risks", []), start=1):
            lines.extend(
                [
                    f"### AI-{index:02d} [{risk['severity'].upper()}] {risk['title']}",
                    "",
                    risk.get("explanation", ""),
                    "",
                    f"建议：{risk.get('suggestion', '')}",
                    "",
                    "来源：" + ", ".join(risk.get("source_refs", [])),
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _github_escape(value: str, *, property_value: bool = False) -> str:
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def github_annotations(report: PRReviewReport) -> list[str]:
    annotations = []
    for item in report.findings:
        properties = [f"file={_github_escape(item.file, property_value=True)}"]
        if item.line:
            properties.append(f"line={item.line}")
        properties.append(
            f"title={_github_escape(f'ReproGuard {item.finding_id}', property_value=True)}"
        )
        message = _github_escape(f"{item.title}：{item.message} 建议：{item.suggestion}")
        annotations.append(f"::warning {','.join(properties)}::{message}")
    return annotations


def write_reports(report: PRReviewReport, output: Path, output_format: str) -> list[Path]:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if output_format in {"json", "both"}:
        path = output.with_suffix(".json")
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
    if output_format in {"markdown", "both"}:
        path = output.with_suffix(".md")
        path.write_text(report_to_markdown(report), encoding="utf-8")
        paths.append(path)
    return paths


def _append_github_file(environment_name: str, content: str) -> None:
    target = os.environ.get(environment_name)
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as stream:
        stream.write(content)
        if not content.endswith("\n"):
            stream.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="审查 GitHub PR 中的科研复现风险。")
    parser.add_argument("--diff", required=True, help="unified diff 文件；使用 - 从标准输入读取")
    parser.add_argument("--constraints", help="可选论文或协议，支持 .txt、.md、.pdf")
    parser.add_argument("--output", required=True, help="报告输出前缀")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument("--github-annotations", action="store_true", help="向标准输出写 GitHub workflow 注释")
    parser.add_argument("--fail-on", choices=("never", "high", "any"), default="never")
    parser.add_argument("--model-mode", choices=("rules", "ollama", "deepseek"), default="rules")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--ollama-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        diff_text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
        cloud_mode = args.model_mode == "deepseek"
        model_config = ModelConfig(
            enabled=args.model_mode != "rules",
            provider=PROVIDER_OPENAI_COMPATIBLE if cloud_mode else PROVIDER_OLLAMA,
            base_url=args.api_base_url if cloud_mode else args.ollama_url,
            model_name=args.model_name or (DEFAULT_OPENAI_MODEL_NAME if cloud_mode else DEFAULT_MODEL_NAME),
            api_key_env=args.api_key_env,
        )
        report = review_pull_request(
            diff_text,
            constraints_path=Path(args.constraints) if args.constraints else None,
            model_config=model_config,
        )
        paths = write_reports(report, Path(args.output), args.format)
    except (OSError, UnicodeError, PaperExtractionError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.github_annotations:
        for annotation in github_annotations(report):
            print(annotation)
    markdown = report_to_markdown(report)
    _append_github_file("GITHUB_STEP_SUMMARY", markdown)
    summary = report.to_dict()["summary"]
    _append_github_file(
        "GITHUB_OUTPUT",
        "\n".join(
            [
                f"finding-count={summary['finding_count']}",
                f"high-count={summary['high_count']}",
                f"report-json={Path(args.output).with_suffix('.json') if args.format in {'json', 'both'} else ''}",
                f"report-markdown={Path(args.output).with_suffix('.md') if args.format in {'markdown', 'both'} else ''}",
            ]
        ),
    )
    for path in paths:
        print(f"已生成：{path.resolve()}")
    print(
        f"PR 审查完成：{summary['changed_file_count']} 个文件，"
        f"{summary['finding_count']} 项规则风险，其中 {summary['high_count']} 项高风险。"
    )
    if args.fail_on == "any" and report.findings:
        return 1
    if args.fail_on == "high" and any(item.severity == "high" for item in report.findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
