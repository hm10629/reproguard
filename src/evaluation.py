"""Evaluation harness for the reproducibility checker.

Compares the tool's rule verdicts against human annotations, aligning both
sides by ``rule_id``. Reports per-rule agreement plus precision / recall for
gap detection.

Scope note: this module builds the *skeleton* only. It never downloads papers
or repositories, and it never fabricates annotations. A project directory is
only evaluated from material already present on disk.

Standard library only, matching the rest of the project.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .analyzer import analyze
from .models import ALLOWED_STATUSES
from .paper_extract import PaperExtractionError
from .repository_scan import RepositoryScanError


EXPECTED_FILENAME = "expected-findings.json"
REPOSITORY_DIRNAME = "repository"
PAPER_SUFFIXES = (".txt", ".md", ".markdown", ".pdf")

#: Statuses that mean "a human still has work to do on this item".
#: Used as the positive class when computing gap-detection precision / recall.
GAP_STATUSES = frozenset({"missing", "partial", "needs_review"})

#: Marker used when the tool produced no finding for an annotated rule.
ABSENT_FROM_TOOL = "absent"

#: Rule ids follow the existing R001-R015 convention. Enforced here so that
#: `data/evaluation/schema.json` and this module stay in agreement.
RULE_ID_PATTERN = re.compile(r"R\d{3}")


class EvaluationError(RuntimeError):
    """Raised when an evaluation set or annotation file cannot be used."""


# --------------------------------------------------------------------------
# expectations
# --------------------------------------------------------------------------


def _normalise_expectations(raw: Any, source: Path) -> dict[str, str]:
    """Accept both the object form and the list form of ``expectations``.

    Object form (canonical, used by the fixed sample)::

        {"R001": "found", "R002": "partial"}

    List form (allowed when an explicit per-rule record is preferred)::

        [{"rule_id": "R001", "expected": "found"}]

    The list form is the only one in which a duplicate ``rule_id`` can be
    expressed, so duplicated ids are rejected here.
    """

    if isinstance(raw, dict):
        items: list[Any] = [
            {"rule_id": key, "expected": value} for key, value in raw.items()
        ]
    elif isinstance(raw, list):
        items = raw
    else:
        raise EvaluationError(
            f"{source}: expectations 必须是对象或数组，实际为 {type(raw).__name__}"
        )

    expectations: dict[str, str] = {}
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise EvaluationError(f"{source}: expectations 第 {index} 条不是对象")
        rule_id = item.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise EvaluationError(f"{source}: expectations 第 {index} 条缺少 rule_id")
        rule_id = rule_id.strip()
        if not RULE_ID_PATTERN.fullmatch(rule_id):
            raise EvaluationError(
                f"{source}: expectations 第 {index} 条的 rule_id 格式非法: {rule_id!r}；"
                "应为 R 加三位数字，例如 R005"
            )
        if rule_id in expectations:
            raise EvaluationError(f"{source}: rule_id 重复: {rule_id}")
        expected = item.get("expected")
        if not isinstance(expected, str) or expected not in ALLOWED_STATUSES:
            raise EvaluationError(
                f"{source}: {rule_id} 的 expected 状态非法: {expected!r}；"
                f"允许值 {sorted(ALLOWED_STATUSES)}"
            )
        expectations[rule_id] = expected

    if not expectations:
        raise EvaluationError(f"{source}: expectations 为空，没有任何标注项")
    return expectations


def load_expectations(path: Path) -> dict[str, str]:
    """Read and validate one annotation file."""

    path = Path(path)
    if not path.exists():
        raise EvaluationError(f"标注文件不存在: {path}")
    if not path.is_file():
        raise EvaluationError(f"标注路径不是文件: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise EvaluationError(f"{path}: 标注文件不是 UTF-8 文本") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"{path}: 标注文件不是合法 JSON（{exc}）") from exc

    if not isinstance(raw, dict):
        raise EvaluationError(f"{path}: 标注文件顶层必须是 JSON 对象")
    if "expectations" not in raw:
        raise EvaluationError(f"{path}: 标注文件缺少 expectations 字段")
    return _normalise_expectations(raw["expectations"], path)


# --------------------------------------------------------------------------
# project discovery
# --------------------------------------------------------------------------


def find_paper(project_dir: Path) -> Path:
    for suffix in PAPER_SUFFIXES:
        candidate = project_dir / f"paper{suffix}"
        if candidate.is_file():
            return candidate
    raise EvaluationError(
        f"{project_dir}: 未找到论文文件，应为 paper.txt / paper.md / paper.pdf 之一"
    )


def find_repository(project_dir: Path) -> Path:
    candidate = project_dir / REPOSITORY_DIRNAME
    if not candidate.is_dir():
        raise EvaluationError(f"{project_dir}: 未找到 repository/ 目录")
    return candidate


def discover_projects(root: Path) -> list[Path]:
    """Return every direct subdirectory of ``root`` carrying an annotation file."""

    root = Path(root)
    if not root.exists():
        raise EvaluationError(f"评测集目录不存在: {root}")
    if not root.is_dir():
        raise EvaluationError(f"评测集路径不是目录: {root}")

    projects = sorted(
        item
        for item in root.iterdir()
        if item.is_dir() and (item / EXPECTED_FILENAME).is_file()
    )
    if not projects:
        raise EvaluationError(
            f"评测集为空: {root} 下没有任何包含 {EXPECTED_FILENAME} 的项目目录。"
            "真实公开项目需由人提供；只想验证规则本身时，请把 --root 指向 "
            "data/examples（那是固定的自造样例，不是真实评测集）"
        )
    return projects


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> float:
    """Ratio that reads 0.0 instead of raising when the denominator is zero."""

    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


@dataclass(frozen=True)
class RuleComparison:
    """One rule, seen from both the annotation and the tool."""

    rule_id: str
    expected: str
    actual: str

    @property
    def match(self) -> bool:
        return self.expected == self.actual

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "expected": self.expected,
            "actual": self.actual,
            "match": self.match,
        }


def compute_metrics(comparisons: Iterable[RuleComparison]) -> dict[str, float]:
    """Agreement plus gap-detection precision / recall.

    The positive class is "a human still has work here" (``missing``,
    ``partial`` or ``needs_review``). Precision answers "when the tool flags
    work, is it right"; recall answers "of the work a human found, how much
    did the tool flag".
    """

    items = list(comparisons)
    total = len(items)
    matched = sum(item.match for item in items)

    true_positive = false_positive = false_negative = true_negative = 0
    for item in items:
        expected_gap = item.expected in GAP_STATUSES
        actual_gap = item.actual in GAP_STATUSES
        if expected_gap and actual_gap:
            true_positive += 1
        elif not expected_gap and actual_gap:
            false_positive += 1
        elif expected_gap and not actual_gap:
            false_negative += 1
        else:
            true_negative += 1

    return {
        "compared": float(total),
        "matched": float(matched),
        "agreement": _ratio(matched, total),
        "gap_true_positive": float(true_positive),
        "gap_false_positive": float(false_positive),
        "gap_false_negative": float(false_negative),
        "gap_true_negative": float(true_negative),
        "gap_precision": _ratio(true_positive, true_positive + false_positive),
        "gap_recall": _ratio(true_positive, true_positive + false_negative),
    }


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


@dataclass
class ProjectEvaluation:
    project_id: str
    project_dir: str
    paper_path: str
    repository_path: str
    comparisons: list[RuleComparison]
    unannotated: list[str]
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_dir": self.project_dir,
            "paper_path": self.paper_path,
            "repository_path": self.repository_path,
            "comparisons": [item.to_dict() for item in self.comparisons],
            "unannotated": list(self.unannotated),
            "metrics": self.metrics,
        }


@dataclass
class SuiteEvaluation:
    root: str
    projects: list[ProjectEvaluation]
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "project_count": len(self.projects),
            "projects": [item.to_dict() for item in self.projects],
            "metrics": self.metrics,
        }


def evaluate_project(project_dir: Path) -> ProjectEvaluation:
    """Run the tool on one annotated project and compare the two sides."""

    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        raise EvaluationError(f"项目目录不存在: {project_dir}")

    expectations = load_expectations(project_dir / EXPECTED_FILENAME)
    paper = find_paper(project_dir)
    repository = find_repository(project_dir)

    try:
        report = analyze(paper, repository)
    except (PaperExtractionError, RepositoryScanError, ValueError) as exc:
        raise EvaluationError(f"{project_dir}: 运行检查器失败（{exc}）") from exc

    actual_by_rule = {finding.rule_id: finding.status for finding in report.findings}

    comparisons = [
        RuleComparison(
            rule_id=rule_id,
            expected=expected,
            actual=actual_by_rule.get(rule_id, ABSENT_FROM_TOOL),
        )
        for rule_id, expected in expectations.items()
    ]
    unannotated = sorted(set(actual_by_rule) - set(expectations))

    return ProjectEvaluation(
        project_id=project_dir.name,
        project_dir=str(project_dir),
        paper_path=str(paper),
        repository_path=str(repository),
        comparisons=comparisons,
        unannotated=unannotated,
        metrics=compute_metrics(comparisons),
    )


def evaluate_suite(root: Path) -> SuiteEvaluation:
    """Evaluate every annotated project under ``root`` and aggregate the metrics."""

    projects = [evaluate_project(item) for item in discover_projects(Path(root))]
    comparisons = [item for project in projects for item in project.comparisons]
    return SuiteEvaluation(
        root=str(root),
        projects=projects,
        metrics=compute_metrics(comparisons),
    )


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def format_suite(suite: SuiteEvaluation) -> str:
    lines: list[str] = [
        f"评测集：{suite.root}",
        f"项目数：{len(suite.projects)}",
    ]

    for project in suite.projects:
        lines.append("")
        lines.append(f"[{project.project_id}] {project.project_dir}")
        lines.append("  rule   annotated    tool         match")
        for item in project.comparisons:
            flag = "yes" if item.match else "NO"
            lines.append(
                f"  {item.rule_id:<6} {item.expected:<12} {item.actual:<12} {flag}"
            )
        if project.unannotated:
            lines.append(f"  tool produced, not annotated: {', '.join(project.unannotated)}")
        metrics = project.metrics
        lines.append(
            f"  agreement {metrics['agreement']:.2%} "
            f"({int(metrics['matched'])}/{int(metrics['compared'])})"
            f"  gap precision {metrics['gap_precision']:.2%}"
            f"  gap recall {metrics['gap_recall']:.2%}"
        )

    metrics = suite.metrics
    lines.append("")
    lines.append("summary")
    lines.append(
        f"  compared {int(metrics['compared'])}, matched {int(metrics['matched'])}, "
        f"agreement {metrics['agreement']:.2%}"
    )
    lines.append(
        f"  gap detection: precision {metrics['gap_precision']:.2%}, "
        f"recall {metrics['gap_recall']:.2%}"
    )
    lines.append(
        f"  counts TP={int(metrics['gap_true_positive'])} "
        f"FP={int(metrics['gap_false_positive'])} "
        f"FN={int(metrics['gap_false_negative'])} "
        f"TN={int(metrics['gap_true_negative'])}"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对照人工标注与检查器判定，输出逐条结果与一致率指标。",
    )
    parser.add_argument(
        "--root",
        default="data/evaluation",
        help="评测集根目录，默认 data/evaluation；验证固定样例时可指向 data/examples",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式，默认 text",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="写入文件而不是打印到终端",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suite = evaluate_suite(Path(args.root))
    except EvaluationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        payload = json.dumps(suite.to_dict(), ensure_ascii=False, indent=2)
    else:
        payload = format_suite(suite)

    if args.output:
        target = Path(args.output)
        target.write_text(payload + "\n", encoding="utf-8")
        print(f"已写入：{target.resolve()}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
