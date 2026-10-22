"""JSON and Markdown report serialization."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Finding, Report


STATUS_LABELS = {
    "found": "已确认",
    "partial": "部分满足",
    "missing": "当前范围内未找到",
    "not_applicable": "不适用",
    "needs_review": "需要人工确认",
}

SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}

NO_ACTION_ITEMS_TEXT = "本次检查未发现待修复任务。"
NO_EVIDENCE_LOCATION_TEXT = "当前检查范围内未找到"

MODEL_ASSISTANCE_TITLE = "模型辅助结果"
MODEL_ASSISTANCE_DISCLAIMER = "以下为本地开源模型给出的辅助结果，不替代规则判定。"
MODEL_STATUS_LABELS = {
    "ok": "已完成",
    "unavailable": "模型不可用",
    "invalid_response": "模型输出不可用",
}


def report_to_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _finding_markdown(finding: Finding) -> str:
    lines = [
        f"### {finding.rule_id} {finding.title}",
        "",
        f"- 状态：**{STATUS_LABELS[finding.status]}**",
        f"- 风险：**{SEVERITY_LABELS[finding.severity]}**",
        f"- 置信度：{finding.confidence:.0%}",
        f"- 结论：{finding.finding}",
        f"- 建议：{finding.suggestion}",
    ]
    if finding.evidence:
        lines.extend(["- 证据："])
        for evidence in finding.evidence:
            lines.append(
                f"  - `{evidence.location}`：{evidence.quote}"
            )
    return "\n".join(lines)


def _action_item_markdown(item: dict) -> str:
    lines = [
        f"### {item['task_id']} {item['rule_id']} {item['title']}",
        "",
        f"- 风险：**{SEVERITY_LABELS[item['severity']]}**",
        f"- 状态：**{STATUS_LABELS[item['status']]}**",
        f"- 行动：{item['action']}",
    ]
    if item["evidence_locations"]:
        lines.append("- 证据位置：")
        for location in item["evidence_locations"]:
            lines.append(f"  - `{location}`")
    else:
        lines.append(f"- 证据位置：{NO_EVIDENCE_LOCATION_TEXT}")
    return "\n".join(lines)


def _model_assistance_markdown(assistance: dict) -> str:
    """Render the optional model-assisted block as its own Markdown section."""

    status = assistance.get("status", "")
    lines = [
        f"## {MODEL_ASSISTANCE_TITLE}",
        "",
        f"> {MODEL_ASSISTANCE_DISCLAIMER}",
        "",
        f"- 提供方：{assistance.get('provider', '')}",
        f"- 模型：{assistance.get('model', '')}",
        f"- 状态：**{MODEL_STATUS_LABELS.get(status, status)}**",
    ]
    message = assistance.get("message")
    if message:
        lines.append(f"- 说明：{message}")
    elements = assistance.get("experiment_elements", [])
    if elements:
        lines.extend(["", "### 抽取到的实验要素", ""])
        for item in elements:
            refs = "、".join(item.get("source_refs", []))
            value = item.get("value") or "（模型未给出取值）"
            lines.append(f"- **{item.get('name', '')}**：{value}（来源：{refs}）")
    notes = assistance.get("review_notes", [])
    if notes:
        lines.extend(["", "### 人工复核提示", ""])
        lines.extend(f"- {note}" for note in notes)
    dropped = assistance.get("dropped_source_refs", [])
    if dropped:
        lines.extend(
            [
                "",
                f"> 已忽略 {len(dropped)} 个不在来源清单内的编号：{'、'.join(dropped)}",
            ]
        )
    return "\n".join(lines)


def report_to_markdown(report: Report) -> str:
    summary = report.summary
    lines = [
        f"# 科研复现体检报告：{report.project_name}",
        "",
        f"- 论文：`{report.paper_path}`",
        f"- 仓库：`{report.repository_path}`",
        f"- 生成时间：`{report.generated_at}`",
        "",
        "## 摘要",
        "",
        f"- 检查项：{summary['total_findings']}",
        f"- 已确认：{summary['found_count']}",
        f"- 部分满足：{summary['partial_count']}",
        f"- 当前范围内未找到：{summary['missing_count']}",
        f"- 需要人工确认：{summary['needs_review_count']}",
        f"- 高风险：{summary['high_risk_count']}",
        f"- 中风险：{summary['medium_risk_count']}",
        f"- 低风险：{summary['low_risk_count']}",
        f"- 证据覆盖率：{summary['evidence_coverage']:.1%}",
        "",
        "## 待修复任务",
        "",
    ]
    action_items = summary.get("action_items", [])
    if action_items:
        lines.extend(_action_item_markdown(item) for item in action_items)
    else:
        lines.append(NO_ACTION_ITEMS_TEXT)
    lines.extend(
        [
            "",
            "## 检查结果",
            "",
        ]
    )
    ordered = sorted(
        report.findings,
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}[item.severity],
            {"missing": 0, "partial": 1, "needs_review": 2, "found": 3, "not_applicable": 4}[item.status],
            item.rule_id,
        ),
    )
    lines.extend(_finding_markdown(item) for item in ordered)
    lines.append("")
    lines.append("> “当前范围内未找到”不等于证明项目绝对没有该信息。")
    if report.model_assistance:
        lines.append("")
        lines.append(_model_assistance_markdown(report.model_assistance))
    return "\n\n".join(lines) + "\n"


def write_reports(report: Report, output_prefix: Path, formats: str = "both") -> list[Path]:
    """Write selected report files and return their paths."""

    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if formats in {"json", "both"}:
        json_path = output_prefix.with_suffix(".json")
        json_path.write_text(report_to_json(report), encoding="utf-8")
        paths.append(json_path)
    if formats in {"markdown", "both"}:
        markdown_path = output_prefix.with_suffix(".md")
        markdown_path.write_text(report_to_markdown(report), encoding="utf-8")
        paths.append(markdown_path)
    return paths
