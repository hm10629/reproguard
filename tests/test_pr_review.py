from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from src.model_assist import ModelConfig
from src.pr_review import (
    github_annotations,
    parse_unified_diff,
    report_to_markdown,
    review_pull_request,
)


ROOT = Path(__file__).resolve().parents[1]

PARAMETER_DIFF = """diff --git a/config.yaml b/config.yaml
index 1111111..2222222 100644
--- a/config.yaml
+++ b/config.yaml
@@ -2,3 +2,3 @@ model: unet
-batch_size: 1
+batch_size: 8
 seed: 42
"""

SEED_REMOVAL_DIFF = """diff --git a/train.py b/train.py
--- a/train.py
+++ b/train.py
@@ -9,2 +9,1 @@ def train():
-    seed = 42
     run_training()
"""

# Minimal verbatim excerpts from the merged upstream PR used by the public case.
# Source: https://github.com/milesial/Pytorch-UNet/pull/141
PYTORCH_UNET_PR_141_EXCERPT = """diff --git a/eval.py b/eval.py
--- a/eval.py
+++ b/eval.py
@@ -5,5 +5,7 @@ def eval_net(net, loader, device, n_val):
-def eval_net(net, loader, device, n_val):
+def eval_net(net, loader, device):
+    n_val = len(loader)  # the number of batch
     tot = 0
@@ -20,5 +22,6 @@ def eval_net(net, loader, device):
-                pred = (pred > 0.5).float()
+                pred = torch.sigmoid(mask_pred)
+                pred = (pred > 0.5).float()
                 tot += dice_coeff(pred, true_masks).item()
     return tot / n_val
diff --git a/train.py b/train.py
--- a/train.py
+++ b/train.py
@@ -38,1 +38,1 @@ def train_net(net):
-    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False)
+    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False, drop_last=True)
"""


class FakeModelClient:
    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, prompt):
        self.prompt = prompt
        return self.payload


class PullRequestReviewTests(unittest.TestCase):
    def test_parser_preserves_added_and_removed_line_numbers(self):
        files = parse_unified_diff(PARAMETER_DIFF)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "config.yaml")
        removed = next(item for item in files[0].lines if item.kind == "removed")
        added = next(item for item in files[0].lines if item.kind == "added")
        self.assertEqual(removed.old_line, 2)
        self.assertEqual(added.new_line, 2)

    def test_parser_accepts_quoted_paths_with_spaces(self):
        diff = """diff --git \"a/config files/train.yaml\" \"b/config files/train.yaml\"
--- \"a/config files/train.yaml\"
+++ \"b/config files/train.yaml\"
@@ -1 +1 @@
-batch_size: 1
+batch_size: 8
"""
        files = parse_unified_diff(diff)
        self.assertEqual(files[0].path, "config files/train.yaml")

    def test_parameter_change_without_constraint_is_pending_medium_risk(self):
        report = review_pull_request(PARAMETER_DIFF)
        finding = next(item for item in report.findings if item.category == "parameter_change")
        self.assertEqual(finding.severity, "medium")
        self.assertEqual(finding.file, "config.yaml")
        self.assertEqual(finding.line, 2)
        self.assertIn("`1`", finding.message)
        self.assertIn("`8`", finding.message)
        self.assertTrue(finding.needs_human_review)

    def test_constraint_old_value_escalates_parameter_change(self):
        with tempfile.TemporaryDirectory() as directory:
            constraint = Path(directory) / "paper.txt"
            constraint.write_text("Training uses batch size 1 for all experiments.\n", encoding="utf-8")
            report = review_pull_request(PARAMETER_DIFF, constraints_path=constraint)

        finding = next(item for item in report.findings if item.category == "parameter_change")
        self.assertEqual(finding.severity, "high")
        self.assertTrue(any(item["source"] == "constraint" for item in finding.evidence))
        self.assertIn("page 1, line 1", [item["location"] for item in finding.evidence])

    def test_numeric_constraint_does_not_match_larger_number(self):
        with tempfile.TemporaryDirectory() as directory:
            constraint = Path(directory) / "paper.txt"
            constraint.write_text("Training uses batch size 16.\n", encoding="utf-8")
            report = review_pull_request(PARAMETER_DIFF, constraints_path=constraint)

        finding = next(item for item in report.findings if item.category == "parameter_change")
        self.assertEqual(finding.severity, "medium")
        self.assertFalse(any(item["source"] == "constraint" for item in finding.evidence))

    def test_nested_parameter_name_is_normalized(self):
        diff = PARAMETER_DIFF.replace("batch_size", "training.batch_size")
        report = review_pull_request(diff)
        self.assertTrue(any(item.category == "parameter_change" for item in report.findings))

    def test_argparse_default_change_is_detected(self):
        diff = """diff --git a/train.py b/train.py
--- a/train.py
+++ b/train.py
@@ -10 +10 @@ def parse_args():
-    parser.add_argument("--batch-size", type=int, default=64)
+    parser.add_argument("--batch-size", type=int, default=32)
"""
        report = review_pull_request(diff)
        finding = next(item for item in report.findings if item.category == "parameter_change")
        self.assertEqual(finding.file, "train.py")
        self.assertEqual(finding.line, 10)
        self.assertIn("`64`", finding.message)
        self.assertIn("`32`", finding.message)

    def test_seed_removal_is_high_risk(self):
        report = review_pull_request(SEED_REMOVAL_DIFF)
        finding = next(item for item in report.findings if item.category == "seed_removed")
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.file, "train.py")

    def test_dependency_and_pipeline_changes_are_detected(self):
        diff = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1 @@
-torch==2.1.0
+torch==2.2.0
diff --git a/preprocess.py b/preprocess.py
--- a/preprocess.py
+++ b/preprocess.py
@@ -4 +4 @@
-data = normalize(data)
+data = augmentation(data)
"""
        report = review_pull_request(diff)
        categories = {item.category for item in report.findings}
        self.assertIn("dependency_change", categories)
        self.assertIn("pipeline_change", categories)

    def test_real_pytorch_unet_pr_141_evaluation_changes_are_detected(self):
        report = review_pull_request(PYTORCH_UNET_PR_141_EXCERPT)
        pipeline_findings = [
            item for item in report.findings if item.category == "pipeline_change"
        ]
        self.assertEqual(len(pipeline_findings), 2)
        self.assertEqual({item.file for item in pipeline_findings}, {"eval.py", "train.py"})
        self.assertTrue(all(item.needs_human_review for item in pipeline_findings))
        eval_finding = next(item for item in pipeline_findings if item.file == "eval.py")
        self.assertTrue(any("sigmoid" in item["quote"] for item in eval_finding.evidence))
        denominator = next(
            item
            for item in report.findings
            if item.category == "evaluation_denominator_change"
        )
        self.assertEqual(denominator.file, "eval.py")
        self.assertEqual(denominator.severity, "high")
        self.assertTrue(any("len(loader)" in item["quote"] for item in denominator.evidence))
        self.assertTrue(any("/ n_val" in item["quote"] for item in denominator.evidence))

    def test_loader_length_without_metric_division_does_not_warn(self):
        diff = """diff --git a/train.py b/train.py
--- a/train.py
+++ b/train.py
@@ -1 +1,2 @@
 def train(loader):
+    batch_count = len(loader)
"""
        report = review_pull_request(diff)

        self.assertFalse(
            any(item.category == "evaluation_denominator_change" for item in report.findings)
        )

    def test_unrelated_code_change_produces_no_rule_findings(self):
        diff = """diff --git a/ui.py b/ui.py
--- a/ui.py
+++ b/ui.py
@@ -1 +1 @@
-title = "Old"
+title = "New"
"""
        report = review_pull_request(diff)
        self.assertEqual(report.findings, [])

    def test_model_assistance_drops_unknown_and_non_diff_citations(self):
        payload = {
            "risks": [
                {
                    "category": "parameter",
                    "severity": "high",
                    "title": "参数变化",
                    "explanation": "需要复核",
                    "suggestion": "补充结果",
                    "source_refs": ["D001", "P999"],
                },
                {
                    "category": "unsupported",
                    "severity": "medium",
                    "title": "无变更证据",
                    "source_refs": ["P001"],
                },
            ],
            "review_notes": ["人工确认"],
        }
        report = review_pull_request(
            PARAMETER_DIFF,
            model_config=ModelConfig(enabled=True),
            model_client=FakeModelClient(payload),
        )
        assistance = report.model_assistance
        self.assertEqual(assistance["status"], "ok")
        self.assertEqual(len(assistance["risks"]), 1)
        self.assertEqual(assistance["risks"][0]["source_refs"], ["D001"])
        self.assertEqual(assistance["dropped_source_refs"], ["P999", "P001"])

    def test_markdown_json_and_github_annotations_are_structured(self):
        report = review_pull_request(SEED_REMOVAL_DIFF)
        markdown = report_to_markdown(report)
        annotation = github_annotations(report)[0]
        payload = report.to_dict()
        self.assertIn("ReproGuard PR", markdown)
        self.assertIn("等待人工确认", markdown)
        self.assertEqual(payload["summary"]["high_count"], 1)
        self.assertTrue(annotation.startswith("::warning file=train.py,line=9"))
        self.assertIn("title=ReproGuard PR001", annotation)

    def test_cli_writes_reports_and_supports_fail_on(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diff = root / "change.diff"
            diff.write_text(SEED_REMOVAL_DIFF, encoding="utf-8")
            output = root / "review"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.pr_review",
                    "--diff",
                    str(diff),
                    "--output",
                    str(output),
                    "--github-annotations",
                    "--fail-on",
                    "high",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertTrue(output.with_suffix(".json").exists())
            self.assertTrue(output.with_suffix(".md").exists())
            data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["high_count"], 1)
            self.assertIn("::warning", result.stdout)

    def test_cli_reads_stdin_and_writes_github_environment_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "review"
            step_summary = root / "step-summary.md"
            github_output = root / "github-output.txt"
            environment = dict(os.environ)
            environment["GITHUB_STEP_SUMMARY"] = str(step_summary)
            environment["GITHUB_OUTPUT"] = str(github_output)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.pr_review",
                    "--diff",
                    "-",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                input=PARAMETER_DIFF,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary_text = step_summary.read_text(encoding="utf-8")
            output_text = github_output.read_text(encoding="utf-8")
            self.assertIn("ReproGuard PR", summary_text)
            self.assertIn("finding-count=1", output_text)
            self.assertIn("high-count=0", output_text)
            self.assertIn("report-json=", output_text)
            self.assertIn("report-markdown=", output_text)


if __name__ == "__main__":
    unittest.main()
