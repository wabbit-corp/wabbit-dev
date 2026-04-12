from __future__ import annotations

from pathlib import Path


def repo_template_root() -> Path:
    root = Path(__file__).resolve().parent / "assets" / "repo-template"
    if not root.is_dir():
        raise FileNotFoundError(f"Missing internal repo-template assets at {root}")
    return root


def repo_template_path(*parts: str) -> Path:
    return repo_template_root().joinpath(*parts)


__all__ = ["repo_template_path", "repo_template_root"]
