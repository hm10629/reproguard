"""Tests for the optional local open-model assistance adapter.

Every test runs against an in-process stub HTTP server, so no real network
access and no local Ollama installation are required.
"""

from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from src.analyzer import analyze
from src.cli import main as cli_main
from src.model_assist import (
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    ModelAssistError,
    ModelConfig,
    OllamaClient,
    OpenAICompatibleClient,
    PROVIDER_OPENAI_COMPATIBLE,
    build_model_client,
    build_prompt,
    build_source_index,
    run_model_assistance,
    sanitize_model_output,
)
from src.paper_extract import load_paper
from src.repository_scan import scan_repository


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "examples" / "incomplete-ml-project"


class StubOllamaServer:
    """In-process HTTP server that mimics the Ollama ``/api/generate`` shape."""

    def __init__(self, *, model_payload=None, status=200, raw_content=None):
        self.model_payload = model_payload
        self.status = status
        self.raw_content = raw_content
        self.base_url = ""
        self.last_request = None
        self._httpd = None
        self._thread = None

    def __enter__(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    outer.last_request = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    outer.last_request = None
                if outer.raw_content is not None:
                    body = outer.raw_content
                else:
                    body = json.dumps(
                        {"response": json.dumps(outer.model_payload)}
                    ).encode("utf-8")
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="stub-ollama", daemon=True
        )
        self._thread.start()
        host, port = self._httpd.server_address
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc_info):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)
        return False


class StubOpenAICompatibleServer:
    """In-process server for the ``/chat/completions`` response shape."""

    def __init__(self, *, model_payload=None, status=200, raw_content=None):
        self.model_payload = model_payload
        self.status = status
        self.raw_content = raw_content
        self.base_url = ""
        self.last_request = None
        self.last_authorization = ""
        self.last_path = ""
        self._httpd = None
        self._thread = None

    def __enter__(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.last_path = self.path
                outer.last_authorization = self.headers.get("Authorization", "")
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                outer.last_request = json.loads(raw.decode("utf-8"))
                if outer.raw_content is not None:
                    body = outer.raw_content
                else:
                    body = json.dumps(
                        {
                            "choices": [
                                {
                                    "message": {
                                        "content": json.dumps(outer.model_payload)
                                    }
                                }
                            ]
                        }
                    ).encode("utf-8")
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="stub-openai", daemon=True
        )
        self._thread.start()
        _, port = self._httpd.server_address
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc_info):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)
        return False


class SourceIndexTests(unittest.TestCase):
    def setUp(self):
        self.paper = load_paper(SAMPLE / "paper.txt")
        self.repository = scan_repository(SAMPLE / "repository")

    def test_refs_are_unique_and_avoid_rule_prefix(self):
        entries = build_source_index(self.paper, self.repository)
        refs = [item.ref for item in entries]

        self.assertTrue(refs)
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(any(ref.startswith("P") for ref in refs))
        self.assertTrue(any(ref.startswith("F") for ref in refs))
        # The R prefix stays reserved for R001-R015 rule ids.
        self.assertFalse(any(ref.startswith("R") for ref in refs))

    def test_prompt_lists_each_source_ref(self):
        entries = build_source_index(self.paper, self.repository)
        prompt = build_prompt(entries)

        for item in entries:
            self.assertIn(f"[{item.ref}]", prompt)


class SanitizeTests(unittest.TestCase):
    def test_valid_payload_is_kept(self):
        payload = {
            "experiment_elements": [
                {"name": "数据集", "value": "MNIST", "source_refs": ["P001"]}
            ],
            "review_notes": ["确认数据划分"],
            "source_refs": ["P001", "F002"],
        }

        elements, notes, refs, dropped = sanitize_model_output(
            payload, {"P001", "F002"}
        )

        self.assertEqual([item["name"] for item in elements], ["数据集"])
        self.assertEqual(elements[0]["source_refs"], ["P001"])
        self.assertEqual(notes, ["确认数据划分"])
        self.assertEqual(refs, ["P001", "F002"])
        self.assertEqual(dropped, [])

    def test_unknown_refs_are_dropped(self):
        payload = {
            "experiment_elements": [
                {"name": "模型", "value": "ResNet", "source_refs": ["P999"]}
            ],
            "source_refs": ["P999", "P001"],
        }

        elements, _, refs, dropped = sanitize_model_output(payload, {"P001"})

        # The element loses every trusted source, so it is discarded rather
        # than reported with fabricated evidence.
        self.assertEqual(elements, [])
        self.assertEqual(refs, ["P001"])
        self.assertEqual(dropped, ["P999"])

    def test_element_without_name_is_skipped(self):
        payload = {"experiment_elements": [{"value": "x", "source_refs": ["P001"]}]}

        elements, _, _, _ = sanitize_model_output(payload, {"P001"})

        self.assertEqual(elements, [])

    def test_malformed_payload_yields_empty_result(self):
        payload = {
            "experiment_elements": "not-a-list",
            "review_notes": {"a": 1},
            "source_refs": None,
        }

        result = sanitize_model_output(payload, {"P001"})

        self.assertEqual(result, ([], [], [], []))


class OllamaClientTests(unittest.TestCase):
    def test_parses_structured_response(self):
        payload = {"experiment_elements": [], "review_notes": ["核对种子"]}

        with StubOllamaServer(model_payload=payload) as server:
            client = OllamaClient(server.base_url, "stub-model", 5.0)
            parsed = client.generate_json("hello")

        self.assertEqual(parsed["review_notes"], ["核对种子"])

    def test_request_serialises_expected_options(self):
        with StubOllamaServer(model_payload={"review_notes": []}) as server:
            client = OllamaClient(server.base_url, "stub-model", 5.0)
            client.generate_json("hello")
            sent = server.last_request

        self.assertEqual(sent["model"], "stub-model")
        self.assertFalse(sent["stream"])
        self.assertEqual(sent["format"], "json")
        self.assertEqual(sent["options"]["temperature"], 0.0)

    def test_raises_on_invalid_inner_json(self):
        with StubOllamaServer(raw_content=b'{"response": "not-json"}') as server:
            client = OllamaClient(server.base_url, "stub-model", 5.0)
            with self.assertRaises(ModelAssistError):
                client.generate_json("hello")

    def test_raises_on_http_error(self):
        with StubOllamaServer(status=500, raw_content=b"boom") as server:
            client = OllamaClient(server.base_url, "stub-model", 5.0)
            with self.assertRaises(ModelAssistError):
                client.generate_json("hello")

    def test_raises_when_service_is_missing(self):
        client = OllamaClient("http://127.0.0.1:1", "stub-model", 1.0)
        with self.assertRaises(ModelAssistError):
            client.generate_json("hello")


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_parses_chat_completion_and_sends_bearer_key(self):
        payload = {"experiment_elements": [], "review_notes": ["人工确认"]}

        with StubOpenAICompatibleServer(model_payload=payload) as server:
            client = OpenAICompatibleClient(
                server.base_url, "deepseek-chat", "test-secret", 5.0
            )
            parsed = client.generate_json("hello")

        self.assertEqual(parsed, payload)
        self.assertEqual(server.last_path, "/chat/completions")
        self.assertEqual(server.last_authorization, "Bearer test-secret")
        self.assertEqual(server.last_request["model"], "deepseek-chat")
        self.assertEqual(
            server.last_request["response_format"], {"type": "json_object"}
        )

    def test_invalid_chat_completion_shape_is_rejected(self):
        with StubOpenAICompatibleServer(raw_content=b'{"choices": []}') as server:
            client = OpenAICompatibleClient(server.base_url, "model", "key", 5.0)
            with self.assertRaises(ModelAssistError):
                client.generate_json("hello")

    def test_provider_reads_key_from_named_environment_variable(self):
        config = ModelConfig(
            enabled=True,
            provider=PROVIDER_OPENAI_COMPATIBLE,
            base_url="https://example.invalid",
            model_name="deepseek-chat",
            api_key_env="REPROCHECK_TEST_KEY",
        )

        client = build_model_client(
            config, environ={"REPROCHECK_TEST_KEY": "secret-from-env"}
        )

        self.assertIsInstance(client, OpenAICompatibleClient)
        self.assertEqual(client.api_key, "secret-from-env")

    def test_provider_rejects_missing_environment_variable(self):
        config = ModelConfig(
            enabled=True,
            provider=PROVIDER_OPENAI_COMPATIBLE,
            api_key_env="REPROCHECK_MISSING_TEST_KEY",
        )

        with self.assertRaisesRegex(ModelAssistError, "REPROCHECK_MISSING_TEST_KEY"):
            build_model_client(config, environ={})


class RunModelAssistanceTests(unittest.TestCase):
    def setUp(self):
        self.paper = load_paper(SAMPLE / "paper.txt")
        self.repository = scan_repository(SAMPLE / "repository")

    def test_unavailable_service_returns_status_not_exception(self):
        config = ModelConfig(enabled=True, base_url="http://127.0.0.1:1", timeout=1.0)

        result = run_model_assistance(self.paper, self.repository, config)

        self.assertEqual(result.status, STATUS_UNAVAILABLE)
        self.assertTrue(result.message)

    def test_valid_response_returns_ok(self):
        payload = {
            "experiment_elements": [
                {"name": "随机种子", "value": "42", "source_refs": ["P001"]}
            ],
            "review_notes": ["人工确认数据集版本"],
            "source_refs": ["P001"],
        }

        with StubOllamaServer(model_payload=payload) as server:
            config = ModelConfig(
                enabled=True,
                base_url=server.base_url,
                model_name="stub-model",
                timeout=5.0,
            )
            result = run_model_assistance(self.paper, self.repository, config)

        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.experiment_elements[0]["name"], "随机种子")
        self.assertEqual(result.review_notes, ["人工确认数据集版本"])

    def test_missing_fields_return_invalid_status(self):
        with StubOllamaServer(model_payload={"unexpected": []}) as server:
            config = ModelConfig(
                enabled=True, base_url=server.base_url, timeout=5.0
            )
            result = run_model_assistance(self.paper, self.repository, config)

        self.assertEqual(result.status, STATUS_INVALID)

    def test_openai_compatible_provider_uses_same_source_guardrails(self):
        payload = {
            "experiment_elements": [
                {"name": "数据集", "value": "可信", "source_refs": ["P001"]},
                {"name": "编造项", "value": "x", "source_refs": ["P999"]},
            ],
            "review_notes": ["人工确认"],
            "source_refs": ["P001", "P999"],
        }
        with StubOpenAICompatibleServer(model_payload=payload) as server:
            config = ModelConfig(
                enabled=True,
                provider=PROVIDER_OPENAI_COMPATIBLE,
                base_url=server.base_url,
                model_name="deepseek-chat",
                api_key_env="REPROCHECK_TEST_KEY",
                timeout=5.0,
            )
            with patch.dict("os.environ", {"REPROCHECK_TEST_KEY": "secret"}):
                result = run_model_assistance(self.paper, self.repository, config)

        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual([item["name"] for item in result.experiment_elements], ["数据集"])
        self.assertEqual(result.dropped_source_refs, ["P999"])


class AnalyzeModelModeTests(unittest.TestCase):
    def test_default_mode_has_no_model_block(self):
        report = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")

        self.assertIsNone(report.model_assistance)
        self.assertNotIn("model_assistance", report.to_dict())

    def test_disabled_config_keeps_rules_only_output(self):
        report = analyze(
            SAMPLE / "paper.txt",
            SAMPLE / "repository",
            model_config=ModelConfig(enabled=False),
        )

        self.assertIsNone(report.model_assistance)

    def test_enabled_config_adds_block_without_changing_findings(self):
        baseline = analyze(SAMPLE / "paper.txt", SAMPLE / "repository")
        payload = {
            "experiment_elements": [
                {"name": "数据集", "value": "MNIST", "source_refs": ["P001"]}
            ],
            "review_notes": ["人工确认"],
            "source_refs": ["P001"],
        }

        with StubOllamaServer(model_payload=payload) as server:
            report = analyze(
                SAMPLE / "paper.txt",
                SAMPLE / "repository",
                model_config=ModelConfig(
                    enabled=True, base_url=server.base_url, timeout=5.0
                ),
            )

        self.assertIsNotNone(report.model_assistance)
        self.assertEqual(report.model_assistance["status"], STATUS_OK)
        # The rule verdicts must stay byte-identical to the rules-only run.
        self.assertEqual(
            [finding.to_dict() for finding in report.findings],
            [finding.to_dict() for finding in baseline.findings],
        )
        self.assertEqual(report.summary, baseline.summary)

    def test_unavailable_model_does_not_break_report(self):
        report = analyze(
            SAMPLE / "paper.txt",
            SAMPLE / "repository",
            model_config=ModelConfig(
                enabled=True, base_url="http://127.0.0.1:1", timeout=1.0
            ),
        )

        self.assertEqual(len(report.findings), 15)
        self.assertEqual(report.model_assistance["status"], STATUS_UNAVAILABLE)


class CliModelModeTests(unittest.TestCase):
    def _run(self, extra_args):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli_main(extra_args)
        return code, buffer.getvalue()

    def test_default_cli_writes_rules_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report"
            code, _ = self._run(
                [
                    "--paper",
                    str(SAMPLE / "paper.txt"),
                    "--repo",
                    str(SAMPLE / "repository"),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(code, 0)
            data = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

        self.assertNotIn("model_assistance", data)

    def test_ollama_cli_records_model_status(self):
        payload = {
            "experiment_elements": [],
            "review_notes": ["x"],
            "source_refs": [],
        }

        with StubOllamaServer(model_payload=payload) as server:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "report"
                code, stdout = self._run(
                    [
                        "--paper",
                        str(SAMPLE / "paper.txt"),
                        "--repo",
                        str(SAMPLE / "repository"),
                        "--output",
                        str(output),
                        "--model-mode",
                        "ollama",
                        "--model-name",
                        "stub-model",
                        "--ollama-url",
                        server.base_url,
                    ]
                )
                data = json.loads(
                    output.with_suffix(".json").read_text(encoding="utf-8")
                )

        self.assertEqual(code, 0)
        self.assertEqual(data["model_assistance"]["status"], STATUS_OK)
        self.assertEqual(data["model_assistance"]["model"], "stub-model")
        self.assertIn("模型辅助", stdout)


if __name__ == "__main__":
    unittest.main()
