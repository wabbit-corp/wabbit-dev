from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_black
from dev.config import Project


class PythonBlackCheck(RepoCheck):
    order = 110
    issue_types = qa_tool_issue_types("black")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_black(path, project)


__all__ = ["PythonBlackCheck"]
