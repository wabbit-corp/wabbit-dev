from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_black
from dev.config import Project


class PythonBlackCheck(RepoCheck):
    order = 110

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_black(path, project)
