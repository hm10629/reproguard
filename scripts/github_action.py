"""GitHub Action entry point for ReproGuard pull-request reviews."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ACTION_ROOT = Path(__file__).resolve().parents[1]
if str(ACTION_ROOT) not in sys.path:
    sys.path.insert(0, str(ACTION_ROOT))

from src.pr_review import main as review_main  # noqa: E402


COMMENT_MARKER = "<!-- reproguard-report -->"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub event payload must be a JSON object")
    return payload


def _event_pull_request(event: dict[str, Any]) -> dict[str, Any]:
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ValueError(
            "ReproGuard needs a pull_request event or the diff-path input for replay"
        )
    return pull_request


def _request(
    url: str,
    *,
    token: str,
    accept: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> bytes:
    data = None
    headers = {"Accept": accept, "User-Agent": "ReproGuard-GitHub-Action"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch_diff(event: dict[str, Any], token: str) -> str:
    pull_request = _event_pull_request(event)
    diff_url = pull_request.get("diff_url")
    if not isinstance(diff_url, str) or not diff_url.startswith(("https://", "http://")):
        raise ValueError("The pull_request event does not contain a valid diff_url")
    payload = _request(
        diff_url,
        token=token,
        accept="application/vnd.github.v3.diff",
    )
    return payload.decode("utf-8")


def _workspace_path(workspace: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def _is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _github_warning(message: str) -> None:
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::warning title=ReproGuard comment::{escaped}")


def _comment_endpoint(event: dict[str, Any]) -> str:
    repository = event.get("repository")
    pull_request = _event_pull_request(event)
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    number = pull_request.get("number")
    if not full_name or not isinstance(number, int):
        raise ValueError("The event does not identify a repository and pull request number")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    return f"{api_url}/repos/{full_name}/issues/{number}/comments"


def upsert_comment(event: dict[str, Any], token: str, markdown: str) -> None:
    if not token:
        _github_warning("GITHUB_TOKEN is unavailable; the report remains in the job summary.")
        return
    endpoint = _comment_endpoint(event)
    body = f"{COMMENT_MARKER}\n{markdown}"
    comments = json.loads(
        _request(
            endpoint,
            token=token,
            accept="application/vnd.github+json",
        ).decode("utf-8")
    )
    existing_url = ""
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, dict) and COMMENT_MARKER in str(comment.get("body", "")):
                existing_url = str(comment.get("url", ""))
                break
    if existing_url:
        _request(
            existing_url,
            token=token,
            accept="application/vnd.github+json",
            method="PATCH",
            payload={"body": body},
        )
        print("Updated the existing ReproGuard pull-request comment.")
    else:
        _request(
            endpoint,
            token=token,
            accept="application/vnd.github+json",
            method="POST",
            payload={"body": body},
        )
        print("Created the ReproGuard pull-request comment.")


def run() -> int:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    event_path_value = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    event = _read_json(Path(event_path_value)) if event_path_value else {}
    token = os.environ.get("GITHUB_TOKEN", "")

    diff_path_value = os.environ.get("REPROGUARD_DIFF_PATH", "").strip()
    if diff_path_value:
        diff_path = _workspace_path(workspace, diff_path_value)
        if not diff_path.is_file():
            raise FileNotFoundError(f"diff-path does not exist: {diff_path}")
    else:
        diff_text = fetch_diff(event, token)
        runner_temp = Path(os.environ.get("RUNNER_TEMP", workspace / ".reproguard-temp"))
        runner_temp.mkdir(parents=True, exist_ok=True)
        diff_path = runner_temp / "reproguard-pr.diff"
        diff_path.write_text(diff_text, encoding="utf-8")

    output = _workspace_path(
        workspace, os.environ.get("REPROGUARD_OUTPUT", "reproguard-report")
    )
    arguments = [
        "--diff",
        str(diff_path),
        "--output",
        str(output),
        "--format",
        "both",
        "--github-annotations",
        "--fail-on",
        os.environ.get("REPROGUARD_FAIL_ON", "never"),
        "--model-mode",
        os.environ.get("REPROGUARD_MODEL_MODE", "rules"),
        "--ollama-url",
        os.environ.get("REPROGUARD_OLLAMA_URL", "http://127.0.0.1:11434"),
        "--api-base-url",
        os.environ.get("REPROGUARD_API_BASE_URL", "https://api.deepseek.com/v1"),
    ]
    constraints = os.environ.get("REPROGUARD_CONSTRAINTS", "").strip()
    if constraints:
        arguments.extend(["--constraints", str(_workspace_path(workspace, constraints))])
    model_name = os.environ.get("REPROGUARD_MODEL_NAME", "").strip()
    if model_name:
        arguments.extend(["--model-name", model_name])

    result = review_main(arguments)
    report_path = output.with_suffix(".md")
    if (
        report_path.is_file()
        and event
        and _is_true(os.environ.get("REPROGUARD_POST_COMMENT", "true"))
    ):
        try:
            upsert_comment(event, token, report_path.read_text(encoding="utf-8"))
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            _github_warning(
                f"Could not publish the PR comment ({exc}); the report remains in the job summary."
            )
    return result


def main() -> int:
    try:
        return run()
    except (HTTPError, URLError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ReproGuard Action error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
