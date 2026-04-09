from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import dev.io
from dev.config import Config, GradleProject, OwnershipType, Project, find_workspace_root, load_config
from dev.ignore_files import IgnoreMatcher

MONITORED_LEGAL_FILENAMES = frozenset(
    {
        "LICENSE.md",
        "NOTICE.md",
        "CLA.md",
        "CLA_EXPLANATIONS.md",
        "CONTRIBUTOR_PRIVACY.md",
        "CODE_OF_CONDUCT.md",
    }
)


@dataclass(frozen=True)
class ProjectLayout:
    project: Project
    repo_root: Path
    test_license_roots: tuple[Path, ...]
    expected_legal_paths: frozenset[Path]

    @property
    def writes_root_legal_files(self) -> bool:
        return self.project.path.resolve() == self.repo_root.resolve()


@dataclass(frozen=True)
class RepoLayout:
    repo_root: Path
    projects: tuple[Project, ...]
    expected_legal_paths: frozenset[Path]


def test_license_root_patterns(project: Project) -> tuple[str, ...]:
    if isinstance(project, GradleProject):
        return (
            "src/*Test",
            "src/test",
            "test",
            "tests",
        )
    return ("test", "tests")


def discover_test_license_roots(project: Project) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for pattern in test_license_root_patterns(project):
        for candidate in sorted(project.path.glob(pattern)):
            if not candidate.is_dir():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append(candidate)
    return roots


def expected_test_license_copy_paths(project: Project) -> list[Path]:
    if project.test_license is None:
        return []
    return [root / "LICENSE.md" for root in discover_test_license_roots(project)]


def build_project_layout(project: Project) -> ProjectLayout:
    repo_root = project.effective_repo_root.resolve()
    test_roots = tuple(discover_test_license_roots(project))
    expected_legal_paths = set(expected_test_license_copy_paths(project))
    if project.path.resolve() == repo_root:
        expected_legal_paths.update(
            {
                project.path / "LICENSE.md",
                project.path / "NOTICE.md",
                project.path / "legal" / "cla" / "v1.0.0" / "CLA.md",
                project.path / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md",
                project.path / "legal" / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md",
                project.path / "legal" / "code-of-conduct" / "v1.0.0" / "CODE_OF_CONDUCT.md",
            }
        )
    return ProjectLayout(
        project=project,
        repo_root=repo_root,
        test_license_roots=test_roots,
        expected_legal_paths=frozenset(path.resolve() for path in expected_legal_paths),
    )


def repo_projects_for_root(config: Config, repo_root: Path) -> list[Project]:
    repo_root = repo_root.resolve()
    return sorted(
        [
            project
            for project in config.defined_projects.values()
            if project.ownership == OwnershipType.WABBIT and project.effective_repo_root.resolve() == repo_root
        ],
        key=lambda project: (project.project_id or "", project.path.as_posix()),
    )


def wabbit_repo_projects(repo_root: Path) -> list[Project]:
    if find_workspace_root(repo_root) is None:
        return []
    config = load_config(repo_root)
    return repo_projects_for_root(config, repo_root)


def build_repo_layout(repo_root: Path, projects: list[Project]) -> RepoLayout:
    expected_legal_paths: set[Path] = set()
    for project in projects:
        expected_legal_paths.update(build_project_layout(project).expected_legal_paths)
    return RepoLayout(
        repo_root=repo_root.resolve(),
        projects=tuple(projects),
        expected_legal_paths=frozenset(expected_legal_paths),
    )


def find_misplaced_legal_files(repo_root: Path, projects: list[Project]) -> list[Path]:
    if not projects:
        return []
    repo_layout = build_repo_layout(repo_root, projects)
    matcher = IgnoreMatcher(repo_layout.repo_root)
    misplaced: list[Path] = []

    for current_root, dirnames, filenames in os.walk(repo_layout.repo_root):
        current_path = Path(current_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not matcher.matches(current_path / dirname, is_dir=True)
        ]
        for filename in filenames:
            if filename not in MONITORED_LEGAL_FILENAMES:
                continue
            candidate = current_path / filename
            if matcher.matches(candidate, is_dir=False):
                continue
            if candidate.resolve() in repo_layout.expected_legal_paths:
                continue
            misplaced.append(candidate)

    return sorted(misplaced)


def delete_path_and_empty_parents(path: Path, *, stop_at: Path) -> None:
    stop_at = stop_at.resolve()
    dev.io.delete_if_exists(path)
    current = path.parent
    while current != stop_at and current.exists():
        try:
            next(current.iterdir())
        except StopIteration:
            current.rmdir()
            current = current.parent
            continue
        break


def cleanup_misplaced_legal_files(repo_root: Path, projects: list[Project]) -> list[Path]:
    misplaced = find_misplaced_legal_files(repo_root, projects)
    for path in misplaced:
        delete_path_and_empty_parents(path, stop_at=repo_root)
    return misplaced
