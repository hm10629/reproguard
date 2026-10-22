import json
from pathlib import Path
import re
import tempfile
import unittest

from src.analyzer import analyze
from src.models import ALLOWED_STATUSES
from src.paper_extract import load_paper
from src.repository_scan import scan_repository
from src.rules import run_checks


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"

# 预期结果清单实际位于 data/examples/README.md。
# 注意：交接单 T-007 第 5 节第 2 条指向 incomplete-ml-project/README.md，该路径不存在。
EXPECTATIONS_README = ROOT / "data" / "examples" / "README.md"

# 论文刻意不出现 tinycnn、cifar-10、imagenet、mnist，使 R011 走兜底分支。
NEEDS_REVIEW_PAPER = (
    "本文提出一种新的图像分类方法，并在公开数据上报告了主要实验结果。\n"
    "训练在单张消费级显卡上完成，未公开权重文件。\n"
)
NEEDS_REVIEW_TRAIN = "def main():\n    print('training loop ready')\n"

# 匹配形如 `- R001 项目说明文档：found` 的条目，只取规则编号与状态，不依赖中文标题。
EXPECTATION_LINE = re.compile(
    r"^- (R\d{3})\s+.+：("
    + "|".join(sorted(ALLOWED_STATUSES, key=len, reverse=True))
    + r")\s*$",
    re.MULTILINE,
)


class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paper = load_paper(SAMPLE / "paper.txt")
        cls.repo = scan_repository(SAMPLE / "repository")
        cls.findings = {finding.rule_id: finding for finding in run_checks(cls.paper, cls.repo)}

    def test_all_fifteen_rules_return_allowed_status(self):
        allowed = {"found", "partial", "missing", "not_applicable", "needs_review"}
        self.assertEqual(len(self.findings), 15)
        self.assertTrue(all(item.status in allowed for item in self.findings.values()))

    def test_matches_sample_expectations(self):
        expected = json.loads((SAMPLE / "expected-findings.json").read_text(encoding="utf-8"))
        for rule_id, status in expected["expectations"].items():
            self.assertEqual(self.findings[rule_id].status, status, rule_id)

    def test_missing_findings_use_careful_language(self):
        for finding in self.findings.values():
            if finding.status == "missing":
                self.assertIn("当前检查范围内未找到", finding.finding)

    def test_found_and_partial_findings_have_evidence(self):
        """found 与 partial 必须给出证据。

        needs_review 表示无法可靠判断，按设计允许空证据，因此不纳入本条不变式。
        该状态由下方临时样例覆盖。
        """

        for finding in self.findings.values():
            if finding.status in {"found", "partial"}:
                self.assertTrue(finding.evidence, finding.rule_id)

    def test_sample_readme_matches_expected_findings(self):
        readme = EXPECTATIONS_README.read_text(encoding="utf-8")
        expected = json.loads(
            (SAMPLE / "expected-findings.json").read_text(encoding="utf-8")
        )["expectations"]

        documented = {
            match.group(1): match.group(2)
            for match in EXPECTATION_LINE.finditer(readme)
        }

        self.assertEqual(documented, expected)

    def _analyze_without_known_terms(self):
        """构造一次性样例：论文不出现已知模型或数据集术语。

        固定样例不含 needs_review，且 R011 的兜底分支不附带证据。
        用临时目录可以在不改动固定样例报告结果的前提下覆盖该状态。
        """

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        paper_path = root / "paper.txt"
        paper_path.write_text(NEEDS_REVIEW_PAPER, encoding="utf-8")
        repository = root / "repository"
        repository.mkdir()
        (repository / "train.py").write_text(NEEDS_REVIEW_TRAIN, encoding="utf-8")
        return analyze(paper_path, repository)

    def test_r011_returns_needs_review_without_known_terms(self):
        report = self._analyze_without_known_terms()

        finding = next(item for item in report.findings if item.rule_id == "R011")

        self.assertEqual(finding.status, "needs_review")
        self.assertEqual(finding.evidence, [])
        self.assertAlmostEqual(finding.confidence, 0.45)

    def test_needs_review_finding_enters_action_items(self):
        report = self._analyze_without_known_terms()

        items = [
            item
            for item in report.summary["action_items"]
            if item["rule_id"] == "R011"
        ]

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "needs_review")
        self.assertEqual(items[0]["severity"], "high")
        self.assertEqual(items[0]["evidence_locations"], [])

    def test_generic_output_weight_version_and_issue_words_do_not_create_false_positives(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        paper_path = root / "paper.txt"
        paper_path.write_text("A model uses random weight initialization.\n", encoding="utf-8")
        repository = root / "repository"
        repository.mkdir()
        (repository / "README.md").write_text(
            "This is a modified version.\n"
            "output = model(input_tensor)\n"
            "This change may not make sense theoretically.\n"
            "See https://github.com/example/project/issues/1 for context.\n",
            encoding="utf-8",
        )
        (repository / "model.py").write_text(
            "def forward(value):\n    return value\n",
            encoding="utf-8",
        )

        findings = {
            item.rule_id: item
            for item in run_checks(load_paper(paper_path), scan_repository(repository))
        }

        self.assertEqual(findings["R008"].status, "missing")
        self.assertEqual(findings["R010"].status, "missing")
        self.assertEqual(findings["R012"].status, "missing")
        self.assertEqual(findings["R013"].status, "missing")
        self.assertEqual(findings["R015"].status, "missing")

    def _findings_for_repository(self, files: dict[str, str]):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        paper_path = root / "paper.txt"
        paper_path.write_text(
            "We evaluate on the ExampleSet dataset.\n", encoding="utf-8"
        )
        repository = root / "repository"
        repository.mkdir()
        for relative_path, content in files.items():
            target = repository / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return {
            item.rule_id: item
            for item in run_checks(load_paper(paper_path), scan_repository(repository))
        }

    def test_r001_readme_without_install_and_experiment_command_is_partial(self):
        findings = self._findings_for_repository(
            {"README.md": "# Model\nfrom model import Network\noutput = model(input)\n"}
        )

        self.assertEqual(findings["R001"].status, "partial")
        self.assertIn("安装说明", findings["R001"].finding)
        self.assertIn("训练或评测命令", findings["R001"].finding)

    def test_r001_install_and_experiment_command_are_found(self):
        findings = self._findings_for_repository(
            {
                "README.md": (
                    "# Model\npip install -r requirements.txt\n"
                    "python train.py --epochs 10\n"
                )
            }
        )

        self.assertEqual(findings["R001"].status, "found")

    def test_r003_generic_url_is_not_dataset_download_evidence(self):
        findings = self._findings_for_repository(
            {
                "README.md": (
                    "The ExampleSet dataset is used.\n"
                    "Paper: https://example.org/paper\n"
                    "Issue: https://github.com/example/repo/issues/1\n"
                )
            }
        )

        self.assertEqual(findings["R003"].status, "partial")

    def test_r003_dataset_url_is_download_evidence(self):
        findings = self._findings_for_repository(
            {
                "README.md": (
                    "The ExampleSet dataset is used.\n"
                    "Dataset download: https://example.org/datasets/example-set\n"
                )
            }
        )

        self.assertEqual(findings["R003"].status, "found")

    def test_r014_code_license_without_data_terms_is_partial(self):
        findings = self._findings_for_repository(
            {
                "README.md": "The ExampleSet dataset is used.\n",
                "LICENSE": "MIT License\nPermission is hereby granted.\n",
            }
        )

        self.assertEqual(findings["R014"].status, "partial")

    def test_r014_code_and_dataset_license_information_are_found(self):
        findings = self._findings_for_repository(
            {
                "README.md": (
                    "The ExampleSet dataset license permits research use; "
                    "redistribution is prohibited.\n"
                ),
                "LICENSE": "MIT License\nPermission is hereby granted.\n",
            }
        )

        self.assertEqual(findings["R014"].status, "found")


if __name__ == "__main__":
    unittest.main()
