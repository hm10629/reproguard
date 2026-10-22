import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.model_assist import ModelConfig
from src.paper_extract import load_paper
from src.protocol_extract import (
    STATUS_INVALID,
    STATUS_MANUAL,
    STATUS_OK,
    build_paper_source_index,
    create_passport_from_paper,
    run_protocol_extraction,
    sanitize_protocol_output,
)


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "data" / "examples" / "incomplete-ml-project" / "paper.txt"


class ProtocolExtractionTests(unittest.TestCase):
    def test_paper_source_index_is_stable_and_page_aware(self):
        paper = load_paper(PAPER)
        first = build_paper_source_index(paper)
        second = build_paper_source_index(paper)

        self.assertEqual(first, second)
        self.assertEqual(first[0].ref, "P001")
        self.assertIn("第 1 页", first[0].location)

    def test_manual_mode_creates_valid_empty_pack_with_pending_review(self):
        pack, extraction = create_passport_from_paper(PAPER)

        self.assertEqual(extraction.status, STATUS_MANUAL)
        self.assertEqual(pack.protocol_steps, [])
        self.assertEqual(pack.claims, [])
        self.assertEqual(pack.reviews[0].decision, "pending")
        self.assertIn("人工", pack.reviews[0].note)

    def test_sanitizer_drops_items_with_fabricated_refs(self):
        extraction = sanitize_protocol_output(
            {
                "study": {"title": "x", "source_refs": ["P001"]},
                "claims": [
                    {"text": "可信", "source_refs": ["P001"]},
                    {"text": "不可信", "source_refs": ["P999"]},
                ],
                "protocol_steps": [],
                "review_notes": [],
            },
            {"P001"},
        )

        self.assertEqual([item["text"] for item in extraction.claims], ["可信"])
        self.assertEqual(extraction.dropped_source_refs, ["P999"])

    def test_model_output_becomes_cited_pending_records(self):
        payload = {
            "study": {
                "title": "CIFAR-10 分类实验",
                "discipline": "机器学习",
                "summary": "训练分类模型。",
                "source_refs": ["P001"],
            },
            "claims": [
                {"text": "报告测试准确率。", "source_refs": ["P002"]}
            ],
            "protocol_steps": [
                {
                    "title": "训练模型",
                    "description": "运行训练入口。",
                    "expected_parameters": {"batch_size": 64},
                    "source_refs": ["P003"],
                }
            ],
            "review_notes": ["确认数据划分"],
        }
        config = ModelConfig(enabled=True)

        with patch("src.model_assist.OllamaClient.generate_json", return_value=payload):
            pack, extraction = create_passport_from_paper(PAPER, model_config=config)

        self.assertEqual(extraction.status, STATUS_OK)
        self.assertEqual(pack.study.title, "CIFAR-10 分类实验")
        self.assertEqual(pack.claims[0].status, "needs_review")
        self.assertEqual(pack.evidence[0].verification_level, "machine_extracted")
        self.assertTrue(all(review.decision == "pending" for review in pack.reviews))
        self.assertGreaterEqual(len(pack.reviews), 3)

    def test_all_unsupported_refs_produce_invalid_extraction(self):
        paper = load_paper(PAPER)
        payload = {
            "study": {"title": "x", "source_refs": ["P999"]},
            "claims": [],
            "protocol_steps": [],
            "review_notes": [],
        }

        with patch("src.model_assist.OllamaClient.generate_json", return_value=payload):
            extraction, _ = run_protocol_extraction(paper, ModelConfig(enabled=True))

        self.assertEqual(extraction.status, STATUS_INVALID)


if __name__ == "__main__":
    unittest.main()
