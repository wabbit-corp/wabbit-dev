from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_import_linter
from dev.config import Project


class PythonImportLinterCheck(RepoCheck):
    order = 120
    issue_types = qa_tool_issue_types("import_linter")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_import_linter(path, project)


__all__ = ["PythonImportLinterCheck"]
