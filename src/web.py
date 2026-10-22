"""Dependency-free local web shell for the analyzer."""

from __future__ import annotations

import argparse
import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .analyzer import analyze
from .alignment import AlignmentError, detect_run_deviations
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
from .passport import passport_to_json, passport_to_markdown
from .protocol_extract import create_passport_from_paper
from .report import (
    MODEL_ASSISTANCE_DISCLAIMER,
    MODEL_STATUS_LABELS,
    NO_ACTION_ITEMS_TEXT,
    NO_EVIDENCE_LOCATION_TEXT,
    SEVERITY_LABELS,
    STATUS_LABELS,
    report_to_json,
    report_to_markdown,
)
from .review_workflow import ReviewInputError, apply_review_decision
from .workflow import WorkflowInputError, add_protocol_step, record_reproduction_run


class WebState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.report = None
        self.passport = None
        self.extraction = None
        self.error = ""


STATE = WebState()


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }}
body {{ margin: 0; background: #f4f7fb; color: #172033; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 40px 22px 64px; }}
header {{ margin-bottom: 28px; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
h2 {{ margin-top: 32px; font-size: 20px; }}
p {{ color: #526078; line-height: 1.6; }}
form, .panel {{ background: #fff; border: 1px solid #dce3ef; border-radius: 8px; padding: 22px; box-shadow: 0 8px 24px #1b315012; }}
label {{ display: block; margin-top: 14px; font-weight: 600; }}
input, select, textarea {{ display: block; box-sizing: border-box; width: 100%; margin-top: 7px; padding: 11px 12px; border: 1px solid #bcc8da; border-radius: 6px; font: inherit; }}
textarea {{ min-height: 92px; resize: vertical; }}
button {{ margin-top: 20px; padding: 11px 16px; border: 0; border-radius: 6px; background: #1769aa; color: white; font: inherit; font-weight: 700; cursor: pointer; }}
button:hover {{ background: #0f568e; }}
.workspace {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .65fr); gap: 22px; align-items: start; }}
.secondary {{ box-shadow: none; background: #f9fbfe; }}
.eyebrow {{ margin: 0 0 7px; color: #1769aa; font-size: 13px; font-weight: 700; }}
.badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; background: #e8f1f8; color: #14517e; font-size: 13px; font-weight: 700; }}
.review {{ border-left-color: #c88918; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 18px 0; }}
.stat {{ background: #fff; border-left: 4px solid #1769aa; border-radius: 6px; padding: 15px; border-top: 1px solid #dce3ef; border-right: 1px solid #dce3ef; border-bottom: 1px solid #dce3ef; }}
.stat strong {{ display: block; font-size: 24px; margin-top: 5px; }}
.finding {{ margin: 12px 0; padding: 16px; background: #fff; border: 1px solid #dce3ef; border-left: 5px solid #8492a6; border-radius: 6px; }}
.finding.high {{ border-left-color: #c33d3d; }} .finding.medium {{ border-left-color: #c88918; }} .finding.low {{ border-left-color: #2f7d4f; }}
.task {{ border-left-style: dashed; }}
.task h3 {{ font-size: 16px; }}
.finding h3 {{ margin: 0 0 8px; font-size: 17px; }}
.meta {{ color: #526078; font-size: 14px; }}
code {{ background: #eef2f7; padding: 2px 4px; border-radius: 3px; word-break: break-word; }}
li {{ margin: 7px 0; line-height: 1.45; }}
.error {{ padding: 12px; border: 1px solid #e5a6a6; background: #fff1f1; color: #8b2424; border-radius: 6px; }}
.links a {{ margin-right: 16px; color: #1769aa; }}
.inline-action {{ display: inline; padding: 0; border: 0; box-shadow: none; background: transparent; }}
.inline-action button {{ display: inline; width: auto; margin: 0 16px 0 0; padding: 0; background: transparent; color: #1769aa; font-weight: 400; }}
.inline-action button:hover {{ background: transparent; text-decoration: underline; }}
.form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }}
.step-editor {{ margin-top: 18px; padding-top: 18px; border-top: 1px solid #dce3ef; }}
@media (max-width: 820px) {{ .workspace {{ grid-template-columns: 1fr; }} main {{ padding-top: 24px; }} }}
@media (max-width: 620px) {{ .form-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body><main>{body}</main></body>
</html>"""
    return document.encode("utf-8")


def _home(
    error: str = "",
    paper: str = "",
    repo: str = "",
    model_mode: str = "rules",
    model_name: str = "",
    ollama_url: str = "",
    api_base_url: str = "",
    api_key_env: str = "",
) -> bytes:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    rules_selected = " selected" if model_mode == "rules" else ""
    ollama_selected = " selected" if model_mode == "ollama" else ""
    deepseek_selected = " selected" if model_mode == "deepseek" else ""
    body = f"""
<header>
<h1>科研复现体检员</h1>
<p>输入本机论文和代码仓库路径，生成带证据的复现风险报告。规则模式和 Ollama 模式可完全本地运行；也可主动选择 DeepSeek 云端辅助。</p>
</header>
{error_html}
<form method="post" action="/analyze">
<label for="paper">论文路径（.txt、.md 或 .pdf）</label>
<input id="paper" name="paper" value="{html.escape(paper)}" placeholder="D:\\\\path\\\\paper.pdf" required>
<label for="repo">代码仓库路径</label>
<input id="repo" name="repo" value="{html.escape(repo)}" placeholder="D:\\\\path\\\\repository" required>
<label for="model_mode">检查模式</label>
<select id="model_mode" name="model_mode">
<option value="rules"{rules_selected}>规则模式（离线，默认）</option>
<option value="ollama"{ollama_selected}>本地开源模型辅助（需本机 Ollama）</option>
<option value="deepseek"{deepseek_selected}>DeepSeek 云端辅助（需 API Key）</option>
</select>
<label for="model_name">模型名（留空使用所选模式默认值）</label>
<input id="model_name" name="model_name" value="{html.escape(model_name)}">
<label for="ollama_url">Ollama 地址（Ollama 模式，留空用默认）</label>
<input id="ollama_url" name="ollama_url" value="{html.escape(ollama_url)}">
<label for="api_base_url">DeepSeek / OpenAI 兼容 API 地址</label>
<input id="api_base_url" name="api_base_url" value="{html.escape(api_base_url)}" placeholder="{html.escape(DEFAULT_OPENAI_BASE_URL)}">
<label for="api_key_env">API Key 环境变量名</label>
<input id="api_key_env" name="api_key_env" value="{html.escape(api_key_env)}" placeholder="{html.escape(DEFAULT_API_KEY_ENV)}">
<button type="submit">开始体检</button>
</form>
"""
    return _page("科研复现体检员", body)


def _workspace_home(
    error: str = "",
    paper: str = "",
    repo: str = "",
    model_mode: str = "manual",
    model_name: str = "",
    ollama_url: str = "",
    api_base_url: str = "",
    api_key_env: str = "",
) -> bytes:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    manual_selected = " selected" if model_mode == "manual" else ""
    rules_selected = " selected" if model_mode in {"manual", "rules"} else ""
    ollama_selected = " selected" if model_mode == "ollama" else ""
    deepseek_selected = " selected" if model_mode == "deepseek" else ""
    body = f"""
<header>
<p class="eyebrow">开放科研 · 本地优先</p>
<h1>科研复现证据链</h1>
<p>从论文或实验协议创建复现任务，把研究主张、实际步骤、来源证据和偏差整理为可复核、可复用的档案。</p>
</header>
{error_html}
<div class="workspace">
<form method="post" action="/create-passport">
<span class="badge">主流程</span>
<h2>从论文或实验协议建档</h2>
<p>不要求代码仓库。手工模式先创建待填写骨架；模型模式会抽取带来源的研究主张和复现步骤。</p>
<label for="passport_paper">论文或实验协议路径（.txt、.md 或 .pdf）</label>
<input id="passport_paper" name="paper" value="{html.escape(paper)}" placeholder="D:\\path\\paper.pdf" required>
<label for="passport_model_mode">建档模式</label>
<select id="passport_model_mode" name="model_mode">
<option value="manual"{manual_selected}>手工建档（先生成待复核骨架）</option>
<option value="ollama"{ollama_selected}>本地开源模型抽取（需本机 Ollama）</option>
<option value="deepseek"{deepseek_selected}>DeepSeek 云端抽取（需 API Key）</option>
</select>
<label for="passport_model_name">模型名（留空使用模式默认值）</label>
<input id="passport_model_name" name="model_name" value="{html.escape(model_name)}" placeholder="{html.escape(DEFAULT_MODEL_NAME)} / {html.escape(DEFAULT_OPENAI_MODEL_NAME)}">
<label for="passport_ollama_url">Ollama 地址</label>
<input id="passport_ollama_url" name="ollama_url" value="{html.escape(ollama_url)}" placeholder="{html.escape(DEFAULT_BASE_URL)}">
<label for="passport_api_base_url">DeepSeek / OpenAI 兼容 API 地址</label>
<input id="passport_api_base_url" name="api_base_url" value="{html.escape(api_base_url)}" placeholder="{html.escape(DEFAULT_OPENAI_BASE_URL)}">
<label for="passport_api_key_env">API Key 环境变量名（不填写实际密钥）</label>
<input id="passport_api_key_env" name="api_key_env" value="{html.escape(api_key_env)}" placeholder="{html.escape(DEFAULT_API_KEY_ENV)}">
<button type="submit">创建复现档案</button>
</form>
<form class="secondary" method="post" action="/analyze">
<span class="badge">已有工具</span>
<h2>论文 + 代码体检</h2>
<p>使用现有15条确定性规则检查论文和本地代码仓库，生成风险与修复任务。</p>
<label for="paper">论文路径</label>
<input id="paper" name="paper" value="{html.escape(paper)}" required>
<label for="repo">代码仓库路径</label>
<input id="repo" name="repo" value="{html.escape(repo)}" required>
<label for="model_mode">检查模式</label>
<select id="model_mode" name="model_mode">
<option value="rules"{rules_selected}>规则模式（离线，默认）</option>
<option value="ollama"{ollama_selected}>本地开源模型辅助（需本机 Ollama）</option>
<option value="deepseek"{deepseek_selected}>DeepSeek 云端辅助（需 API Key）</option>
</select>
<label for="model_name">模型名</label>
<input id="model_name" name="model_name" value="{html.escape(model_name)}">
<label for="ollama_url">Ollama 地址</label>
<input id="ollama_url" name="ollama_url" value="{html.escape(ollama_url)}">
<label for="api_base_url">DeepSeek / OpenAI 兼容 API 地址</label>
<input id="api_base_url" name="api_base_url" value="{html.escape(api_base_url)}" placeholder="{html.escape(DEFAULT_OPENAI_BASE_URL)}">
<label for="api_key_env">API Key 环境变量名</label>
<input id="api_key_env" name="api_key_env" value="{html.escape(api_key_env)}" placeholder="{html.escape(DEFAULT_API_KEY_ENV)}">
<button type="submit">开始体检</button>
</form>
</div>
"""
    return _page("开放科研复现证据链", body)


def _passport_result_page(pack, extraction, notice: str = "", error: str = "") -> bytes:
    status_labels = {
        "manual": "手工骨架",
        "ok": "模型抽取完成",
        "unavailable": "模型不可用",
        "invalid_response": "模型输出不可用",
    }
    pending_reviews = [item for item in pack.reviews if item.decision == "pending"]
    stats = [
        ("研究主张", len(pack.claims)),
        ("复现步骤", len(pack.protocol_steps)),
        ("来源证据", len(pack.evidence)),
        ("实际运行", len(pack.runs)),
        ("结果", len(pack.results)),
        ("偏差", len(pack.deviations)),
        ("待人工复核", len(pending_reviews)),
    ]
    stats_html = "".join(
        f'<div class="stat"><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        for label, value in stats
    )
    claims_html = "".join(
        f'<article class="finding review"><h3>{html.escape(item.claim_id)}</h3>'
        f'<div class="meta">状态：{html.escape(item.status)} · 证据：{html.escape("、".join(item.evidence_ids) or "待补充")}</div>'
        f'<p>{html.escape(item.text)}</p></article>'
        for item in pack.claims
    ) or '<p class="meta">尚无研究主张。可启用模型抽取，并由研究者人工复核。</p>'
    steps_html = "".join(
        f'<article class="finding"><h3>{html.escape(item.step_id)} {html.escape(item.title)}</h3>'
        f'<div class="meta">顺序：{item.sequence} · 证据：{html.escape("、".join(item.evidence_ids) or "待补充")}</div>'
        f'<p>{html.escape(item.description or "待人工补充步骤说明。")}</p>'
        f'<p><strong>预期参数：</strong><code>{html.escape(json.dumps(item.expected_parameters, ensure_ascii=False))}</code></p>'
        f'</article>'
        for item in sorted(pack.protocol_steps, key=lambda value: (value.sequence, value.step_id))
    ) or '<p class="meta">尚无复现步骤。请进入“编辑步骤”手工添加，或启用模型抽取。</p>'
    evidence_html = "".join(
        f'<article class="finding"><h3>{html.escape(item.evidence_id)} {html.escape(item.source_type)}</h3>'
        f'<div class="meta">{html.escape(item.source_location)} · {html.escape(item.verification_level)} · {html.escape(item.status)}</div>'
        f'<p>{html.escape(item.content)}</p></article>'
        for item in pack.evidence
    ) or '<p class="meta">当前档案尚未收录来源证据。</p>'
    runs_html = "".join(
        f'<article class="finding"><h3>{html.escape(item.run_id)} {html.escape(item.title)}</h3>'
        f'<div class="meta">状态：{html.escape(item.status)} · 步骤记录：{len(item.steps)}</div>'
        f'<p><strong>环境：</strong><code>{html.escape(json.dumps(item.environment, ensure_ascii=False))}</code></p></article>'
        for item in pack.runs
    ) or '<p class="meta">当前没有实际复现过程记录。</p>'
    deviations_html = "".join(
        f'<article class="finding review"><h3>{html.escape(item.deviation_id)} {html.escape(item.summary)}</h3>'
        f'<div class="meta">状态：{html.escape(item.status)} · 证据：{html.escape("、".join(item.evidence_ids) or "待补充")}</div>'
        f'<p><strong>预期：</strong>{html.escape(item.expected)}<br><strong>实际：</strong>{html.escape(item.observed)}</p>'
        f'<p>{html.escape(item.explanation)}</p></article>'
        for item in pack.deviations
    ) or '<p class="meta">当前没有检测到待复核偏差。</p>'
    reviews_html = "".join(
        f'<article class="finding review"><h3>{html.escape(item.review_id)}</h3>'
        f'<div class="meta">对象：{html.escape(item.target_id)} · 决定：{html.escape(item.decision)}</div>'
        f'<p>{html.escape(item.note)}</p>'
        f'<form method="post" action="/review">'
        f'<input type="hidden" name="review_id" value="{html.escape(item.review_id, quote=True)}">'
        f'<div class="form-grid"><label>复核人<input name="reviewer" required></label>'
        f'<label>决定<select name="decision"><option value="accepted">接受</option><option value="rejected">驳回</option><option value="revised">修订</option></select></label></div>'
        f'<label>复核说明<textarea name="note"></textarea></label>'
        f'<button type="submit">提交人工复核</button></form></article>'
        for item in pending_reviews
    ) or '<p class="meta">当前没有待处理的人工复核任务。</p>'
    notice_html = (
        f'<section class="panel"><strong>{html.escape(notice)}</strong></section>'
        if notice
        else ""
    )
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
<header>
<p class="eyebrow">复现档案 · {html.escape(status_labels.get(extraction.status, extraction.status))}</p>
<h1>{html.escape(pack.title)}</h1>
<p>{html.escape(pack.study.summary or "当前档案等待研究者补充研究摘要。")}</p>
</header>
<div class="links"><a href="/edit-passport">编辑步骤</a><a href="/record-run">记录实际过程</a>{'<form class="inline-action" method="post" action="/check-deviations"><button type="submit">检查最新运行偏差</button></form>' if pack.runs else ''}<a href="/download/passport-json">下载档案 JSON</a><a href="/download/passport-markdown">下载档案 Markdown</a><a href="/">返回工作台</a></div>
{notice_html}{error_html}
<section class="stats">{stats_html}</section>
<section class="panel"><strong>建档状态：</strong>{html.escape(extraction.message)}<br><strong>档案编号：</strong><code>{html.escape(pack.pack_id)}</code></section>
<h2>研究主张</h2>
{claims_html}
<h2>复现步骤</h2>
{steps_html}
<h2>来源证据</h2>
{evidence_html}
<h2>实际复现过程</h2>
{runs_html}
<h2>自动发现的偏差</h2>
{deviations_html}
<h2>待人工复核</h2>
{reviews_html}
"""
    return _page("开放科研复现档案", body)


def _passport_editor_page(pack, notice: str = "", error: str = "") -> bytes:
    notice_html = (
        f'<section class="panel"><strong>{html.escape(notice)}</strong></section>'
        if notice
        else ""
    )
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    steps_html = "".join(
        f'<article class="finding"><h3>{html.escape(item.step_id)} {html.escape(item.title)}</h3>'
        f'<div class="meta">顺序：{item.sequence} · 来源证据：{html.escape("、".join(item.evidence_ids) or "待补充")}</div>'
        f'<p>{html.escape(item.description or "未填写说明")}</p>'
        f'<p><strong>预期参数：</strong><code>{html.escape(json.dumps(item.expected_parameters, ensure_ascii=False))}</code></p></article>'
        for item in sorted(pack.protocol_steps, key=lambda value: (value.sequence, value.step_id))
    ) or '<p class="meta">当前没有步骤。请先添加一条研究者确认过的复现步骤。</p>'
    record_link = (
        '<a href="/record-run">进入实际过程记录</a>'
        if pack.protocol_steps
        else '<span class="meta">添加步骤后才能记录实际过程</span>'
    )
    body = f"""
<header>
<p class="eyebrow">人工编辑 · 所有新增内容默认待复核</p>
<h1>编辑复现步骤</h1>
<p>{html.escape(pack.study.title)}</p>
</header>
<div class="links">{record_link}<a href="/download/passport-json">下载 JSON</a><a href="/">返回工作台</a></div>
{notice_html}{error_html}
<h2>现有步骤</h2>
{steps_html}
<form method="post" action="/add-step">
<h2>新增步骤</h2>
<label for="step_title">步骤标题</label>
<input id="step_title" name="title" required>
<label for="step_description">步骤说明</label>
<textarea id="step_description" name="description"></textarea>
<label for="expected_parameters">预期参数（JSON 对象）</label>
<textarea id="expected_parameters" name="expected_parameters" placeholder='{{"温度": "25°C", "时间": "30 min"}}'></textarea>
<div class="form-grid">
<label for="source_location">来源位置<input id="source_location" name="source_location" placeholder="论文第3页或协议第5步"></label>
<label for="evidence_content">来源原文<textarea id="evidence_content" name="evidence_content"></textarea></label>
</div>
<button type="submit">保存步骤</button>
</form>
"""
    return _page("编辑复现步骤", body)


def _run_form_page(pack, error: str = "") -> bytes:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    if not pack.protocol_steps:
        return _passport_editor_page(pack, error="请先添加至少一个复现步骤。")
    step_blocks = []
    for step in sorted(pack.protocol_steps, key=lambda value: (value.sequence, value.step_id)):
        step_id = html.escape(step.step_id, quote=True)
        expected = html.escape(json.dumps(step.expected_parameters, ensure_ascii=False))
        step_blocks.append(
            f'<section class="step-editor"><h3>{html.escape(step.step_id)} {html.escape(step.title)}</h3>'
            f'<p class="meta">预期参数：<code>{expected}</code></p>'
            f'<input type="hidden" name="step_id" value="{step_id}">'
            f'<label>实际状态<select name="status_{step_id}">'
            '<option value="not_started">未开始</option>'
            '<option value="in_progress">进行中</option>'
            '<option value="completed">已完成</option>'
            '<option value="failed">失败</option>'
            '<option value="skipped">跳过</option>'
            '</select></label>'
            f'<label>实际参数（JSON 对象）<textarea name="actual_parameters_{step_id}"></textarea></label>'
            f'<label>过程备注<textarea name="notes_{step_id}"></textarea></label>'
            '<div class="form-grid">'
            f'<label>证据位置<input name="evidence_location_{step_id}" placeholder="日志文件、实验记录页或结果路径"></label>'
            f'<label>证据内容<textarea name="evidence_content_{step_id}"></textarea></label>'
            '</div></section>'
        )
    body = f"""
<header>
<p class="eyebrow">实际过程 · 研究者填写</p>
<h1>记录一次复现运行</h1>
<p>{html.escape(pack.study.title)}</p>
</header>
<div class="links"><a href="/edit-passport">返回步骤编辑</a><a href="/download/passport-json">下载当前档案</a></div>
{error_html}
<form method="post" action="/save-run">
<div class="form-grid">
<label for="run_title">运行标题<input id="run_title" name="title" required></label>
<label for="run_status">运行状态<select id="run_status" name="status"><option value="planned">计划中</option><option value="in_progress">进行中</option><option value="completed">已完成</option><option value="failed">失败</option><option value="stopped">已停止</option></select></label>
<label for="started_at">开始时间<input id="started_at" name="started_at" placeholder="2026-10-20T09:00:00+08:00"></label>
<label for="ended_at">结束时间<input id="ended_at" name="ended_at" placeholder="2026-10-20T11:00:00+08:00"></label>
</div>
<label for="environment">运行环境（JSON 对象）</label>
<textarea id="environment" name="environment" placeholder='{{"设备": "实验室A仪器1", "软件": "Python 3.13"}}'></textarea>
<h2>逐步骤实际记录</h2>
{''.join(step_blocks)}
<h2>本次主要结果（可选）</h2>
<div class="form-grid">
<label>结果名称<input name="result_name"></label>
<label>实际值<input name="result_value"></label>
<label>预期值<input name="result_expected_value"></label>
<label>单位<input name="result_unit"></label>
<label>结果证据位置<input name="result_evidence_location"></label>
<label>结果证据内容<textarea name="result_evidence_content"></textarea></label>
</div>
<button type="submit">保存实际过程</button>
</form>
"""
    return _page("记录复现运行", body)


def _action_items_html(report) -> str:
    """Render the repair checklist. Every task field is HTML-escaped."""

    items = report.summary.get("action_items", [])
    if not items:
        return f'<p class="meta">{html.escape(NO_ACTION_ITEMS_TEXT)}</p>'
    blocks = []
    for item in items:
        severity = html.escape(item["severity"])
        heading = " ".join(
            html.escape(str(value))
            for value in (item["task_id"], item["rule_id"], item["title"])
        )
        severity_label = html.escape(SEVERITY_LABELS[item["severity"]])
        status_label = html.escape(STATUS_LABELS[item["status"]])
        if item["evidence_locations"]:
            locations_html = "<ul>" + "".join(
                f"<li><code>{html.escape(location)}</code></li>"
                for location in item["evidence_locations"]
            ) + "</ul>"
        else:
            locations_html = (
                f'<p class="meta">证据位置：{html.escape(NO_EVIDENCE_LOCATION_TEXT)}</p>'
            )
        blocks.append(
            f'<article class="finding task {severity}">'
            f"<h3>{heading}</h3>"
            f'<div class="meta">风险：{severity_label} · 状态：{status_label}</div>'
            f"<p><strong>行动：</strong>{html.escape(item['action'])}</p>"
            f"{locations_html}</article>"
        )
    return "".join(blocks)


def _model_assistance_html(report) -> str:
    """Render the optional model-assisted block. Every field is HTML-escaped."""

    assistance = getattr(report, "model_assistance", None)
    if not assistance:
        return ""
    status = assistance.get("status", "")
    rows = "".join(
        f'<div class="stat"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in (
            ("模型", str(assistance.get("model", ""))),
            ("模型状态", MODEL_STATUS_LABELS.get(status, str(status))),
        )
    )
    message = assistance.get("message")
    message_html = (
        f'<p class="meta">{html.escape(str(message))}</p>' if message else ""
    )
    elements_html = ""
    elements = assistance.get("experiment_elements", [])
    if elements:
        items = "".join(
            "<li><strong>{}</strong>：{}（来源：{}）</li>".format(
                html.escape(str(item.get("name", ""))),
                html.escape(str(item.get("value") or "（模型未给出取值）")),
                html.escape("、".join(item.get("source_refs", []))),
            )
            for item in elements
        )
        elements_html = f"<h3>抽取到的实验要素</h3><ul>{items}</ul>"
    notes_html = ""
    notes = assistance.get("review_notes", [])
    if notes:
        notes_html = "<h3>人工复核提示</h3><ul>" + "".join(
            f"<li>{html.escape(str(note))}</li>" for note in notes
        ) + "</ul>"
    return (
        f"<h2>模型辅助结果</h2>"
        f'<p class="meta">{html.escape(MODEL_ASSISTANCE_DISCLAIMER)}</p>'
        f'<section class="stats">{rows}</section>'
        f"{message_html}{elements_html}{notes_html}"
    )


def _result_page(report) -> bytes:
    summary = report.summary
    model_html = _model_assistance_html(report)
    stats = [
        ("检查项", summary["total_findings"]),
        ("待修复", len(summary.get("action_items", []))),
        ("高风险", summary["high_risk_count"]),
        ("中风险", summary["medium_risk_count"]),
        ("未找到", summary["missing_count"]),
        ("需确认", summary["needs_review_count"]),
        ("证据覆盖率", f"{summary['evidence_coverage']:.1%}"),
    ]
    stats_html = "".join(
        f'<div class="stat"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in stats
    )
    findings_html = []
    for finding in report.findings:
        evidence_html = ""
        if finding.evidence:
            evidence_html = "<ul>" + "".join(
                f"<li><code>{html.escape(item.location)}</code> {html.escape(item.quote)}</li>"
                for item in finding.evidence
            ) + "</ul>"
        findings_html.append(
            f'<article class="finding {finding.severity}">'
            f"<h3>{html.escape(finding.rule_id)} {html.escape(finding.title)}</h3>"
            f'<div class="meta">状态：{html.escape(finding.status)} · 风险：{html.escape(finding.severity)} · 置信度：{finding.confidence:.0%}</div>'
            f"<p>{html.escape(finding.finding)}</p>"
            f"<p><strong>建议：</strong>{html.escape(finding.suggestion)}</p>"
            f"{evidence_html}</article>"
        )
    action_items_html = _action_items_html(report)
    body = f"""
<header>
<h1>体检报告：{html.escape(report.project_name)}</h1>
<p>论文：<code>{html.escape(report.paper_path)}</code><br>仓库：<code>{html.escape(report.repository_path)}</code></p>
</header>
<div class="links"><a href="/download/json">下载 JSON</a><a href="/download/markdown">下载 Markdown</a><a href="/">重新检查</a></div>
<section class="stats">{stats_html}</section>
<h2>待修复任务</h2>
{action_items_html}
<h2>检查结果</h2>
{''.join(findings_html)}
{model_html}
"""
    return _page("体检报告", body)


class AnalysisHandler(BaseHTTPRequestHandler):
    def _send(self, content: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if self.path == "/":
            with STATE.lock:
                error = STATE.error
                STATE.error = ""
            self._send(_workspace_home(error))
            return
        if self.path in {"/edit-passport", "/record-run"}:
            with STATE.lock:
                passport = STATE.passport
            if passport is None:
                self._send(_workspace_home("请先创建复现档案。"), status=404)
                return
            page = (
                _passport_editor_page(passport)
                if self.path == "/edit-passport"
                else _run_form_page(passport)
            )
            self._send(page)
            return
        if self.path in {"/download/passport-json", "/download/passport-markdown"}:
            with STATE.lock:
                passport = STATE.passport
            if passport is None:
                self._send(_workspace_home("还没有可下载的复现档案。"), status=404)
                return
            is_json = self.path.endswith("json")
            content = (
                passport_to_json(passport) if is_json else passport_to_markdown(passport)
            ).encode("utf-8")
            filename = "reproduction-passport.json" if is_json else "reproduction-passport.md"
            content_type = (
                "application/json; charset=utf-8"
                if is_json
                else "text/markdown; charset=utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == "/download/json":
            with STATE.lock:
                report = STATE.report
            if report is None:
                self._send(_home("还没有可下载的报告。"), status=404)
                return
            content = report_to_json(report).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="reprocheck-report.json"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == "/download/markdown":
            with STATE.lock:
                report = STATE.report
            if report is None:
                self._send(_home("还没有可下载的报告。"), status=404)
                return
            content = report_to_markdown(report).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="reprocheck-report.md"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self._send(_workspace_home("页面不存在。"), status=404)

    def do_POST(self) -> None:
        if self.path not in {
            "/analyze",
            "/create-passport",
            "/add-step",
            "/save-run",
            "/check-deviations",
            "/review",
        }:
            self._send(_workspace_home("请求地址不存在。"), status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        if self.path == "/review":
            with STATE.lock:
                passport = STATE.passport
                extraction = STATE.extraction
                if passport is None:
                    self._send(_workspace_home("请先创建复现档案。"), status=404)
                    return
                review_id = form.get("review_id", [""])[0]
                try:
                    review = apply_review_decision(
                        passport,
                        review_id=review_id,
                        decision=form.get("decision", [""])[0],
                        reviewer=form.get("reviewer", [""])[0],
                        note=form.get("note", [""])[0],
                    )
                except (ReviewInputError, ValueError) as exc:
                    self._send(
                        _passport_result_page(passport, extraction, error=str(exc)),
                        status=400,
                    )
                    return
            self._send(
                _passport_result_page(
                    passport,
                    extraction,
                    notice=f"{review.review_id} 已由 {review.reviewer} 完成人工复核。",
                )
            )
            return

        if self.path == "/check-deviations":
            with STATE.lock:
                passport = STATE.passport
                extraction = STATE.extraction
                if passport is None or not passport.runs:
                    self._send(_workspace_home("请先记录一次实际运行。"), status=400)
                    return
                try:
                    detect_run_deviations(passport, passport.runs[-1].run_id)
                except (AlignmentError, ValueError) as exc:
                    self._send(_passport_result_page(passport, extraction), status=400)
                    return
            self._send(_passport_result_page(passport, extraction))
            return

        if self.path == "/add-step":
            with STATE.lock:
                passport = STATE.passport
                if passport is None:
                    self._send(_workspace_home("请先创建复现档案。"), status=404)
                    return
                try:
                    step = add_protocol_step(
                        passport,
                        title=form.get("title", [""])[0],
                        description=form.get("description", [""])[0],
                        expected_parameters_json=form.get(
                            "expected_parameters", [""]
                        )[0],
                        source_location=form.get("source_location", [""])[0],
                        evidence_content=form.get("evidence_content", [""])[0],
                    )
                except (WorkflowInputError, ValueError) as exc:
                    self._send(_passport_editor_page(passport, error=str(exc)), status=400)
                    return
            self._send(
                _passport_editor_page(
                    passport, notice=f"已保存 {step.step_id}，等待人工复核。"
                )
            )
            return

        if self.path == "/save-run":
            with STATE.lock:
                passport = STATE.passport
                extraction = STATE.extraction
                if passport is None:
                    self._send(_workspace_home("请先创建复现档案。"), status=404)
                    return
                step_entries = []
                for step_id in form.get("step_id", []):
                    step_entries.append(
                        {
                            "step_id": step_id,
                            "status": form.get(f"status_{step_id}", ["not_started"])[0],
                            "actual_parameters_json": form.get(
                                f"actual_parameters_{step_id}", [""]
                            )[0],
                            "notes": form.get(f"notes_{step_id}", [""])[0],
                            "source_location": form.get(
                                f"evidence_location_{step_id}", [""]
                            )[0],
                            "evidence_content": form.get(
                                f"evidence_content_{step_id}", [""]
                            )[0],
                            "source_type": "experiment_record",
                        }
                    )
                result = {
                    "name": form.get("result_name", [""])[0],
                    "value": form.get("result_value", [""])[0],
                    "expected_value": form.get("result_expected_value", [""])[0],
                    "unit": form.get("result_unit", [""])[0],
                    "source_location": form.get(
                        "result_evidence_location", [""]
                    )[0],
                    "evidence_content": form.get("result_evidence_content", [""])[0],
                    "source_type": "result_record",
                }
                try:
                    record_reproduction_run(
                        passport,
                        title=form.get("title", [""])[0],
                        status=form.get("status", ["planned"])[0],
                        step_entries=step_entries,
                        environment_json=form.get("environment", [""])[0],
                        started_at=form.get("started_at", [""])[0],
                        ended_at=form.get("ended_at", [""])[0],
                        result=result,
                    )
                except (WorkflowInputError, ValueError) as exc:
                    self._send(_run_form_page(passport, error=str(exc)), status=400)
                    return
            self._send(_passport_result_page(passport, extraction))
            return

        paper = form.get("paper", [""])[0].strip()
        default_mode = "manual" if self.path == "/create-passport" else "rules"
        model_mode = form.get("model_mode", [default_mode])[0].strip() or default_mode
        requested_model = form.get("model_name", [""])[0].strip()
        ollama_url = form.get("ollama_url", [""])[0].strip() or DEFAULT_BASE_URL
        api_base_url = (
            form.get("api_base_url", [""])[0].strip() or DEFAULT_OPENAI_BASE_URL
        )
        api_key_env = form.get("api_key_env", [""])[0].strip() or DEFAULT_API_KEY_ENV
        cloud_mode = model_mode == "deepseek"
        model_name = requested_model or (
            DEFAULT_OPENAI_MODEL_NAME if cloud_mode else DEFAULT_MODEL_NAME
        )
        model_config = ModelConfig(
            enabled=model_mode in {"ollama", "deepseek"},
            provider=(
                PROVIDER_OPENAI_COMPATIBLE if cloud_mode else PROVIDER_OLLAMA
            ),
            base_url=api_base_url if cloud_mode else ollama_url,
            model_name=model_name,
            api_key_env=api_key_env,
        )
        if self.path == "/create-passport":
            try:
                passport, extraction = create_passport_from_paper(
                    Path(paper), model_config=model_config
                )
            except Exception as exc:
                with STATE.lock:
                    STATE.error = str(exc)
                self._send(
                    _workspace_home(
                        str(exc),
                        paper=paper,
                        model_mode=model_mode,
                        model_name=requested_model,
                        ollama_url=ollama_url,
                        api_base_url=api_base_url,
                        api_key_env=api_key_env,
                    ),
                    status=400,
                )
                return
            with STATE.lock:
                STATE.passport = passport
                STATE.extraction = extraction
                STATE.error = ""
            self._send(_passport_result_page(passport, extraction))
            return

        repo = form.get("repo", [""])[0].strip()
        try:
            report = analyze(Path(paper), Path(repo), model_config=model_config)
        except Exception as exc:
            with STATE.lock:
                STATE.error = str(exc)
            self._send(
                _home(
                    str(exc),
                    paper,
                    repo,
                    model_mode,
                    requested_model,
                    ollama_url,
                    api_base_url,
                    api_key_env,
                ),
                status=400,
            )
            return
        with STATE.lock:
            STATE.report = report
            STATE.error = ""
        self._send(_result_page(report))

    def log_message(self, format: str, *args) -> None:
        print(f"[web] {format % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动科研复现体检员本地网页。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), AnalysisHandler)
    print(f"科研复现体检员已启动: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
