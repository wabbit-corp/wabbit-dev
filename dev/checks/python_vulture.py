from __future__ import annotations

import os
from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_vulture
from dev.config import Project

_ENABLE_VULTURE_ENV = "PYTHON_QA_ENABLE_VULTURE"


class PythonVultureCheck(RepoCheck):
    order = 310
    issue_types = qa_tool_issue_types("vulture")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        if os.environ.get(_ENABLE_VULTURE_ENV, "").strip().lower() not in {"1", "true", "yes"}:
            return []
        return run_vulture(path, project)


__all__ = ["PythonVultureCheck"]
