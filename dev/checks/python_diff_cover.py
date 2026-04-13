from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_diff_cover
from dev.config import Project


class PythonDiffCoverCheck(RepoCheck):
    order = 230
    issue_types = qa_tool_issue_types("diff_cover")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_diff_cover(path, project)


__all__ = ["PythonDiffCoverCheck"]
