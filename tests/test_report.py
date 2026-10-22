from pathlib import Path
import json
import tempfile
import unittest

from src.analyzer import analyze, summarize
from src.models import Finding, Report
from src.report import report_to_json, report_to_markdown, write_reports


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"

REQUIRED_ACTION_FIELDS = {
    "task_id",
    "rule_id",
    "title",
    "severity",
    "status",
    "action",
    "evidence_locations",
}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _report_with(findings):
    return Report(
        project_name="demo",
        paper_path="paper.txt",
        repository_path="repository",
        findings=findings,
        summary=summarize(findings),
        generated_at="2026-01-01T00:00:00+00:00",
    )


class ReportTests(unittest.TestCase):
    def test_json_and_markdown_contain_same_project(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        data = json.loads(report_to_json(report))
        markdown = report_to_markdown(report)
        self.assertEqual(data["project_name"], "repository")
        self.assertIn("科研复现体检报告", markdown)
        self.assertIn("R002", markdown)

    def test_write_reports_creates_selected_files(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports(report, Path(directory) / "report", "both")
            self.assertEqual({path.suffix for path in paths}, {".json", ".md"})
            self.assertTrue(all(path.exists() for path in paths))

    def test_action_items_cover_every_unresolved_finding(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        items = report.summary["action_items"]
        actionable = [
            finding
            for finding in report.findings
            if finding.status in {"missing", "partial", "needs_review"}
        ]
        self.assertTrue(items)
        self.assertEqual(len(items), len(actionable))
        self.assertEqual(
            sorted(item["rule_id"] for item in items),
            sorted(finding.rule_id for finding in actionable),
        )

    def test_action_items_exclude_resolved_findings(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        statuses = {item["status"] for item in report.summary["action_items"]}
        self.assertTrue(statuses <= {"missing", "partial", "needs_review"})
        self.assertNotIn("found", statuses)
        self.assertNotIn("not_applicable", statuses)

    def test_action_items_skip_not_applicable_findings(self):
        findings = [
            Finding(rule_id="R001", title="不适用项", status="not_applicable", severity="low", finding="不适用。"),
            Finding(rule_id="R002", title="缺失项", status="missing", severity="high", finding="缺失。"),
        ]
        summary = summarize(findings)
        self.assertEqual([item["rule_id"] for item in summary["action_items"]], ["R002"])

    def test_action_items_have_required_fields_and_stable_order(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        items = report.summary["action_items"]
        for item in items:
            self.assertTrue(REQUIRED_ACTION_FIELDS.issubset(item.keys()))
            self.assertIsInstance(item["evidence_locations"], list)
        order = [
            (SEVERITY_ORDER[item["severity"]], item["rule_id"]) for item in items
        ]
        self.assertEqual(order, sorted(order))
        self.assertEqual(
            [item["task_id"] for item in items],
            [f"T{index:02d}" for index in range(1, len(items) + 1)],
        )

    def test_action_items_trace_back_to_findings(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        by_rule = {finding.rule_id: finding for finding in report.findings}
        for item in report.summary["action_items"]:
            finding = by_rule[item["rule_id"]]
            self.assertEqual(item["title"], finding.title)
            self.assertEqual(item["severity"], finding.severity)
            self.assertEqual(item["action"], finding.suggestion)
            self.assertEqual(
                item["evidence_locations"],
                [evidence.location for evidence in finding.evidence],
            )

    def test_markdown_shows_action_section_with_first_task(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        markdown = report_to_markdown(report)
        self.assertIn("## 待修复任务", markdown)
        first = report.summary["action_items"][0]
        self.assertIn(first["task_id"], markdown)
        self.assertIn(first["rule_id"], markdown)
        self.assertIn(first["action"], markdown)

    def test_markdown_states_when_no_action_items(self):
        findings = [
            Finding(
                rule_id="R001",
                title="是否存在项目说明文档",
                status="found",
                severity="medium",
                finding="找到说明文档。",
            )
        ]
        report = _report_with(findings)
        self.assertEqual(report.summary["action_items"], [])
        markdown = report_to_markdown(report)
        self.assertIn("## 待修复任务", markdown)
        self.assertIn("本次检查未发现待修复任务。", markdown)

    def test_json_keeps_existing_summary_fields(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        summary = json.loads(report_to_json(report))["summary"]
        for key in (
            "total_findings",
            "found_count",
            "partial_count",
            "missing_count",
            "needs_review_count",
            "not_applicable_count",
            "high_risk_count",
            "medium_risk_count",
            "low_risk_count",
            "evidence_coverage",
        ):
            self.assertIn(key, summary)
        self.assertIn("action_items", summary)
        self.assertIsInstance(summary["action_items"], list)
        self.assertTrue(summary["action_items"])

    def test_json_omits_model_block_in_rules_mode(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")

        # Rule-only reports must keep the exact old JSON contract.
        self.assertNotIn("model_assistance", json.loads(report_to_json(report)))

    def test_reports_render_optional_model_block(self):
        findings = [
            Finding(
                rule_id="R001",
                title="是否存在项目说明文档",
                status="found",
                severity="medium",
                finding="找到说明文档。",
            )
        ]
        report = _report_with(findings)
        report.model_assistance = {
            "provider": "ollama",
            "model": "qwen2.5:3b",
            "base_url": "http://127.0.0.1:11434",
            "status": "ok",
            "experiment_elements": [
                {"name": "数据集", "value": "MNIST", "source_refs": ["P001"]}
            ],
            "review_notes": ["人工确认数据划分"],
            "source_refs": ["P001"],
            "dropped_source_refs": [],
            "message": "模型辅助结果仅供参考，不替代规则判定。",
        }

        markdown = report_to_markdown(report)
        data = json.loads(report_to_json(report))

        self.assertIn("## 模型辅助结果", markdown)
        self.assertIn("不替代规则判定", markdown)
        self.assertIn("MNIST", markdown)
        self.assertIn("P001", markdown)
        self.assertIn("人工确认数据划分", markdown)
        self.assertEqual(data["model_assistance"]["model"], "qwen2.5:3b")


if __name__ == "__main__":
    unittest.main()
