from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_coverage_xml
from dev.config import Project


class PythonCoverageXmlCheck(RepoCheck):
    order = 220
    issue_types = qa_tool_issue_types("coverage_xml")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_coverage_xml(path, project)


__all__ = ["PythonCoverageXmlCheck"]
