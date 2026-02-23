from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_mypy
from dev.config import Project


class PythonMypyCheck(RepoCheck):
    order = 130

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_mypy(path, project)


__all__ = ["PythonMypyCheck"]
