from pathlib import Path
import unittest

from src.passport import load_passport
from src.review_workflow import ReviewInputError, apply_review_decision


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "examples" / "reproduction-passport-demo.json"


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_passport(DEMO)

    def test_accepting_deviation_records_reviewer_and_closes_review(self):
        review = apply_review_decision(
            self.pack,
            review_id="REVIEW-DEV-BATCH",
            decision="accepted",
            reviewer="张同学",
            note="已核对论文与运行配置。",
        )

        self.assertEqual(review.decision, "accepted")
        self.assertEqual(review.reviewer, "张同学")
        self.assertTrue(review.reviewed_at)
        self.assertEqual(self.pack.deviations[0].status, "accepted")
        self.assertFalse(self.pack.deviations[0].requires_review)

    def test_rejecting_deviation_requires_and_records_reason(self):
        review = apply_review_decision(
            self.pack,
            review_id="REVIEW-DEV-BATCH",
            decision="rejected",
            reviewer="李同学",
            note="论文附件说明该参数可按显存调整。",
        )

        self.assertEqual(review.decision, "rejected")
        self.assertEqual(self.pack.deviations[0].status, "explained")
        self.assertIn("不成立", self.pack.deviations[0].explanation)

    def test_reviewer_is_required(self):
        with self.assertRaisesRegex(ReviewInputError, "复核人"):
            apply_review_decision(
                self.pack,
                review_id="REVIEW-DEV-BATCH",
                decision="accepted",
                reviewer="",
            )

        self.assertEqual(self.pack.reviews[0].decision, "pending")

    def test_rejected_or_revised_decision_requires_note(self):
        with self.assertRaisesRegex(ReviewInputError, "必须填写说明"):
            apply_review_decision(
                self.pack,
                review_id="REVIEW-DEV-BATCH",
                decision="revised",
                reviewer="王同学",
                note="",
            )


if __name__ == "__main__":
    unittest.main()
