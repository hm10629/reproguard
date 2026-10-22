from pathlib import Path
import unittest

from src.alignment import detect_run_deviations
from src.protocol_extract import create_passport_from_paper
from src.workflow import add_protocol_step, record_reproduction_run


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "data" / "examples" / "incomplete-ml-project" / "paper.txt"


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.pack, _ = create_passport_from_paper(PAPER)
        self.step = add_protocol_step(
            self.pack,
            title="运行训练",
            expected_parameters_json='{"batch_size": 64}',
            source_location="paper.txt:7",
            evidence_content="batch size 64",
        )

    def _record(self, *, actual_parameters, with_evidence=True):
        return record_reproduction_run(
            self.pack,
            title="测试运行",
            status="completed",
            step_entries=[
                {
                    "step_id": self.step.step_id,
                    "status": "completed",
                    "actual_parameters_json": actual_parameters,
                    "source_location": "run.log:1" if with_evidence else "",
                    "evidence_content": "batch_size=32" if with_evidence else "",
                }
            ],
        )

    def test_parameter_conflict_creates_cited_pending_deviation(self):
        run = self._record(actual_parameters='{"batch_size": 32}')

        deviations = detect_run_deviations(self.pack, run.run_id)

        self.assertEqual(len(deviations), 1)
        self.assertIn("参数不一致", deviations[0].summary)
        self.assertEqual(deviations[0].expected, "64")
        self.assertEqual(deviations[0].observed, "32")
        self.assertEqual(deviations[0].status, "needs_review")
        review = next(
            item for item in self.pack.reviews if item.target_id == deviations[0].deviation_id
        )
        self.assertEqual(review.decision, "pending")

    def test_missing_parameter_and_process_evidence_are_separate(self):
        run = self._record(actual_parameters="{}", with_evidence=False)

        deviations = detect_run_deviations(self.pack, run.run_id)

        self.assertEqual(len(deviations), 2)
        summaries = [item.summary for item in deviations]
        self.assertTrue(any("缺少实际过程证据" in item for item in summaries))
        self.assertTrue(any("缺少实际参数" in item for item in summaries))

    def test_rerun_replaces_auto_deviations_instead_of_duplicating(self):
        run = self._record(actual_parameters='{"batch_size": 32}')

        first = detect_run_deviations(self.pack, run.run_id)
        second = detect_run_deviations(self.pack, run.run_id)

        self.assertEqual([item.deviation_id for item in first], [item.deviation_id for item in second])
        self.assertEqual(len(self.pack.deviations), 1)
        matching_reviews = [
            item for item in self.pack.reviews if item.target_id == second[0].deviation_id
        ]
        self.assertEqual(len(matching_reviews), 1)


if __name__ == "__main__":
    unittest.main()
