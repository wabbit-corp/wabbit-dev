from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_bandit


class PythonBanditCheck(RepoCheck):
    order = 330

    def check(self, path: Path, project: Any) -> list[Issue]:
        return run_bandit(path, project)
