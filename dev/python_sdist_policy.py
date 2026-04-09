from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SDIST_INCLUDED_DIR_NAMES = {
    "LICENSES",
    "docs",
    "examples",
    "example",
    "legal",
    "release-checklist",
    "scripts",
    "test",
    "tests",
}

_SDIST_INCLUDED_FILE_SUFFIXES = {
    ".cfg",
    ".ini",
    ".jpg",
    ".json",
    ".md",
    ".mu",
    ".png",
    ".py",
    ".rst",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

_SDIST_INCLUDED_HIDDEN_FILE_NAMES = {
    ".banner.png",
    ".checkignore",
    ".codespell-ignore-words.txt",
    ".entropyignore",
}

_SDIST_EXCLUDE_PATTERNS = [
    ".coverage",
    ".coverage.*",
    ".llm",
    ".llm/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    ".venv",
    ".venv/**",
    "__pycache__",
    "__pycache__/**",
    "build",
    "build/**",
    "dist",
    "dist/**",
    "docs-research",
    "docs-research/**",
    "pyproject.toml.bak",
    "site",
    "site/**",
    "tmp",
    "tmp/**",
    "tmp-*",
    "tmp-*/**",
]

_CHECK_MANIFEST_IGNORE_PATTERNS = [
    *list(_SDIST_EXCLUDE_PATTERNS),
    ".DS_Store",
    ".editorconfig",
    ".github",
    ".github/**",
    ".gitignore",
    "AGENTS.md",
]


@dataclass(frozen=True)
class PythonSdistIncludeEntry:
    path: str
    formats: tuple[str, ...] = ("sdist",)


def _sorted_unique_patterns(patterns: list[str]) -> list[str]:
    return sorted(set(patterns))


def python_sdist_include_entries(project_path: Path) -> list[PythonSdistIncludeEntry]:
    entries: list[PythonSdistIncludeEntry] = []
    if not project_path.exists():
        return entries

    for child in sorted(project_path.iterdir(), key=lambda path: path.name.casefold()):
        name = child.name
        if child.is_dir():
            if name in _SDIST_INCLUDED_DIR_NAMES:
                entries.append(PythonSdistIncludeEntry(path=name))
            continue

        if not child.is_file():
            continue

        if name in _SDIST_INCLUDED_HIDDEN_FILE_NAMES or child.suffix.lower() in _SDIST_INCLUDED_FILE_SUFFIXES:
            entries.append(PythonSdistIncludeEntry(path=name))

    return entries


def python_sdist_exclude_patterns(_project_path: Path) -> list[str]:
    return _sorted_unique_patterns(list(_SDIST_EXCLUDE_PATTERNS))


def python_check_manifest_ignore_patterns(project_path: Path) -> list[str]:
    del project_path
    return _sorted_unique_patterns(list(_CHECK_MANIFEST_IGNORE_PATTERNS))


__all__ = [
    "PythonSdistIncludeEntry",
    "python_check_manifest_ignore_patterns",
    "python_sdist_exclude_patterns",
    "python_sdist_include_entries",
]
