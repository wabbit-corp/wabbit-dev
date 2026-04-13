from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_pip_audit
from dev.config import Project


class PythonPipAuditCheck(RepoCheck):
    order = 340
    issue_types = qa_tool_issue_types("pip_audit")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_pip_audit(path, project)


__all__ = ["PythonPipAuditCheck"]
