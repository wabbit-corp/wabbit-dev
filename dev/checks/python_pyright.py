from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_pyright
from dev.config import Project


class PythonPyrightCheck(RepoCheck):
    order = 140
    issue_types = qa_tool_issue_types("pyright")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_pyright(path, project)


__all__ = ["PythonPyrightCheck"]
