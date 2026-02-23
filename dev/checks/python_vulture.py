from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_vulture
from dev.config import Project


class PythonVultureCheck(RepoCheck):
    order = 310

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_vulture(path, project)


__all__ = ["PythonVultureCheck"]
