from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_import_linter


class PythonImportLinterCheck(RepoCheck):
    order = 120

    def check(self, path: Path, project: Any) -> list[Issue]:
        return run_import_linter(path, project)
