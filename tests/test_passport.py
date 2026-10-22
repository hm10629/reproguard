import json
from pathlib import Path
import unittest

from src.passport import (
    PassportValidationError,
    ReproductionPack,
    load_passport,
    passport_to_json,
    passport_to_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "examples" / "reproduction-passport-demo.json"


class PassportTests(unittest.TestCase):
    def test_demo_passport_loads_and_has_pending_human_review(self):
        pack = load_passport(DEMO)

        self.assertEqual(pack.schema_version, "0.1.0")
        self.assertEqual(pack.study.discipline, "机器学习")
        self.assertEqual(len(pack.deviations), 1)
        self.assertTrue(pack.deviations[0].requires_review)
        self.assertEqual(pack.reviews[0].decision, "pending")

    def test_json_round_trip_keeps_cross_source_evidence(self):
        pack = load_passport(DEMO)
        restored = ReproductionPack.from_dict(json.loads(passport_to_json(pack)))

        self.assertEqual(restored.pack_id, pack.pack_id)
        self.assertEqual(
            restored.deviations[0].evidence_ids,
            ["EV-PAPER-BATCH", "EV-CODE-BATCH"],
        )

    def test_unknown_evidence_reference_is_rejected(self):
        payload = json.loads(DEMO.read_text(encoding="utf-8"))
        payload["claims"][0]["evidence_ids"] = ["EV-NOT-FOUND"]

        with self.assertRaises(PassportValidationError) as context:
            ReproductionPack.from_dict(payload)

        self.assertIn("不存在的证据", str(context.exception))

    def test_unknown_protocol_step_in_run_is_rejected(self):
        payload = json.loads(DEMO.read_text(encoding="utf-8"))
        payload["runs"][0]["steps"][0]["step_id"] = "STEP-NOT-FOUND"

        with self.assertRaises(PassportValidationError) as context:
            ReproductionPack.from_dict(payload)

        self.assertIn("不存在的步骤", str(context.exception))

    def test_completed_review_requires_reviewer(self):
        payload = json.loads(DEMO.read_text(encoding="utf-8"))
        payload["reviews"][0]["decision"] = "accepted"

        with self.assertRaises(PassportValidationError) as context:
            ReproductionPack.from_dict(payload)

        self.assertIn("reviewer", str(context.exception))

    def test_markdown_exposes_deviation_and_review_disclaimer(self):
        markdown = passport_to_markdown(load_passport(DEMO))

        self.assertIn("论文与训练脚本的 batch size 不一致", markdown)
        self.assertIn("需要人工复核：是", markdown)
        self.assertIn("最终结论以人工复核记录为准", markdown)


if __name__ == "__main__":
    unittest.main()
