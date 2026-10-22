"""Unit tests for the evaluation harness."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from src.evaluation import (
    ABSENT_FROM_TOOL,
    EvaluationError,
    RuleComparison,
    compute_metrics,
    discover_projects,
    evaluate_project,
    evaluate_suite,
    format_suite,
    load_expectations,
    main,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"


def make_project(root: Path, name: str = "sample") -> Path:
    """Copy the fixed sample into a temporary evaluation root."""

    destination = root / name
    shutil.copytree(SAMPLE, destination)
    return destination


def write_expectations(project_dir: Path, payload) -> None:
    (project_dir / "expected-findings.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


class MetricsTests(unittest.TestCase):
    def test_metrics_on_perfect_match(self):
        comparisons = [
            RuleComparison("R001", "found", "found"),
            RuleComparison("R002", "missing", "missing"),
        ]
        metrics = compute_metrics(comparisons)
        self.assertEqual(metrics["agreement"], 1.0)
        self.assertEqual(metrics["gap_precision"], 1.0)
        self.assertEqual(metrics["gap_recall"], 1.0)

    def test_gap_metrics_count_all_four_quadrants(self):
        comparisons = [
            RuleComparison("R001", "missing", "missing"),
            RuleComparison("R002", "found", "missing"),
            RuleComparison("R003", "missing", "found"),
            RuleComparison("R004", "found", "found"),
        ]
        metrics = compute_metrics(comparisons)
        self.assertEqual(metrics["gap_true_positive"], 1.0)
        self.assertEqual(metrics["gap_false_positive"], 1.0)
        self.assertEqual(metrics["gap_false_negative"], 1.0)
        self.assertEqual(metrics["gap_true_negative"], 1.0)
        self.assertEqual(metrics["gap_precision"], 0.5)
        self.assertEqual(metrics["gap_recall"], 0.5)
        self.assertEqual(metrics["agreement"], 0.5)

    def test_zero_denominator_returns_zero_instead_of_raising(self):
        comparisons = [RuleComparison("R001", "found", "found")]
        metrics = compute_metrics(comparisons)
        self.assertEqual(metrics["gap_precision"], 0.0)
        self.assertEqual(metrics["gap_recall"], 0.0)
        self.assertEqual(metrics["agreement"], 1.0)

    def test_empty_comparison_list_is_all_zero(self):
        metrics = compute_metrics([])
        self.assertEqual(metrics["compared"], 0.0)
        self.assertEqual(metrics["agreement"], 0.0)


class ExpectationFileTests(unittest.TestCase):
    def test_object_form_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(json.dumps({"expectations": {"R001": "found"}}), encoding="utf-8")
            self.assertEqual(load_expectations(path), {"R001": "found"})

    def test_list_form_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps(
                    {"expectations": [{"rule_id": "R001", "expected": "partial"}]}
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_expectations(path), {"R001": "partial"})

    def test_missing_expectations_field_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(json.dumps({"sample_id": "x"}), encoding="utf-8")
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_invalid_status_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps({"expectations": {"R001": "probably"}}), encoding="utf-8"
            )
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_duplicate_rule_id_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps(
                    {
                        "expectations": [
                            {"rule_id": "R001", "expected": "found"},
                            {"rule_id": "R001", "expected": "missing"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_entry_without_expected_field_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps({"expectations": [{"rule_id": "R001"}]}), encoding="utf-8"
            )
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationError):
                load_expectations(Path(directory) / "nope.json")

    def test_malformed_rule_id_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps({"expectations": {"r1": "found"}}), encoding="utf-8"
            )
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_rule_id_without_three_digits_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(
                json.dumps({"expectations": {"R01": "found"}}), encoding="utf-8"
            )
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(EvaluationError):
                load_expectations(path)

    def test_empty_expectations_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected-findings.json"
            path.write_text(json.dumps({"expectations": {}}), encoding="utf-8")
            with self.assertRaises(EvaluationError):
                load_expectations(path)


class DiscoveryTests(unittest.TestCase):
    def test_empty_root_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationError):
                discover_projects(Path(directory))

    def test_missing_root_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationError):
                discover_projects(Path(directory) / "absent")

    def test_directory_without_annotation_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "no-annotations").mkdir()
            with self.assertRaises(EvaluationError):
                discover_projects(root)

    def test_annotation_directory_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_project(root)
            self.assertEqual([item.name for item in discover_projects(root)], ["sample"])


class ProjectEvaluationTests(unittest.TestCase):
    def test_matches_fixed_sample_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            result = evaluate_project(project)
            self.assertEqual(int(result.metrics["compared"]), 15)
            self.assertEqual(result.metrics["agreement"], 1.0)
            self.assertEqual(result.metrics["gap_precision"], 1.0)
            self.assertEqual(result.metrics["gap_recall"], 1.0)
            self.assertEqual(result.unannotated, [])

    def test_unannotated_rules_are_listed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            write_expectations(project, {"expectations": {"R001": "found"}})
            result = evaluate_project(project)
            self.assertIn("R002", result.unannotated)
            self.assertEqual(len(result.comparisons), 1)

    def test_rule_absent_from_tool_is_marked(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            write_expectations(project, {"expectations": {"R999": "found"}})
            result = evaluate_project(project)
            self.assertEqual(result.comparisons[0].actual, ABSENT_FROM_TOOL)
            self.assertFalse(result.comparisons[0].match)
            self.assertEqual(result.metrics["gap_recall"], 0.0)

    def test_detected_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            write_expectations(
                project,
                {"expectations": {"R001": "found", "R002": "missing"}},
            )
            result = evaluate_project(project)
            self.assertEqual(int(result.metrics["compared"]), 2)
            self.assertEqual(result.metrics["agreement"], 0.5)

    def test_missing_paper_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            (project / "paper.txt").unlink()
            with self.assertRaises(EvaluationError):
                evaluate_project(project)

    def test_missing_repository_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(Path(directory))
            shutil.rmtree(project / "repository")
            with self.assertRaises(EvaluationError):
                evaluate_project(project)

    def test_missing_project_directory_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationError):
                evaluate_project(Path(directory) / "absent")


class SuiteTests(unittest.TestCase):
    def test_suite_on_fixed_sample_root(self):
        suite = evaluate_suite(ROOT / "data" / "examples")
        self.assertEqual(len(suite.projects), 1)
        self.assertEqual(suite.metrics["agreement"], 1.0)
        self.assertIn("summary", format_suite(suite))

    def test_suite_aggregates_multiple_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_project(root, "first")
            make_project(root, "second")
            suite = evaluate_suite(root)
            self.assertEqual(len(suite.projects), 2)
            self.assertEqual(int(suite.metrics["compared"]), 30)
            self.assertEqual(suite.metrics["agreement"], 1.0)

    def test_suite_on_empty_root_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EvaluationError):
                evaluate_suite(Path(directory))

    def test_json_payload_is_serialisable(self):
        suite = evaluate_suite(ROOT / "data" / "examples")
        encoded = json.dumps(suite.to_dict(), ensure_ascii=False)
        self.assertIn("gap_precision", encoded)


class CommandLineTests(unittest.TestCase):
    def test_success_returns_zero(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--root", str(ROOT / "data" / "examples")])
        self.assertEqual(code, 0)
        self.assertIn("agreement", buffer.getvalue())

    def test_empty_set_returns_two_with_readable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = main(["--root", directory])
            self.assertEqual(code, 2)
            self.assertIn("评测集为空", errors.getvalue())

    def test_json_format_and_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "--root",
                        str(ROOT / "data" / "examples"),
                        "--format",
                        "json",
                        "--output",
                        str(target),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["project_count"], 1)


if __name__ == "__main__":
    unittest.main()
