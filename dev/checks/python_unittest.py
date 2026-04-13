from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_unittest
from dev.config import Project


class PythonUnittestCheck(RepoCheck):
    order = 240
    issue_types = qa_tool_issue_types("unittest")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_unittest(path, project)


__all__ = ["PythonUnittestCheck"]
