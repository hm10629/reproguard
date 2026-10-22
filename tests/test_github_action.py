import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "github_action.py"
SPEC = importlib.util.spec_from_file_location("reproguard_github_action", SCRIPT)
github_action = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(github_action)


class GitHubActionTests(unittest.TestCase):
    def test_entry_point_runs_outside_action_checkout(self):
        diff = """diff --git a/train.py b/train.py
--- a/train.py
+++ b/train.py
@@ -1 +1 @@
-learning_rate = 0.01
+learning_rate = 0.02
"""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "change.diff").write_text(diff, encoding="utf-8")
            github_output = workspace / "github-output.txt"
            environment = os.environ.copy()
            environment.update(
                {
                    "GITHUB_WORKSPACE": str(workspace),
                    "GITHUB_OUTPUT": str(github_output),
                    "REPROGUARD_DIFF_PATH": "change.diff",
                    "REPROGUARD_OUTPUT": "report",
                    "REPROGUARD_POST_COMMENT": "false",
                    "REPROGUARD_MODEL_MODE": "rules",
                }
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=workspace,
                env=environment,
                capture_output=True,
                check=False,
            )
            stderr = result.stderr.decode(errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            self.assertTrue((workspace / "report.json").is_file())
            self.assertTrue((workspace / "report.md").is_file())
            self.assertIn("finding-count=1", github_output.read_text(encoding="utf-8"))

    def test_fetch_diff_uses_event_url_and_diff_media_type(self):
        event = {"pull_request": {"diff_url": "https://example.test/pull/7.diff"}}
        with patch.object(github_action, "_request", return_value=b"diff --git a/a b/a") as request:
            result = github_action.fetch_diff(event, "token")
        self.assertEqual(result, "diff --git a/a b/a")
        request.assert_called_once_with(
            "https://example.test/pull/7.diff",
            token="token",
            accept="application/vnd.github.v3.diff",
        )

    def test_fetch_diff_rejects_non_pull_request_event(self):
        with self.assertRaisesRegex(ValueError, "pull_request"):
            github_action.fetch_diff({"push": {}}, "token")

    def test_upsert_comment_updates_existing_report(self):
        event = {
            "repository": {"full_name": "team/project"},
            "pull_request": {"number": 7},
        }
        comments = [
            {
                "url": "https://api.github.test/comments/9",
                "body": f"{github_action.COMMENT_MARKER}\nold",
            }
        ]
        with patch.object(
            github_action,
            "_request",
            side_effect=[json.dumps(comments).encode("utf-8"), b"{}"],
        ) as request, patch.dict(
            github_action.os.environ,
            {"GITHUB_API_URL": "https://api.github.test"},
            clear=False,
        ):
            github_action.upsert_comment(event, "token", "new report")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].args[0], "https://api.github.test/comments/9")
        self.assertEqual(request.call_args_list[1].kwargs["method"], "PATCH")
        self.assertIn(github_action.COMMENT_MARKER, request.call_args_list[1].kwargs["payload"]["body"])

    def test_boolean_input_is_strict(self):
        self.assertTrue(github_action._is_true("TRUE"))
        self.assertFalse(github_action._is_true("false"))
        self.assertFalse(github_action._is_true("anything"))


if __name__ == "__main__":
    unittest.main()
