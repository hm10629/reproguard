from pathlib import Path
import unittest

from src.passport import passport_to_markdown
from src.protocol_extract import create_passport_from_paper
from src.workflow import (
    WorkflowInputError,
    add_protocol_step,
    record_reproduction_run,
)


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "data" / "examples" / "incomplete-ml-project" / "paper.txt"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.pack, _ = create_passport_from_paper(PAPER)

    def test_manual_step_is_saved_with_pending_review(self):
        step = add_protocol_step(
            self.pack,
            title="准备样本",
            description="按照协议准备输入材料。",
            expected_parameters_json='{"温度": "25 C"}',
            source_location="协议第2页",
            evidence_content="在25 C条件下准备样本。",
        )

        self.assertEqual(step.step_id, "STEP-001")
        self.assertEqual(self.pack.protocol_steps[0].expected_parameters["温度"], "25 C")
        self.assertEqual(self.pack.evidence[0].verification_level, "user_supplied")
        self.assertEqual(self.pack.evidence[0].status, "needs_review")
        self.assertEqual(self.pack.reviews[-1].decision, "pending")

    def test_run_and_result_are_exported_without_becoming_confirmed(self):
        step = add_protocol_step(self.pack, title="执行实验")

        run = record_reproduction_run(
            self.pack,
            title="第一次复现",
            status="completed",
            environment_json='{"设备": "演示设备"}',
            step_entries=[
                {
                    "step_id": step.step_id,
                    "status": "completed",
                    "actual_parameters_json": '{"温度": 24}',
                    "notes": "完成。",
                    "source_location": "实验记录第1页",
                    "evidence_content": "记录温度为24。",
                }
            ],
            result={
                "name": "产率",
                "value": "81",
                "expected_value": "85",
                "unit": "%",
                "source_location": "结果表A1",
                "evidence_content": "本次产率81%。",
            },
        )

        self.assertEqual(run.run_id, "RUN-001")
        self.assertEqual(self.pack.results[0].status, "needs_review")
        self.assertTrue(all(item.decision == "pending" for item in self.pack.reviews))
        markdown = passport_to_markdown(self.pack)
        self.assertIn("## 实际复现过程", markdown)
        self.assertIn("第一次复现", markdown)
        self.assertIn("产率", markdown)

    def test_invalid_later_step_does_not_partially_mutate_pack(self):
        step = add_protocol_step(self.pack, title="执行实验")
        evidence_count = len(self.pack.evidence)

        with self.assertRaises(WorkflowInputError):
            record_reproduction_run(
                self.pack,
                title="错误记录",
                status="completed",
                step_entries=[
                    {
                        "step_id": step.step_id,
                        "status": "completed",
                        "source_location": "记录1",
                        "evidence_content": "内容1",
                    },
                    {"step_id": "STEP-NOT-FOUND", "status": "completed"},
                ],
            )

        self.assertEqual(self.pack.runs, [])
        self.assertEqual(len(self.pack.evidence), evidence_count)

    def test_json_fields_must_be_objects(self):
        with self.assertRaisesRegex(WorkflowInputError, "JSON 对象"):
            add_protocol_step(
                self.pack,
                title="错误步骤",
                expected_parameters_json="[1, 2]",
            )


if __name__ == "__main__":
    unittest.main()
