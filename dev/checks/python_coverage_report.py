from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_coverage_report
from dev.config import Project


class PythonCoverageReportCheck(RepoCheck):
    order = 210

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_coverage_report(path, project)
