from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, RepoCheck
from dev.checks.python_qa_common import run_coverage_xml
from dev.config import Project


class PythonCoverageXmlCheck(RepoCheck):
    order = 220

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        return run_coverage_xml(path, project)


__all__ = ["PythonCoverageXmlCheck"]
