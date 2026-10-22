"""Local repository scanner used as the deterministic evidence source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "outputs",
    "checkpoints",
}

ALLOWED_SUFFIXES = {
    ".py",
    ".sh",
    ".bat",
    ".ps1",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
    ".md",
}

SPECIAL_FILENAMES = {
    "dockerfile",
    "makefile",
    "requirements.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "setup.py",
}


class RepositoryScanError(RuntimeError):
    """Raised when a repository cannot be scanned."""


@dataclass(frozen=True)
class RepositoryFile:
    relative_path: str
    text: str
    size: int

    @property
    def name(self) -> str:
        return Path(self.relative_path).name

    @property
    def suffix(self) -> str:
        return Path(self.relative_path).suffix.lower()

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    def line_evidence(self, line_number: int) -> tuple[str, int]:
        lines = self.lines
        if not lines:
            return "", line_number
        index = max(1, min(line_number, len(lines))) - 1
        return lines[index].strip(), index + 1


@dataclass
class RepositorySnapshot:
    root: Path
    files: list[RepositoryFile]
    skipped_files: list[str]

    @property
    def text(self) -> str:
        return "\n".join(item.text for item in self.files)

    def find_files(self, *names: str) -> list[RepositoryFile]:
        wanted = {name.lower() for name in names}
        return [
            item for item in self.files if item.name.lower() in wanted
        ]

    def find_name_prefix(self, prefix: str) -> list[RepositoryFile]:
        return [
            item
            for item in self.files
            if item.name.lower().startswith(prefix.lower())
        ]

    def matching_lines(self, terms: Iterable[str]):
        lowered_terms = [term.lower() for term in terms]
        for item in self.files:
            for line_number, line in enumerate(item.lines, start=1):
                lower_line = line.lower()
                if any(term in lower_line for term in lowered_terms):
                    yield item, line_number, line.strip()


def _is_candidate(path: Path) -> bool:
    name = path.name.lower()
    return name in SPECIAL_FILENAMES or name.startswith("readme") or name.startswith(
        "license"
    ) or path.suffix.lower() in ALLOWED_SUFFIXES


def scan_repository(
    root: Path,
    *,
    max_file_size: int = 2 * 1024 * 1024,
    ignored_dirs: set[str] | None = None,
) -> RepositorySnapshot:
    """Scan text-like research files while preserving relative paths."""

    root = Path(root)
    if not root.exists():
        raise RepositoryScanError(f"代码仓库路径不存在: {root}")
    if not root.is_dir():
        raise RepositoryScanError(f"代码仓库路径不是目录: {root}")

    ignored = ignored_dirs or DEFAULT_IGNORED_DIRS
    files: list[RepositoryFile] = []
    skipped: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in {item.lower() for item in ignored} for part in relative.parts):
            skipped.append(relative.as_posix())
            continue
        if not _is_candidate(path):
            skipped.append(relative.as_posix())
            continue
        size = path.stat().st_size
        if size > max_file_size:
            skipped.append(f"{relative.as_posix()} (too large)")
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            skipped.append(f"{relative.as_posix()} (not readable text)")
            continue
        files.append(
            RepositoryFile(
                relative_path=relative.as_posix(),
                text=text,
                size=size,
            )
        )

    return RepositorySnapshot(root=root, files=files, skipped_files=skipped)
