from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_pyright


class PythonPyrightCheck(RepoCheck):
    order = 140

    def check(self, path: Path, project: Any) -> list[Issue]:
        return run_pyright(path, project)
