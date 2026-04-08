from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, IssueType, RootCheck
from dev.config import Project

E_GITIGNORE_WITHOUT_REPO = IssueType(
    "E_GITIGNORE_WITHOUT_REPO",
    "Gitignore file found without a git repository.",
)


def _find_enclosing_repo_root(path: Path) -> Path | None:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


class GitignoreWithoutRepoCheck(RootCheck):
    """
    Report a selected root directory that contains a .gitignore file but is not
    inside a git repository.
    """

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del project
        if path.is_file():
            return []
        if not (path / ".gitignore").exists():
            return []
        if _find_enclosing_repo_root(path) is not None:
            return []
        return [E_GITIGNORE_WITHOUT_REPO.at(path)]


__all__ = [
    "E_GITIGNORE_WITHOUT_REPO",
    "GitignoreWithoutRepoCheck",
]
