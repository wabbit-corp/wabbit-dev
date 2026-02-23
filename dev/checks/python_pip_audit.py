from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_pip_audit


class PythonPipAuditCheck(RepoCheck):
    order = 340

    def check(self, path: Path, project: Any) -> list[Issue]:
        return run_pip_audit(path, project)
