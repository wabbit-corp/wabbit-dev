from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_deptry
from dev.config import Project


class PythonDeptryCheck(RepoCheck):
    order = 300
    issue_types = qa_tool_issue_types("deptry")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_deptry(path, project)


__all__ = ["PythonDeptryCheck"]
