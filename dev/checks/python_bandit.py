from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_bandit
from dev.config import Project


class PythonBanditCheck(RepoCheck):
    order = 330

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_bandit(path, project)


__all__ = ["PythonBanditCheck"]
