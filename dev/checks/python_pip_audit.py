from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_pip_audit
from dev.config import Project


class PythonPipAuditCheck(RepoCheck):
    order = 340

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_pip_audit(path, project)


__all__ = ["PythonPipAuditCheck"]
