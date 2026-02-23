from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.checks.base import RepoCheck, Issue
from dev.checks.python_qa_common import run_vulture


class PythonVultureCheck(RepoCheck):
    order = 310

    def check(self, path: Path, project: Any) -> list[Issue]:
        return run_vulture(path, project)
