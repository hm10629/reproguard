"""Command-line entry point for the local analyzer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import analyze
from .model_assist import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_NAME,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL_NAME,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    ModelConfig,
)
from .paper_extract import PaperExtractionError
from .report import MODEL_STATUS_LABELS, write_reports
from .repository_scan import RepositoryScanError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="分析论文和本地代码仓库的科研复现条件。",
    )
    parser.add_argument("--paper", required=True, help="论文路径，支持 .txt、.md、.pdf")
    parser.add_argument("--repo", required=True, help="本地代码仓库目录")
    parser.add_argument("--output", required=True, help="报告输出前缀")
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "both"),
        default="both",
        help="输出格式，默认 both",
    )
    parser.add_argument(
        "--model-mode",
        choices=("rules", "ollama", "deepseek"),
        default="rules",
        help=(
            "检查模式：rules 为纯规则离线模式；ollama 为本地模型辅助；"
            "deepseek 为 DeepSeek 云端 API 辅助"
        ),
    )
    parser.add_argument(
        "--model-name",
        default="",
        help=(
            f"模型名；Ollama 默认 {DEFAULT_MODEL_NAME}，"
            f"DeepSeek 默认 {DEFAULT_OPENAI_MODEL_NAME}"
        ),
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_BASE_URL,
        help=f"Ollama 模式的服务地址，默认 {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_OPENAI_BASE_URL,
        help=f"DeepSeek/OpenAI 兼容 API 地址，默认 {DEFAULT_OPENAI_BASE_URL}",
    )
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help=f"API Key 所在环境变量名，默认 {DEFAULT_API_KEY_ENV}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cloud_mode = args.model_mode == "deepseek"
    model_config = ModelConfig(
        enabled=args.model_mode != "rules",
        provider=(PROVIDER_OPENAI_COMPATIBLE if cloud_mode else PROVIDER_OLLAMA),
        base_url=args.api_base_url if cloud_mode else args.ollama_url,
        model_name=args.model_name
        or (DEFAULT_OPENAI_MODEL_NAME if cloud_mode else DEFAULT_MODEL_NAME),
        api_key_env=args.api_key_env,
    )
    try:
        report = analyze(Path(args.paper), Path(args.repo), model_config=model_config)
        paths = write_reports(report, Path(args.output), args.format)
    except (PaperExtractionError, RepositoryScanError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    for path in paths:
        print(f"已生成：{path.resolve()}")
    print(
        "检查完成："
        f"{report.summary['total_findings']} 项，"
        f"{report.summary['high_risk_count']} 个高风险，"
        f"{report.summary['missing_count']} 项当前范围内未找到。"
    )
    if report.model_assistance:
        assistance = report.model_assistance
        status = MODEL_STATUS_LABELS.get(
            assistance.get("status", ""), assistance.get("status", "")
        )
        print(
            "模型辅助："
            f"{assistance.get('provider', '')} / {assistance.get('model', '')} / {status}"
        )
        if assistance.get("message"):
            print(f"  {assistance['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
