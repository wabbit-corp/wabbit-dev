from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_mypy
from dev.config import Project


class PythonMypyCheck(RepoCheck):
    order = 130
    issue_types = qa_tool_issue_types("mypy")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_mypy(path, project)


__all__ = ["PythonMypyCheck"]
