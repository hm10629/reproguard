"""Create a source-grounded reproduction passport from a paper or protocol."""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model_assist import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NAME,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL_NAME,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    ModelAssistError,
    ModelConfig,
    SourceLine,
    build_model_client,
    model_setup_hint,
)
from .paper_extract import PaperDocument, PaperExtractionError, load_paper
from .passport import (
    Claim,
    EvidenceRecord,
    ProtocolStep,
    ReproductionPack,
    Review,
    Study,
    write_passport,
)


STATUS_MANUAL = "manual"
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INVALID = "invalid_response"
MAX_SOURCE_LINES = 300
MAX_SOURCE_TEXT = 360


@dataclass
class ProtocolExtraction:
    status: str
    study: dict[str, Any] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    protocol_steps: list[dict[str, Any]] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    dropped_source_refs: list[str] = field(default_factory=list)
    message: str = ""


def build_paper_source_index(
    paper: PaperDocument,
    *,
    max_lines: int = MAX_SOURCE_LINES,
) -> list[SourceLine]:
    """Assign stable source ids to non-empty paper or protocol lines."""

    entries: list[SourceLine] = []
    for page, line_number, line in paper.iter_lines():
        text = line.strip()
        if not text:
            continue
        entries.append(
            SourceLine(
                ref=f"P{len(entries) + 1:03d}",
                origin="paper",
                location=f"第 {page.page} 页 第 {line_number} 行",
                text=text[:MAX_SOURCE_TEXT],
            )
        )
        if len(entries) >= max_lines:
            break
    return entries


PROMPT_TEMPLATE = """你是开放科研复现档案的步骤抽取器。输入可能来自计算机、生物、化学、材料、社会科学或其他学科，不要假设一定存在代码。

请只依据给出的来源行，提取研究信息、可执行复现步骤和需要人工复核的事项。只输出 JSON，不要输出解释文字。

JSON 结构必须是：
{{
  "study": {{
    "title": "研究标题",
    "discipline": "学科或研究领域，不确定时为空",
    "summary": "只基于来源的简短研究摘要",
    "source_refs": ["P001"]
  }},
  "claims": [
    {{"text": "论文明确提出的研究主张", "source_refs": ["P002"]}}
  ],
  "protocol_steps": [
    {{
      "title": "步骤标题",
      "description": "可执行步骤说明",
      "expected_parameters": {{"参数名": "来源中明确给出的值"}},
      "source_refs": ["P003"]
    }}
  ],
  "review_notes": ["必须由研究者确认的事项"]
}}

约束：
1. source_refs 只能引用下面出现的编号；不得编造编号。
2. 不得补写来源中没有的参数、材料、设备、数据或结论。
3. 无法确定的内容放入 review_notes，不要猜测。
4. protocol_steps 应描述来源明确支持的操作；不要把背景介绍改写成实验步骤。
5. 所有输出都将进入人工复核，模型不得声称已经完成复现。

来源行：
{context}
"""


def build_protocol_prompt(source_lines: list[SourceLine]) -> str:
    context = "\n".join(
        f"[{item.ref}] {item.location} | {item.text}" for item in source_lines
    )
    return PROMPT_TEMPLATE.format(context=context)


def _clean_refs(value: Any, allowed_refs: set[str], dropped: list[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for ref in value:
        if not isinstance(ref, str):
            continue
        if ref in allowed_refs:
            if ref not in result:
                result.append(ref)
        elif ref not in dropped:
            dropped.append(ref)
    return result


def sanitize_protocol_output(
    payload: dict[str, Any],
    allowed_refs: set[str],
) -> ProtocolExtraction:
    """Discard unsupported fields and every item without a trusted citation."""

    dropped: list[str] = []
    study: dict[str, Any] = {}
    raw_study = payload.get("study")
    if isinstance(raw_study, dict):
        study_refs = _clean_refs(raw_study.get("source_refs"), allowed_refs, dropped)
        if study_refs:
            study = {
                "title": str(raw_study.get("title", "")).strip(),
                "discipline": str(raw_study.get("discipline", "")).strip(),
                "summary": str(raw_study.get("summary", "")).strip(),
                "source_refs": study_refs,
            }

    claims: list[dict[str, Any]] = []
    raw_claims = payload.get("claims")
    if isinstance(raw_claims, list):
        for item in raw_claims:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            refs = _clean_refs(item.get("source_refs"), allowed_refs, dropped)
            if isinstance(text, str) and text.strip() and refs:
                claims.append({"text": text.strip(), "source_refs": refs})

    steps: list[dict[str, Any]] = []
    raw_steps = payload.get("protocol_steps")
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            refs = _clean_refs(item.get("source_refs"), allowed_refs, dropped)
            if not isinstance(title, str) or not title.strip() or not refs:
                continue
            parameters = item.get("expected_parameters")
            if not isinstance(parameters, dict):
                parameters = {}
            steps.append(
                {
                    "title": title.strip(),
                    "description": str(item.get("description", "")).strip(),
                    "expected_parameters": parameters,
                    "source_refs": refs,
                }
            )

    notes = payload.get("review_notes")
    review_notes = (
        [note.strip() for note in notes if isinstance(note, str) and note.strip()]
        if isinstance(notes, list)
        else []
    )
    return ProtocolExtraction(
        status=STATUS_OK,
        study=study,
        claims=claims,
        protocol_steps=steps,
        review_notes=review_notes,
        dropped_source_refs=dropped,
        message="模型提取结果已绑定来源，仍须人工复核。",
    )


def run_protocol_extraction(
    paper: PaperDocument,
    config: ModelConfig | None,
) -> tuple[ProtocolExtraction, list[SourceLine]]:
    sources = build_paper_source_index(paper)
    if not sources:
        return (
            ProtocolExtraction(
                status=STATUS_INVALID,
                review_notes=["论文或协议中没有可读取的非空文本。"],
                message="没有可用于抽取的来源行。",
            ),
            sources,
        )
    if config is None or not config.enabled:
        return (
            ProtocolExtraction(
                status=STATUS_MANUAL,
                review_notes=["尚未启用模型，请人工填写研究主张和复现步骤。"],
                message="已创建空白复现档案骨架。",
            ),
            sources,
        )

    try:
        client = build_model_client(config)
        payload = client.generate_json(build_protocol_prompt(sources))
    except ModelAssistError as exc:
        return (
            ProtocolExtraction(
                status=STATUS_UNAVAILABLE,
                review_notes=["模型不可用，研究主张和步骤需要人工填写。"],
                message=f"{exc}。{model_setup_hint(config)}。",
            ),
            sources,
        )

    if not isinstance(payload, dict):
        return (
            ProtocolExtraction(
                status=STATUS_INVALID,
                review_notes=["模型输出结构无效，需要人工填写。"],
                message="模型输出不是 JSON 对象。",
            ),
            sources,
        )
    extraction = sanitize_protocol_output(payload, {item.ref for item in sources})
    if not extraction.study and not extraction.claims and not extraction.protocol_steps:
        extraction.status = STATUS_INVALID
        extraction.review_notes.append("模型没有返回任何带有效来源的研究内容。")
        extraction.message = "模型输出没有可采信的来源引用。"
    return extraction, sources


def _stable_suffix(paper: PaperDocument) -> str:
    digest = hashlib.sha256()
    digest.update(str(paper.path.resolve()).encode("utf-8"))
    digest.update(b"\0")
    digest.update(paper.text.encode("utf-8"))
    return digest.hexdigest()[:12].upper()


def create_passport_from_paper(
    paper_path: Path,
    *,
    model_config: ModelConfig | None = None,
) -> tuple[ReproductionPack, ProtocolExtraction]:
    paper = load_paper(Path(paper_path))
    extraction, sources = run_protocol_extraction(paper, model_config)
    suffix = _stable_suffix(paper)
    pack_id = f"PACK-{suffix}"
    study_id = f"STUDY-{suffix}"
    source_by_ref = {item.ref: item for item in sources}
    used_refs: list[str] = []

    def add_refs(refs: list[str]) -> None:
        for ref in refs:
            if ref not in used_refs:
                used_refs.append(ref)

    add_refs(extraction.study.get("source_refs", []))
    for item in extraction.claims:
        add_refs(item["source_refs"])
    for item in extraction.protocol_steps:
        add_refs(item["source_refs"])

    evidence_id_by_ref = {ref: f"EV-{ref}" for ref in used_refs}
    evidence = [
        EvidenceRecord(
            evidence_id=evidence_id_by_ref[ref],
            source_type="paper_or_protocol",
            source_location=source_by_ref[ref].location,
            content=source_by_ref[ref].text,
            verification_level="machine_extracted",
            status="needs_review",
            source_uri=str(paper.path.resolve()),
            metadata={"source_ref": ref},
        )
        for ref in used_refs
    ]

    claims = [
        Claim(
            claim_id=f"CLAIM-{index:03d}",
            text=item["text"],
            evidence_ids=[evidence_id_by_ref[ref] for ref in item["source_refs"]],
            status="needs_review",
        )
        for index, item in enumerate(extraction.claims, start=1)
    ]
    steps = [
        ProtocolStep(
            step_id=f"STEP-{index:03d}",
            title=item["title"],
            description=item["description"],
            sequence=index,
            expected_parameters=item["expected_parameters"],
            evidence_ids=[evidence_id_by_ref[ref] for ref in item["source_refs"]],
        )
        for index, item in enumerate(extraction.protocol_steps, start=1)
    ]

    reviews = [
        Review(
            review_id=f"REVIEW-{item.claim_id}",
            target_type="claim",
            target_id=item.claim_id,
            decision="pending",
            note="【必须人工复核】确认研究主张及其来源证据。",
        )
        for item in claims
    ]
    reviews.extend(
        Review(
            review_id=f"REVIEW-{item.step_id}",
            target_type="protocol_step",
            target_id=item.step_id,
            decision="pending",
            note="【必须人工复核】确认该步骤可执行且未超出来源内容。",
        )
        for item in steps
    )
    if not reviews or extraction.review_notes:
        note = "；".join(extraction.review_notes) or "人工补充研究主张和复现步骤。"
        reviews.append(
            Review(
                review_id="REVIEW-PACK",
                target_type="reproduction_pack",
                target_id=pack_id,
                decision="pending",
                note=f"【必须人工复核】{note}",
            )
        )

    extracted_study = extraction.study
    study_title = extracted_study.get("title") or paper.path.stem
    pack = ReproductionPack(
        pack_id=pack_id,
        title=f"{study_title}复现档案",
        study=Study(
            study_id=study_id,
            title=study_title,
            source_citation=str(paper.path.resolve()),
            discipline=extracted_study.get("discipline", ""),
            summary=extracted_study.get("summary", ""),
        ),
        evidence=evidence,
        claims=claims,
        protocol_steps=steps,
        reviews=reviews,
    )
    pack.validate()
    return pack, extraction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从论文或实验协议创建开放科研复现档案，不要求代码仓库。"
    )
    parser.add_argument("--paper", required=True, help="论文或协议路径")
    parser.add_argument("--output", required=True, help="复现档案输出前缀")
    parser.add_argument(
        "--model-mode",
        choices=("manual", "ollama", "deepseek"),
        default="manual",
        help=(
            "manual 创建待人工填写的骨架；ollama 使用本地模型；"
            "deepseek 使用 DeepSeek 云端 API"
        ),
    )
    parser.add_argument("--model-name", default="")
    parser.add_argument("--ollama-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cloud_mode = args.model_mode == "deepseek"
    config = ModelConfig(
        enabled=args.model_mode != "manual",
        provider=(PROVIDER_OPENAI_COMPATIBLE if cloud_mode else PROVIDER_OLLAMA),
        model_name=args.model_name
        or (DEFAULT_OPENAI_MODEL_NAME if cloud_mode else DEFAULT_MODEL_NAME),
        base_url=args.api_base_url if cloud_mode else args.ollama_url,
        api_key_env=args.api_key_env,
    )
    try:
        pack, extraction = create_passport_from_paper(
            Path(args.paper), model_config=config
        )
        paths = write_passport(pack, Path(args.output))
    except (PaperExtractionError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"建档完成：{pack.pack_id} / 抽取状态：{extraction.status}")
    if extraction.message:
        print(f"说明：{extraction.message}")
    for path in paths:
        print(f"已生成：{path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
