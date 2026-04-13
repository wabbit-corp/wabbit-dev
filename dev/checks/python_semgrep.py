from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_semgrep
from dev.config import Project


class PythonSemgrepCheck(RepoCheck):
    order = 320
    issue_types = qa_tool_issue_types("semgrep")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_semgrep(path, project)


__all__ = ["PythonSemgrepCheck"]
