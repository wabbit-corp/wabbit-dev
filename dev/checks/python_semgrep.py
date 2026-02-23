from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_semgrep
from dev.config import Project


class PythonSemgrepCheck(RepoCheck):
    order = 320

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_semgrep(path, project)


__all__ = ["PythonSemgrepCheck"]
