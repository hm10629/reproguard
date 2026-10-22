"""Paper input readers with page-aware evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PaperExtractionError(RuntimeError):
    """Raised when a paper cannot be read or parsed."""


@dataclass(frozen=True)
class PaperPage:
    page: int
    text: str

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


@dataclass
class PaperDocument:
    path: Path
    pages: list[PaperPage]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)

    def iter_lines(self):
        for page in self.pages:
            for line_number, line in enumerate(page.lines, start=1):
                yield page, line_number, line


def _read_plain_text(path: Path) -> PaperDocument:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PaperExtractionError(
            f"无法按 UTF-8 读取论文文本: {path}"
        ) from exc
    return PaperDocument(path=path, pages=[PaperPage(page=1, text=text)])


def _read_pdf(path: Path) -> PaperDocument:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise PaperExtractionError(
            "读取 PDF 需要 pypdf。请先执行: python -m pip install -r requirements.txt"
        ) from exc

    try:
        pdf = PdfReader(path)
    except Exception as exc:
        raise PaperExtractionError(f"无法打开 PDF: {path}") from exc

    pages: list[PaperPage] = []
    try:
        for index, page in enumerate(pdf.pages, start=1):
            pages.append(PaperPage(page=index, text=page.extract_text() or ""))
    except Exception as exc:
        raise PaperExtractionError(f"无法提取 PDF 文本: {path}") from exc
    if not pages:
        raise PaperExtractionError(f"PDF 没有可读取的页面: {path}")
    return PaperDocument(path=path, pages=pages)


def load_paper(path: Path) -> PaperDocument:
    """Load TXT, Markdown, or PDF paper content."""

    path = Path(path)
    if not path.exists():
        raise PaperExtractionError(f"论文路径不存在: {path}")
    if not path.is_file():
        raise PaperExtractionError(f"论文路径不是文件: {path}")

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return _read_plain_text(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    raise PaperExtractionError(
        f"不支持的论文格式: {suffix or '(无扩展名)'}。支持 .txt、.md、.pdf"
    )
