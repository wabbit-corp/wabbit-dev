from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_bandit
from dev.config import Project


class PythonBanditCheck(RepoCheck):
    order = 330
    issue_types = qa_tool_issue_types("bandit")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_bandit(path, project)


__all__ = ["PythonBanditCheck"]
