"""
Checks for stale or misplaced repo files left behind by layout migrations.
"""

from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, IssueType, RepoCheck
from dev.config import Project
from dev.project_layout import cleanup_misplaced_legal_files, find_misplaced_legal_files, wabbit_repo_projects

E_MISPLACED_LEGAL_FILE = IssueType(
    "E_MISPLACED_LEGAL_FILE",
    "Legal file is in the wrong location: {relative_path}.",
)


class RepoLegalLayoutMigrationCheck(RepoCheck):
    """
    Detect stale nested legal files that should live only at the repo root,
    under `legal/`, or in explicit test-license directories.
    """

    order = 70

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del project
        repo_root = path.resolve()
        projects = wabbit_repo_projects(repo_root)
        if not projects:
            return []

        issues: list[Issue] = []
        for misplaced in find_misplaced_legal_files(repo_root, projects):
            relative_path = misplaced.relative_to(repo_root).as_posix()
            issues.append(
                E_MISPLACED_LEGAL_FILE.make(relative_path=relative_path).at(misplaced).fixable(
                    lambda repo_root=repo_root, projects=projects: cleanup_misplaced_legal_files(repo_root, projects)
                )
            )
        return issues


__all__ = [
    "E_MISPLACED_LEGAL_FILE",
    "RepoLegalLayoutMigrationCheck",
]
