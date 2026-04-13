from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_ruff
from dev.config import Project


class PythonRuffCheck(RepoCheck):
    order = 100
    issue_types = qa_tool_issue_types("ruff")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_ruff(path, project)


__all__ = ["PythonRuffCheck"]
