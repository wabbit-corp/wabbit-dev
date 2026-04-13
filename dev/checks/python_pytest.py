from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_pytest
from dev.config import Project


class PythonPytestCheck(RepoCheck):
    order = 200
    issue_types = qa_tool_issue_types("pytest")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_pytest(path, project)


__all__ = ["PythonPytestCheck"]
