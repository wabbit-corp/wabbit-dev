from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_ruff
from dev.config import Project


class PythonRuffCheck(RepoCheck):
    order = 100

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_ruff(path, project)
