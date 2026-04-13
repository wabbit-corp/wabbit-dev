from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import qa_tool_issue_types, run_coverage_report
from dev.config import Project


class PythonCoverageReportCheck(RepoCheck):
    order = 210
    issue_types = qa_tool_issue_types("coverage_report")

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_coverage_report(path, project)


__all__ = ["PythonCoverageReportCheck"]
