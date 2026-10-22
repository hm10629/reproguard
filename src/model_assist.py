"""Optional source-grounded model assistance for the reproducibility checker.

The rules engine stays authoritative. This module only asks a locally hosted
model (through a local Ollama or OpenAI-compatible endpoint) to extract experiment
elements, normalise synonyms, and flag items for human review. It never writes
evidence and never changes a Finding verdict, status, severity or suggestion.

Only the Python standard library is used, so the default rule mode keeps
working offline without any new dependency.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Protocol

from .paper_extract import PaperDocument
from .repository_scan import RepositorySnapshot


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL_NAME = "qwen2.5:3b"
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com"
DEFAULT_OPENAI_MODEL_NAME = "deepseek-chat"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_PAPER_LINES = 200
DEFAULT_MAX_REPOSITORY_LINES = 200
MAX_SOURCE_TEXT = 280

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INVALID = "invalid_response"

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"

LOCAL_SETUP_HINT = (
    "本机未检测到可用的本地模型服务。安装并启动 Ollama 后运行 "
    "`ollama run qwen2.5:3b`，再用 --model-mode ollama 重新检查；"
    "不安装模型时，规则模式仍可离线使用"
)


class ModelAssistError(RuntimeError):
    """Raised when the local model endpoint fails or returns unusable data."""


@dataclass(frozen=True)
class ModelConfig:
    """Optional model settings. Disabled by default.

    API keys are referenced by environment-variable name and are never stored
    in reports or exported reproduction packs.
    """

    enabled: bool = False
    provider: str = PROVIDER_OLLAMA
    base_url: str = DEFAULT_BASE_URL
    model_name: str = DEFAULT_MODEL_NAME
    timeout: float = DEFAULT_TIMEOUT
    api_key_env: str = DEFAULT_API_KEY_ENV


@dataclass(frozen=True)
class SourceLine:
    """One addressable paper or repository line with a stable source id."""

    ref: str
    origin: str
    location: str
    text: str


@dataclass
class ModelAssistance:
    """Auxiliary model output attached to a report. Never authoritative."""

    provider: str = "ollama"
    model: str = ""
    base_url: str = ""
    status: str = STATUS_OK
    experiment_elements: list[dict[str, Any]] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    dropped_source_refs: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "status": self.status,
            "experiment_elements": [dict(item) for item in self.experiment_elements],
            "review_notes": list(self.review_notes),
            "source_refs": list(self.source_refs),
            "dropped_source_refs": list(self.dropped_source_refs),
            "message": self.message,
        }


def build_source_index(
    paper: PaperDocument,
    repository: RepositorySnapshot,
    *,
    max_paper_lines: int = DEFAULT_MAX_PAPER_LINES,
    max_repository_lines: int = DEFAULT_MAX_REPOSITORY_LINES,
) -> list[SourceLine]:
    """Give every paper and repository line a stable, non-colliding source id.

    Paper lines use the ``P`` prefix and repository lines use the ``F`` prefix.
    The ``R`` prefix is avoided on purpose: ``R001``-``R015`` already name the
    fifteen deterministic rules, so sharing it would make model citations
    ambiguous with rule ids.
    """

    entries: list[SourceLine] = []

    paper_count = 0
    for page, line_number, line in paper.iter_lines():
        if paper_count >= max_paper_lines:
            break
        text = line.strip()
        if not text:
            continue
        paper_count += 1
        entries.append(
            SourceLine(
                ref=f"P{paper_count:03d}",
                origin="paper",
                location=f"论文第 {page.page} 页 第 {line_number} 行",
                text=text[:MAX_SOURCE_TEXT],
            )
        )

    repo_count = 0
    for item in repository.files:
        if repo_count >= max_repository_lines:
            break
        for line_number, line in enumerate(item.lines, start=1):
            text = line.strip()
            if not text:
                continue
            repo_count += 1
            entries.append(
                SourceLine(
                    ref=f"F{repo_count:03d}",
                    origin="repository",
                    location=f"{item.relative_path}:{line_number}",
                    text=text[:MAX_SOURCE_TEXT],
                )
            )
            if repo_count >= max_repository_lines:
                break

    return entries


PROMPT_TEMPLATE = """你是科研复现检查的辅助抽取器。下面的来源行都带编号：论文行以 P 开头，仓库文件行以 F 开头。

请只依据这些来源，抽取实验要素、给出人工复核提示，并列出你实际引用的来源编号。

只输出 JSON，不要输出任何解释文字。JSON 结构必须是：
{{
  "experiment_elements": [
    {{"name": "要素名", "value": "取值或描述", "source_refs": ["P001"]}}
  ],
  "review_notes": ["需要人工确认的事项"],
  "source_refs": ["P001", "F003"]
}}

规则：
1. source_refs 只能使用下面出现过的编号，不得编造或推断新编号。
2. 找不到依据的要素不要输出，不要猜测。
3. review_notes 写需要人工核对的地方，例如同名不同指的术语。

来源行：
{context}
"""


def build_prompt(source_lines: list[SourceLine]) -> str:
    context = "\n".join(
        f"[{item.ref}] {item.location} | {item.text}" for item in source_lines
    )
    return PROMPT_TEMPLATE.format(context=context)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def sanitize_model_output(
    payload: dict[str, Any],
    allowed_refs: set[str],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """Keep only well-formed fields whose source refs are in the whitelist.

    Returns ``(experiment_elements, review_notes, source_refs, dropped_refs)``.
    Elements without a single trusted source are dropped instead of being
    reported with fabricated evidence.
    """

    dropped: list[str] = []

    def clean_refs(value: Any) -> list[str]:
        cleaned: list[str] = []
        for ref in _string_list(value):
            if ref in allowed_refs:
                if ref not in cleaned:
                    cleaned.append(ref)
            elif ref not in dropped:
                dropped.append(ref)
        return cleaned

    elements: list[dict[str, Any]] = []
    raw_elements = payload.get("experiment_elements")
    if isinstance(raw_elements, list):
        for item in raw_elements:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            value = item.get("value")
            value_text = value.strip() if isinstance(value, str) else ""
            refs = clean_refs(item.get("source_refs"))
            if not refs:
                continue
            elements.append(
                {"name": name.strip(), "value": value_text, "source_refs": refs}
            )

    review_notes = [
        note.strip()
        for note in _string_list(payload.get("review_notes"))
        if note.strip()
    ]
    source_refs = clean_refs(payload.get("source_refs"))
    return elements, review_notes, source_refs, dropped


class OllamaClient:
    """Minimal Ollama-compatible client built on the standard library."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL_NAME,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def build_request(self, prompt: str) -> urllib.request.Request:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "top_p": 0.1},
        }
        return urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Send one prompt and return the parsed JSON object the model produced."""

        request = self.build_request(prompt)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ModelAssistError(f"本地模型服务返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ModelAssistError(f"无法连接本地模型服务：{exc.reason}") from exc
        except OSError as exc:
            raise ModelAssistError(f"无法连接本地模型服务：{exc}") from exc

        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelAssistError("本地模型服务返回的内容不是合法 JSON") from exc
        if not isinstance(envelope, dict):
            raise ModelAssistError("本地模型服务返回结构不可识别")

        content = envelope.get("response")
        if not isinstance(content, str):
            raise ModelAssistError("本地模型返回缺少 response 字段")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelAssistError("模型输出不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ModelAssistError("模型输出不是 JSON 对象")
        return parsed


class JsonModelClient(Protocol):
    """Small provider boundary used by both extraction workflows."""

    def generate_json(self, prompt: str) -> dict[str, Any]: ...


class OpenAICompatibleClient:
    """JSON client for OpenAI-compatible chat-completions APIs.

    DeepSeek's public API uses this protocol. The adapter is intentionally
    generic so the same audited path can also be used with vLLM, LM Studio or
    another compatible service selected by the user.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key.strip():
            raise ModelAssistError("云端模型 API Key 为空")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def build_request(self, prompt: str) -> urllib.request.Request:
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "只依据用户提供的来源回答，并严格输出一个 JSON 对象。",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "stream": False,
        }
        return urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def generate_json(self, prompt: str) -> dict[str, Any]:
        request = self.build_request(prompt)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ModelAssistError(f"云端模型服务返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ModelAssistError(f"无法连接云端模型服务：{exc.reason}") from exc
        except OSError as exc:
            raise ModelAssistError(f"无法连接云端模型服务：{exc}") from exc

        try:
            envelope = json.loads(raw)
            choices = envelope["choices"]
            content = choices[0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ModelAssistError("云端模型服务返回结构不可识别") from exc
        if not isinstance(content, str):
            raise ModelAssistError("云端模型返回缺少文本内容")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelAssistError("云端模型输出不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ModelAssistError("云端模型输出不是 JSON 对象")
        return parsed


def build_model_client(
    config: ModelConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> JsonModelClient:
    """Build a provider client without exposing credentials to callers."""

    if config.provider == PROVIDER_OLLAMA:
        return OllamaClient(config.base_url, config.model_name, config.timeout)
    if config.provider == PROVIDER_OPENAI_COMPATIBLE:
        environment = os.environ if environ is None else environ
        key_name = config.api_key_env.strip()
        if not key_name:
            raise ModelAssistError("未指定云端模型 API Key 环境变量名")
        api_key = environment.get(key_name, "")
        if not api_key:
            raise ModelAssistError(f"环境变量 {key_name} 未设置")
        return OpenAICompatibleClient(
            config.base_url,
            config.model_name,
            api_key,
            config.timeout,
        )
    raise ModelAssistError(f"不支持的模型提供方：{config.provider}")


def model_setup_hint(config: ModelConfig) -> str:
    if config.provider == PROVIDER_OLLAMA:
        return LOCAL_SETUP_HINT
    return (
        f"请设置环境变量 {config.api_key_env}，并确认 API 地址、模型名、"
        "服务条款及科研材料上传范围"
    )


def run_model_assistance(
    paper: PaperDocument,
    repository: RepositorySnapshot,
    config: ModelConfig,
) -> ModelAssistance:
    """Ask the local model for auxiliary extraction without touching verdicts."""

    base = ModelAssistance(
        provider=config.provider,
        model=config.model_name,
        base_url=config.base_url,
    )

    source_lines = build_source_index(paper, repository)
    if not source_lines:
        base.status = STATUS_INVALID
        base.message = "没有可用于辅助抽取的来源行，未调用本地模型。"
        return base

    allowed = {item.ref for item in source_lines}
    try:
        client = build_model_client(config)
        payload = client.generate_json(build_prompt(source_lines))
    except ModelAssistError as exc:
        base.status = STATUS_UNAVAILABLE
        base.message = f"{exc}。{model_setup_hint(config)}。"
        return base

    has_elements = isinstance(payload.get("experiment_elements"), list)
    has_notes = isinstance(payload.get("review_notes"), list)
    if not has_elements and not has_notes:
        base.status = STATUS_INVALID
        base.message = "模型输出缺少 experiment_elements 与 review_notes 字段。"
        return base

    elements, notes, refs, dropped = sanitize_model_output(payload, allowed)
    base.status = STATUS_OK
    base.experiment_elements = elements
    base.review_notes = notes
    base.source_refs = refs
    base.dropped_source_refs = dropped
    base.message = "模型辅助结果仅供参考，不替代规则判定。"
    return base
