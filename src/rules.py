"""Deterministic v0.1 reproducibility checks."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Evidence, Finding
from .paper_extract import PaperDocument
from .repository_scan import RepositoryFile, RepositorySnapshot


MISSING_TEXT = "在当前检查范围内未找到相关信息。"

RULE_META = {
    "R001": ("是否存在项目说明文档", "medium", "补充 README，说明安装、数据、运行和评测步骤。"),
    "R002": ("是否声明依赖及版本", "high", "锁定主要依赖的具体版本，并提交依赖文件。"),
    "R003": ("是否说明数据集来源和下载方式", "high", "补充数据集主页、版本、下载方式和许可说明。"),
    "R004": ("是否说明数据预处理和数据划分", "high", "明确预处理、训练/验证/测试划分和对应脚本。"),
    "R005": ("是否设置或说明随机种子", "medium", "固定并记录 Python、NumPy、框架和数据加载器的随机种子。"),
    "R006": ("是否说明关键训练超参数", "high", "补充学习率、优化器、epoch、batch size 等关键参数。"),
    "R007": ("是否说明硬件和运行环境", "medium", "记录 GPU/CPU、显存、操作系统和关键运行环境。"),
    "R008": ("是否存在明确的实验入口命令", "high", "在 README 中给出可以直接复制执行的训练或评测命令。"),
    "R009": ("是否能定位评价指标的计算方式", "high", "提供指标定义、计算代码和评测命令。"),
    "R010": ("是否提供结果生成或评测输出", "medium", "说明结果文件位置、格式和生成命令。"),
    "R011": ("论文中的模型、数据集和代码名称是否对应", "high", "统一论文、代码和数据集名称，避免复现者猜测对应关系。"),
    "R012": ("是否说明预训练模型或外部权重来源", "high", "记录权重名称、下载地址、版本和使用方式；若不涉及请明确说明。"),
    "R013": ("是否记录关键版本或提交号", "medium", "记录代码 commit、发布版本或实验快照。"),
    "R014": ("是否提供许可证和数据使用限制", "low", "补充 LICENSE，并说明数据集和外部模型的使用限制。"),
    "R015": ("是否有失败处理或常见问题说明", "low", "补充常见错误、资源要求和排障步骤。"),
}


def _meta(rule_id: str) -> tuple[str, str, str]:
    return RULE_META[rule_id]


def _evidence_file(file: RepositoryFile, line: int, quote: str) -> Evidence:
    return Evidence(
        source="repository",
        location=f"{file.relative_path}:{line}",
        quote=quote[:240],
        line=line,
    )


def _evidence_paper(page: int, line: int, quote: str) -> Evidence:
    return Evidence(
        source="paper",
        location=f"page {page}, line {line}",
        quote=quote[:240],
        line=line,
        page=page,
    )


def _positive(line: str) -> bool:
    """Ignore explicit negative statements in the sample and real docs."""

    negative = (
        "没有",
        "未说明",
        "未提供",
        "缺少",
        "不存在",
        "不需要",
        "无需",
        "not provided",
        "not specified",
        "no ",
        "missing",
    )
    lower = line.lower()
    return not any(token in lower for token in negative)


def _find_repo_lines(snapshot: RepositorySnapshot, terms: Iterable[str]):
    return [
        (file, line_number, line)
        for file, line_number, line in snapshot.matching_lines(terms)
        if _positive(line)
    ]


def _find_paper_lines(paper: PaperDocument, terms: Iterable[str]):
    lowered = [term.lower() for term in terms]
    matches = []
    for page, line_number, line in paper.iter_lines():
        lower_line = line.lower()
        if _positive(line) and any(term in lower_line for term in lowered):
            matches.append((page, line_number, line.strip()))
    return matches


def _finding(
    rule_id: str,
    status: str,
    finding: str,
    evidence: list[Evidence] | None = None,
    *,
    confidence: float = 1.0,
) -> Finding:
    title, severity, suggestion = _meta(rule_id)
    return Finding(
        rule_id=rule_id,
        title=title,
        status=status,
        severity=severity,
        finding=finding,
        evidence=evidence or [],
        suggestion=suggestion,
        confidence=confidence,
    )


def check_r001(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    files = repo.find_name_prefix("readme")
    if not files:
        return _finding("R001", "missing", MISSING_TEXT)

    install_pattern = re.compile(
        r"(?:pip(?:3)?\s+install|conda\s+(?:env\s+create|install)|"
        r"poetry\s+install|uv\s+(?:sync|pip)|npm\s+(?:install|ci)|"
        r"安装|依赖)",
        re.IGNORECASE,
    )
    run_pattern = re.compile(
        r"(?:python(?:3)?\s+(?:-m\s+)?[^\s`]*(?:train|eval|evaluate|test|main|run)[^\s`]*|"
        r"pytest(?:\s|$)|make\s+(?:train|eval|test|run)|"
        r"(?:bash|sh)\s+[^\s`]+|运行命令|训练命令|评测命令)",
        re.IGNORECASE,
    )
    install_hits: list[Evidence] = []
    run_hits: list[Evidence] = []
    readme_evidence = _evidence_file(
        files[0], 1, files[0].lines[0] if files[0].lines else files[0].name
    )
    for file in files:
        for line_number, line in enumerate(file.lines, start=1):
            if _positive(line) and install_pattern.search(line):
                install_hits.append(_evidence_file(file, line_number, line.strip()))
            if _positive(line) and run_pattern.search(line):
                run_hits.append(_evidence_file(file, line_number, line.strip()))

    evidence = [readme_evidence, *install_hits[:1], *run_hits[:1]]
    if install_hits and run_hits:
        return _finding(
            "R001",
            "found",
            "找到项目说明文档，并定位到安装说明和可执行实验命令。",
            evidence,
        )
    missing_parts = []
    if not install_hits:
        missing_parts.append("安装说明")
    if not run_hits:
        missing_parts.append("可执行的训练或评测命令")
    return _finding(
        "R001",
        "partial",
        f"找到项目说明文档，但未找到{'、'.join(missing_parts)}。",
        evidence,
    )


def check_r002(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    dependency_files = repo.find_files(
        "requirements.txt",
        "environment.yml",
        "environment.yaml",
        "pyproject.toml",
        "setup.py",
        "poetry.lock",
        "package-lock.json",
    )
    if not dependency_files:
        return _finding("R002", "missing", MISSING_TEXT)
    version_pattern = re.compile(r"(==|>=|<=|~=|==\s*[\"'])\s*[vV]?\d")
    version_hits: list[Evidence] = []
    package_hits: list[Evidence] = []
    for file in dependency_files:
        for line_number, line in enumerate(file.lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            package_hits.append(_evidence_file(file, line_number, stripped))
            if version_pattern.search(stripped):
                version_hits.append(_evidence_file(file, line_number, stripped))
    if version_hits:
        return _finding("R002", "found", "找到带版本约束的依赖声明。", version_hits[:3])
    return _finding(
        "R002",
        "partial",
        "找到依赖文件，但当前未找到明确的具体版本。",
        package_hits[:3],
    )


def check_r003(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    paper_hits = _find_paper_lines(
        paper, ["dataset", "数据集", "cifar", "imagenet", "mnist"]
    )
    repo_hits = _find_repo_lines(
        repo, ["dataset", "数据集", "cifar", "imagenet", "mnist"]
    )
    if not paper_hits and not repo_hits:
        return _finding("R003", "missing", MISSING_TEXT)
    evidence = [
        _evidence_paper(page.page, line, text)
        for page, line, text in paper_hits[:2]
    ]
    evidence.extend(
        _evidence_file(file, line, text)
        for file, line, text in repo_hits[:2]
    )
    acquisition_terms = (
        "download", "下载", "data root", "dataset root", "数据来源",
        "数据地址", "数据路径", "dataset url", "dataset homepage",
    )
    data_terms = ("dataset", "data set", "数据集", "数据", "cifar", "imagenet", "mnist")
    download_hits = []
    for file, line_number, line in repo.matching_lines((*acquisition_terms, "http://", "https://")):
        lower = line.lower()
        has_acquisition = any(term in lower for term in acquisition_terms)
        has_data_context = any(term in lower for term in data_terms)
        # A generic paper, badge, issue, or project URL is not evidence that the
        # dataset can be obtained. URLs count only in an explicit data context.
        if _positive(line) and (has_acquisition or (has_data_context and "http" in lower)):
            download_hits.append((file, line_number, line.strip()))
    if download_hits:
        evidence.extend(_evidence_file(file, line, text) for file, line, text in download_hits[:2])
        return _finding("R003", "found", "找到数据集名称及来源或下载线索。", evidence[:5])
    return _finding("R003", "partial", "找到数据集名称，但未找到完整来源或下载方式。", evidence[:4])


def check_r004(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    preprocessing = _find_paper_lines(paper, ["preprocess", "预处理", "normaliz", "归一化", "augmentation", "增强"])
    preprocessing += _find_repo_lines(repo, ["preprocess", "预处理", "normaliz", "归一化", "augmentation", "增强"])
    split = _find_paper_lines(paper, ["train/val", "train/validation", "train/test", "划分", "split", "validation set"])
    split += _find_repo_lines(repo, ["train_test_split", "train/val", "train/test", "划分", "split", "validation"])
    evidence = []
    for match in preprocessing[:2]:
        if hasattr(match[0], "page"):
            evidence.append(_evidence_paper(match[0].page, match[1], match[2]))
        else:
            evidence.append(_evidence_file(match[0], match[1], match[2]))
    for match in split[:2]:
        if hasattr(match[0], "page"):
            evidence.append(_evidence_paper(match[0].page, match[1], match[2]))
        else:
            evidence.append(_evidence_file(match[0], match[1], match[2]))
    if preprocessing and split:
        return _finding("R004", "found", "找到预处理和数据划分相关说明。", evidence)
    if preprocessing or split:
        return _finding("R004", "partial", "只找到预处理或数据划分的部分说明。", evidence)
    return _finding("R004", "missing", MISSING_TEXT)


def check_r005(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    paper_hits = _find_paper_lines(paper, ["random seed", "random_state", "随机种子", "seed"])
    repo_hits = _find_repo_lines(repo, ["random.seed", "random_state", "manual_seed", "set_seed", "--seed"])
    evidence = [_evidence_paper(page.page, line, text) for page, line, text in paper_hits[:2]]
    evidence.extend(_evidence_file(file, line, text) for file, line, text in repo_hits[:2])
    if evidence:
        return _finding("R005", "found", "找到随机种子或随机状态设置。", evidence)
    return _finding("R005", "missing", MISSING_TEXT)


def check_r006(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    terms = ["learning rate", "lr", "学习率", "batch size", "batch_size", "批大小", "epoch", "优化器", "optimizer"]
    hits = _find_paper_lines(paper, terms)
    paper_evidence = [_evidence_paper(page.page, line, text) for page, line, text in hits[:4]]
    repo_hits = _find_repo_lines(repo, terms)
    repo_evidence = [_evidence_file(file, line, text) for file, line, text in repo_hits[:4]]
    all_evidence = paper_evidence + repo_evidence
    if not all_evidence:
        return _finding("R006", "missing", MISSING_TEXT)
    has_learning_rate = any("learning rate" in item.quote.lower() or "学习率" in item.quote for item in all_evidence)
    has_other = any(
        token in item.quote.lower()
        for item in all_evidence
        for token in ("batch", "epoch", "优化器", "optimizer", "批大小")
    )
    if has_learning_rate and has_other:
        return _finding("R006", "found", "找到主要训练超参数说明。", all_evidence[:6])
    return _finding("R006", "partial", "找到部分训练超参数，但仍有关键参数未明确。", all_evidence[:6])


def check_r007(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    terms = ["gpu", "cuda", "显存", "硬件", "hardware", "cpu", "运行环境", "environment"]
    hits = _find_paper_lines(paper, terms)
    evidence = [_evidence_paper(page.page, line, text) for page, line, text in hits[:3]]
    repo_hits = _find_repo_lines(repo, terms)
    evidence.extend(_evidence_file(file, line, text) for file, line, text in repo_hits[:3])
    if evidence:
        return _finding("R007", "found", "找到运行硬件或环境说明。", evidence)
    return _finding("R007", "missing", MISSING_TEXT)


def check_r008(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    command_pattern = re.compile(
        r"^\s*(?:[`$>]\s*)?(?:python(?:3)?|uv\s+run\s+python|poetry\s+run\s+python)\s+[^\s`]+\.py(?:\s|`|$)|"
        r"^\s*(?:[`$>]\s*)?make(?:\s+[\w.-]+)?(?:\s|`|$)",
        re.IGNORECASE,
    )
    command_hits = [
        (file, line, text)
        for file, line, text in _find_repo_lines(repo, ["python", "make"])
        if command_pattern.search(text)
    ]
    if command_hits:
        return _finding(
            "R008",
            "found",
            "找到可执行的实验入口命令。",
            [_evidence_file(file, line, text) for file, line, text in command_hits[:4]],
        )
    entry_files = repo.find_files("train.py", "evaluate.py", "eval.py", "main.py")
    if entry_files:
        return _finding(
            "R008",
            "partial",
            "找到可能的实验入口文件，但未找到可直接执行的命令。",
            [_evidence_file(entry_files[0], 1, entry_files[0].name)],
        )
    return _finding("R008", "missing", MISSING_TEXT)


def check_r009(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    metric_hits = _find_paper_lines(paper, ["accuracy", "准确率", "f1", "precision", "recall", "auc", "评价指标"])
    repo_metric_hits = _find_repo_lines(
        repo, ["accuracy", "准确率", "f1_score", "precision", "recall", "roc_auc", "metric"]
    )
    calc_hits = _find_repo_lines(
        repo, ["sklearn.metrics", "accuracy_score", "f1_score", "roc_auc_score", "evaluate.py"]
    )
    evidence = [
        _evidence_paper(page.page, line, text)
        for page, line, text in metric_hits[:3]
    ]
    evidence.extend(
        _evidence_file(file, line, text)
        for file, line, text in repo_metric_hits[:3]
    )
    evidence.extend(_evidence_file(file, line, text) for file, line, text in calc_hits[:3])
    if not metric_hits and not repo_metric_hits:
        return _finding("R009", "missing", MISSING_TEXT)
    if calc_hits:
        return _finding("R009", "found", "找到评价指标及其计算或评测入口。", evidence)
    return _finding("R009", "partial", "找到评价指标名称，但未定位到明确的计算实现。", evidence)


def check_r010(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    terms = [
        "outputs/", "output/", "results/", "result.json", "结果文件",
        "json.dump", "write_text", "write_csv", "to_csv", "torch.save", "savefig",
    ]
    hits = _find_repo_lines(repo, terms)
    evidence = [_evidence_file(file, line, text) for file, line, text in hits[:5]]
    if evidence:
        return _finding("R010", "found", "找到结果生成或输出位置。", evidence)
    return _finding("R010", "missing", MISSING_TEXT)


def check_r011(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    paper_text = paper.text.lower()
    candidates = []
    for term in ["tinycnn", "cifar-10", "imagenet", "mnist"]:
        if term in paper_text:
            candidates.append(term)
    evidence: list[Evidence] = []
    matched = 0
    for term in candidates:
        paper_hit = next((item for item in _find_paper_lines(paper, [term])), None)
        repo_hit = next((item for item in _find_repo_lines(repo, [term])), None)
        if paper_hit and repo_hit:
            matched += 1
            evidence.append(_evidence_paper(paper_hit[0].page, paper_hit[1], paper_hit[2]))
            evidence.append(_evidence_file(repo_hit[0], repo_hit[1], repo_hit[2]))
    if candidates and matched == len(candidates):
        return _finding("R011", "found", "论文中的关键模型或数据集名称可在仓库中定位。", evidence)
    if matched:
        return _finding("R011", "partial", "部分论文概念可以在仓库中定位，仍需人工确认。", evidence, confidence=0.78)
    return _finding("R011", "needs_review", "未能可靠建立论文术语与仓库内容的对应关系。", confidence=0.45)


def check_r012(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    terms = [
        "pretrained", "pre-trained", "预训练", "checkpoint", "model zoo",
        "load_state_dict", "torch.load", ".pth", ".ckpt",
    ]
    repo_hits = _find_repo_lines(repo, terms)
    evidence = [_evidence_file(file, line, text) for file, line, text in repo_hits[:4]]
    if evidence:
        return _finding("R012", "found", "找到预训练模型、检查点或外部权重相关说明。", evidence)
    return _finding("R012", "missing", MISSING_TEXT)


def check_r013(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    candidates = _find_repo_lines(repo, ["commit", "git rev", "release", "version", "版本", "sha"])
    version_pattern = re.compile(
        r"\b(?:commit|sha(?:-?1)?|git\s+rev(?:ision)?)\b[^\n]{0,24}\b[0-9a-f]{7,40}\b|"
        r"\b(?:version|release|tag)\s*[:=]?\s*v?\d+(?:\.\d+){1,3}\b|"
        r"(?:版本|发布版)\s*[:：]?\s*v?\d+(?:\.\d+){1,3}",
        re.IGNORECASE,
    )
    evidence = [
        _evidence_file(file, line, text)
        for file, line, text in candidates
        if version_pattern.search(text)
    ][:4]
    if evidence:
        return _finding("R013", "found", "找到明确的代码版本、提交号或发布标签。", evidence)
    return _finding("R013", "missing", MISSING_TEXT)


def check_r014(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    license_files = repo.find_name_prefix("license")
    resource_hits = []
    resource_terms = ("dataset", "data set", "数据集", "数据", "weights", "权重", "model", "模型")
    restriction_terms = (
        "license", "licence", "terms of use", "usage restriction",
        "redistribut", "non-commercial", "申请", "许可", "授权",
        "使用限制", "不得分发", "再分发",
    )
    for file in repo.files:
        if file in license_files:
            continue
        for line_number, line in enumerate(file.lines, start=1):
            lower = line.lower()
            if (
                _positive(line)
                and any(term in lower for term in resource_terms)
                and any(term in lower for term in restriction_terms)
            ):
                resource_hits.append((file, line_number, line.strip()))

    evidence = [
        _evidence_file(file, 1, file.name) for file in license_files[:1]
    ]
    evidence.extend(
        _evidence_file(file, line, text) for file, line, text in resource_hits[:3]
    )
    if license_files and resource_hits:
        return _finding(
            "R014",
            "found",
            "找到代码许可证，并找到数据集、模型或外部权重的许可或使用限制说明。",
            evidence,
        )
    if license_files:
        return _finding(
            "R014",
            "partial",
            "找到代码许可证，但未找到数据集、模型或外部权重的许可或使用限制说明。",
            evidence,
        )
    hits = _find_repo_lines(repo, ["license", "许可协议", "使用限制"])
    if hits:
        return _finding("R014", "partial", "找到许可证或使用限制文字，但未找到独立许可证文件。",
                        [_evidence_file(file, line, text) for file, line, text in hits[:3]])
    return _finding("R014", "missing", MISSING_TEXT)


def check_r015(paper: PaperDocument, repo: RepositorySnapshot) -> Finding:
    guide_files = [
        file
        for file in repo.files
        if any(term in file.name.lower() for term in ("troubleshoot", "faq", "known-issues"))
    ]
    hits = _find_repo_lines(
        repo,
        ["troubleshooting", "faq", "常见问题", "故障排除", "排障", "known issues", "常见报错"],
    )
    evidence = [_evidence_file(file, 1, file.name) for file in guide_files[:2]]
    evidence.extend(_evidence_file(file, line, text) for file, line, text in hits[:4])
    if evidence:
        return _finding(
            "R015",
            "found",
            "找到常见问题或排障说明。",
            evidence[:4],
        )
    return _finding("R015", "missing", MISSING_TEXT)


CHECKERS = [
    check_r001,
    check_r002,
    check_r005,
    check_r008,
    check_r010,
    check_r014,
    check_r003,
    check_r006,
    check_r007,
    check_r009,
    check_r012,
    check_r013,
    check_r004,
    check_r011,
    check_r015,
]


def run_checks(paper: PaperDocument, repo: RepositorySnapshot) -> list[Finding]:
    return [checker(paper, repo) for checker in CHECKERS]
