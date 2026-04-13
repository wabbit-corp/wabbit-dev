"""
Check for duplicate files and duplicate directory trees by reusing the shared duplicates task logic.
"""

from __future__ import annotations

from pathlib import Path

from dev.checks.base import Issue, IssueType, RepoCheck
from dev.config import Project
from dev.project_layout import build_content_ignore_matcher
from dev.tasks.duplicates import FileGroup, TreeGroup, find_duplicates

E_DUPLICATE_FILE = IssueType(
    "E_DUPLICATE_FILE",
    "Duplicate files found ({duplicate_count} copies): {duplicate_paths}.",
)
E_DUPLICATE_DIRECTORY_TREE = IssueType(
    "E_DUPLICATE_DIRECTORY_TREE",
    "Duplicate directory trees found ({duplicate_count} copies): {duplicate_paths}.",
)


def _join_paths(paths: list[str]) -> str:
    return ", ".join(paths)


def _make_file_issue(group: FileGroup) -> Issue:
    anchor_path = Path(group.files[0])
    per_file_size = group.total_size // max(group.total_count, 1)
    return E_DUPLICATE_FILE.make(
        duplicate_count=group.total_count,
        duplicate_paths=_join_paths(group.files),
        total_size=group.total_size,
        per_file_size=per_file_size,
        other_paths=group.files[1:],
    ).at(anchor_path)


def _make_tree_issue(group: TreeGroup) -> Issue:
    anchor_path = Path(group.paths[0])
    return E_DUPLICATE_DIRECTORY_TREE.make(
        duplicate_count=group.total_count,
        duplicate_paths=_join_paths(group.paths),
        tree_size=group.tree_size,
        file_count=group.file_count,
        directory_count=group.directory_count,
        match_kind=group.match_kind,
        other_paths=group.paths[1:],
    ).at(anchor_path)


class DuplicateFilesCheck(RepoCheck):
    order = 70
    issue_types = (E_DUPLICATE_FILE, E_DUPLICATE_DIRECTORY_TREE)

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        report = find_duplicates(
            [str(path)],
            ignore_path=build_content_ignore_matcher(path, project=project),
        )

        issues = [_make_tree_issue(group) for group in report.tree_groups]
        issues.extend(_make_file_issue(group) for group in report.file_groups)
        return issues


__all__ = [
    "DuplicateFilesCheck",
    "E_DUPLICATE_DIRECTORY_TREE",
    "E_DUPLICATE_FILE",
]
