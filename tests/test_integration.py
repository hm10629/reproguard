from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from src.analyzer import analyze


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"


class IntegrationTests(unittest.TestCase):
    def test_end_to_end_analysis(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        self.assertEqual(report.summary["total_findings"], 15)
        self.assertGreater(report.summary["high_risk_count"], 0)
        self.assertTrue(report.summary["action_items"])

    def test_cli_report_contains_action_items(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.cli",
                    "--paper",
                    str(SAMPLE / "paper.txt"),
                    "--repo",
                    str(SAMPLE / "repository"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            items = data["summary"]["action_items"]
            self.assertTrue(items)
            required = {
                "task_id",
                "rule_id",
                "title",
                "severity",
                "status",
                "action",
                "evidence_locations",
            }
            self.assertTrue(required.issubset(items[0].keys()))
            markdown = output.with_suffix(".md").read_text(encoding="utf-8")
            self.assertIn("## 待修复任务", markdown)
            self.assertIn(items[0]["rule_id"], markdown)

    def test_cli_generates_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "first-report"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.cli",
                    "--paper",
                    str(SAMPLE / "paper.txt"),
                    "--repo",
                    str(SAMPLE / "repository"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.with_suffix(".json").exists())
            self.assertTrue(output.with_suffix(".md").exists())
            data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["total_findings"], 15)

    def test_cli_rejects_missing_paper(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.cli",
                "--paper",
                str(ROOT / "missing.txt"),
                "--repo",
                str(SAMPLE / "repository"),
                "--output",
                str(ROOT / "reports" / "unused"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("论文路径不存在", result.stderr)

    def test_cli_ollama_mode_without_service_records_status(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.cli",
                    "--paper",
                    str(SAMPLE / "paper.txt"),
                    "--repo",
                    str(SAMPLE / "repository"),
                    "--output",
                    str(output),
                    "--model-mode",
                    "ollama",
                    "--ollama-url",
                    "http://127.0.0.1:1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

        # A missing local model must never invalidate the deterministic result.
        self.assertEqual(data["summary"]["total_findings"], 15)
        self.assertEqual(data["model_assistance"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
