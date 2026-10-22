import json
from http.client import HTTPConnection
from pathlib import Path
import threading
import unittest
from urllib.parse import urlencode

from src import web
from src.analyzer import summarize
from src.models import Finding, Report


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"


class WebEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = web.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            web.AnalysisHandler,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            name="web-test-server",
            daemon=True,
        )
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        with web.STATE.lock:
            web.STATE.report = None
            web.STATE.passport = None
            web.STATE.extraction = None
            web.STATE.error = ""

    def request(self, method, path, form=None):
        body = None
        headers = {}
        if form is not None:
            body = urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection = HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def analyze_sample(self):
        return self.request(
            "POST",
            "/analyze",
            {
                "paper": str(SAMPLE / "paper.txt"),
                "repo": str(SAMPLE / "repository"),
            },
        )

    def test_home_get_returns_chinese_form(self):
        status, headers, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html; charset=utf-8"))
        page = body.decode("utf-8")
        self.assertIn('<html lang="zh-CN">', page)
        self.assertIn("科研复现证据链", page)
        self.assertIn('<form method="post" action="/create-passport">', page)
        self.assertIn('action="/analyze"', page)

    def test_paper_only_creates_manual_passport(self):
        status, headers, body = self.request(
            "POST",
            "/create-passport",
            {
                "paper": str(SAMPLE / "paper.txt"),
                "model_mode": "manual",
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html; charset=utf-8"))
        page = body.decode("utf-8")
        self.assertIn("复现档案", page)
        self.assertIn("手工骨架", page)
        self.assertIn("待人工复核", page)
        self.assertNotIn("代码仓库路径", page)

    def test_passport_download_returns_valid_json(self):
        status, _, _ = self.request(
            "POST",
            "/create-passport",
            {"paper": str(SAMPLE / "paper.txt"), "model_mode": "manual"},
        )
        self.assertEqual(status, 200)

        status, headers, body = self.request("GET", "/download/passport-json")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["schema_version"], "0.1.0")
        self.assertTrue(data["pack_id"].startswith("PACK-"))
        self.assertEqual(data["reviews"][0]["decision"], "pending")

    def test_manual_step_and_actual_run_are_saved_to_passport(self):
        status, _, _ = self.request(
            "POST",
            "/create-passport",
            {"paper": str(SAMPLE / "paper.txt"), "model_mode": "manual"},
        )
        self.assertEqual(status, 200)

        status, _, body = self.request(
            "POST",
            "/add-step",
            {
                "title": "运行训练",
                "description": "按照论文参数训练。",
                "expected_parameters": '{"batch_size": 64}',
                "source_location": "paper.txt:7",
                "evidence_content": "batch size 64",
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("STEP-001", body.decode("utf-8"))

        status, _, body = self.request("GET", "/record-run")
        self.assertEqual(status, 200)
        self.assertIn("记录一次复现运行", body.decode("utf-8"))

        status, _, body = self.request(
            "POST",
            "/save-run",
            {
                "title": "演示运行",
                "status": "completed",
                "environment": '{"mode": "demo"}',
                "step_id": "STEP-001",
                "status_STEP-001": "completed",
                "actual_parameters_STEP-001": '{"batch_size": 32}',
                "notes_STEP-001": "因资源限制调整参数。",
                "evidence_location_STEP-001": "run.log:1",
                "evidence_content_STEP-001": "batch_size=32",
                "result_name": "准确率",
                "result_value": "0.91",
                "result_expected_value": "0.93",
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("实际运行", body.decode("utf-8"))

        status, _, body = self.request("POST", "/check-deviations", {})
        self.assertEqual(status, 200)
        self.assertIn("参数不一致", body.decode("utf-8"))

        with web.STATE.lock:
            deviation_review = next(
                item
                for item in web.STATE.passport.reviews
                if item.target_type == "deviation"
            )
        status, _, body = self.request(
            "POST",
            "/review",
            {
                "review_id": deviation_review.review_id,
                "decision": "accepted",
                "reviewer": "测试复核人",
                "note": "已人工比对参数记录。",
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("完成人工复核", body.decode("utf-8"))

        status, _, body = self.request("GET", "/download/passport-json")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["runs"][0]["steps"][0]["status"], "completed")
        self.assertEqual(data["results"][0]["status"], "needs_review")
        self.assertEqual(data["runs"][0]["steps"][0]["actual_parameters"]["batch_size"], 32)
        self.assertEqual(data["deviations"][0]["status"], "accepted")
        reviewed = next(
            item for item in data["reviews"] if item["review_id"] == deviation_review.review_id
        )
        self.assertEqual(reviewed["reviewer"], "测试复核人")

    def test_normal_analyze_post_returns_report_page(self):
        status, headers, body = self.analyze_sample()

        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html; charset=utf-8"))
        page = body.decode("utf-8")
        self.assertIn("体检报告：repository", page)
        self.assertIn("R001", page)
        self.assertIn("下载 JSON", page)
        self.assertIn("下载 Markdown", page)

    def test_invalid_analyze_input_returns_error_response(self):
        missing_paper = ROOT / "data" / "missing-paper.txt"
        status, headers, body = self.request(
            "POST",
            "/analyze",
            {
                "paper": str(missing_paper),
                "repo": str(SAMPLE / "repository"),
            },
        )

        self.assertEqual(status, 400)
        self.assertTrue(headers["Content-Type"].startswith("text/html; charset=utf-8"))
        page = body.decode("utf-8")
        self.assertIn("论文路径不存在", page)
        self.assertIn(str(missing_paper), page)

    def test_json_download_returns_current_report(self):
        status, _, _ = self.analyze_sample()
        self.assertEqual(status, 200)

        status, headers, body = self.request("GET", "/download/json")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertIn('attachment; filename="reprocheck-report.json"', headers["Content-Disposition"])
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["project_name"], "repository")
        self.assertEqual(data["summary"]["total_findings"], 15)
        self.assertTrue(data["summary"]["action_items"])

    def test_markdown_download_returns_current_report(self):
        status, _, _ = self.analyze_sample()
        self.assertEqual(status, 200)

        status, headers, body = self.request("GET", "/download/markdown")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/markdown; charset=utf-8")
        self.assertIn('attachment; filename="reprocheck-report.md"', headers["Content-Disposition"])
        markdown = body.decode("utf-8")
        self.assertTrue(markdown.startswith("# 科研复现体检报告：repository"))
        self.assertIn("R001", markdown)

    def test_result_page_shows_action_items(self):
        status, _, body = self.analyze_sample()

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertIn("待修复任务", page)
        first = web.STATE.report.summary["action_items"][0]
        self.assertIn(first["task_id"], page)
        self.assertIn(first["rule_id"], page)
        self.assertIn(first["action"], page)

    def test_result_page_escapes_action_item_fields(self):
        findings = [
            Finding(
                rule_id="R002",
                title="<script>alert(1)</script>",
                status="missing",
                severity="high",
                finding="缺失。",
                suggestion="<b>注入</b>",
            )
        ]
        report = Report(
            project_name="demo",
            paper_path="paper.txt",
            repository_path="repository",
            findings=findings,
            summary=summarize(findings),
        )

        page = web._result_page(report).decode("utf-8")

        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<b>注入</b>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;b&gt;", page)

    def test_result_page_states_when_no_action_items(self):
        findings = [
            Finding(
                rule_id="R001",
                title="是否存在项目说明文档",
                status="found",
                severity="medium",
                finding="找到说明文档。",
            )
        ]
        report = Report(
            project_name="demo",
            paper_path="paper.txt",
            repository_path="repository",
            findings=findings,
            summary=summarize(findings),
        )

        page = web._result_page(report).decode("utf-8")

        self.assertIn("本次检查未发现待修复任务。", page)

    def test_home_form_offers_model_mode(self):
        status, _, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertIn('name="model_mode"', page)
        self.assertIn('value="ollama"', page)
        self.assertIn('value="deepseek"', page)
        self.assertIn('name="api_key_env"', page)

    def test_deepseek_mode_without_key_becomes_pending_manual_work(self):
        status, _, body = self.request(
            "POST",
            "/create-passport",
            {
                "paper": str(SAMPLE / "paper.txt"),
                "model_mode": "deepseek",
                "api_key_env": "REPROCHECK_MISSING_WEB_TEST_KEY",
            },
        )

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertIn("模型不可用", page)
        self.assertIn("REPROCHECK_MISSING_WEB_TEST_KEY", page)
        self.assertIn("待人工复核", page)

    def test_ollama_mode_without_service_reports_unavailable(self):
        status, _, body = self.request(
            "POST",
            "/analyze",
            {
                "paper": str(SAMPLE / "paper.txt"),
                "repo": str(SAMPLE / "repository"),
                "model_mode": "ollama",
                "model_name": "stub-model",
                "ollama_url": "http://127.0.0.1:1",
            },
        )

        self.assertEqual(status, 200)
        page = body.decode("utf-8")
        self.assertIn("模型辅助结果", page)
        self.assertIn("模型不可用", page)


if __name__ == "__main__":
    unittest.main()
