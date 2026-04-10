from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import dev.io
from dev.checks.base import CoarseFileScope
from dev.config import Config, GradleProject, OwnershipType, Project, find_workspace_root, load_config
from dev.generated_files import is_setup_managed_file
from dev.ignore_files import IgnoreMatcher
from dev.licenses import canonicalize_license_key

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

_TMP_NAME_RE = re.compile(r"^\.?tmp(?:$|[._-].+)$")


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


def expected_extra_license_paths(project: Project) -> list[Path]:
    if project.test_license is None:
        return []
    if project.path.resolve() != project.effective_repo_root.resolve():
        return []
    normalized = canonicalize_license_key(project.test_license) or project.test_license
    safe_name = normalized.replace("/", "-").replace("\\", "-")
    return [project.path / "LICENSES" / f"{safe_name}.md"]


def build_project_layout(project: Project) -> ProjectLayout:
    repo_root = project.effective_repo_root.resolve()
    test_roots = tuple(discover_test_license_roots(project))
    expected_legal_paths = set(expected_test_license_copy_paths(project))
    expected_legal_paths.update(expected_extra_license_paths(project))
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


def expected_repo_root_legal_paths(repo_root: Path, projects: Sequence[Project]) -> set[Path]:
    expected_paths = {
        repo_root / "LICENSE.md",
        repo_root / "legal" / "cla" / "v1.0.0" / "CLA.md",
        repo_root / "legal" / "cla" / "v1.0.0" / "CLA_EXPLANATIONS.md",
        repo_root / "legal" / "contributor-privacy" / "v1.0.0" / "CONTRIBUTOR_PRIVACY.md",
        repo_root / "legal" / "code-of-conduct" / "v1.0.0" / "CODE_OF_CONDUCT.md",
    }
    for project in projects:
        expected_paths.update(expected_extra_license_paths(project))
        if project.test_license is not None:
            expected_paths.add(repo_root / "NOTICE.md")
    return expected_paths


class SetupOwnedPathMatcher:
    def __init__(self, repo_root: Path, *, projects: list[Project] | None = None) -> None:
        self.repo_root = repo_root.resolve()
        if projects is None:
            projects = wabbit_repo_projects(self.repo_root)
        self.repo_layout = build_repo_layout(self.repo_root, projects) if projects else None
        self._managed_file_cache: dict[Path, bool] = {}
        self._managed_dir_cache: dict[Path, bool] = {}

    def _normalize_path(self, path: Path | str) -> Path:
        absolute_path = Path(path)
        if not absolute_path.is_absolute():
            absolute_path = absolute_path.absolute()
        return absolute_path.resolve()

    def _is_setup_owned_file(self, absolute_path: Path) -> bool:
        if self.repo_layout is not None and absolute_path in self.repo_layout.expected_legal_paths:
            return True

        if not absolute_path.is_file():
            return False

        cached = self._managed_file_cache.get(absolute_path)
        if cached is not None:
            return cached

        is_managed = is_setup_managed_file(absolute_path)
        self._managed_file_cache[absolute_path] = is_managed
        return is_managed

    def _is_setup_owned_dir(self, absolute_path: Path) -> bool:
        cached = self._managed_dir_cache.get(absolute_path)
        if cached is not None:
            return cached

        if not absolute_path.is_dir():
            self._managed_dir_cache[absolute_path] = False
            return False

        try:
            children = sorted(absolute_path.iterdir())
        except OSError:
            self._managed_dir_cache[absolute_path] = False
            return False

        if not children:
            self._managed_dir_cache[absolute_path] = False
            return False

        for child in children:
            if child.is_dir():
                if not self._is_setup_owned_dir(child):
                    self._managed_dir_cache[absolute_path] = False
                    return False
            elif not self._is_setup_owned_file(child):
                self._managed_dir_cache[absolute_path] = False
                return False

        self._managed_dir_cache[absolute_path] = True
        return True

    def matches(self, path: Path | str, *, is_dir: bool) -> bool:
        absolute_path = self._normalize_path(path)

        try:
            absolute_path.relative_to(self.repo_root)
        except ValueError:
            return False

        if is_dir:
            return self._is_setup_owned_dir(absolute_path)
        return self._is_setup_owned_file(absolute_path)

    def __call__(self, path: Path | str, is_dir: bool) -> bool:
        return self.matches(path, is_dir=is_dir)


def build_content_ignore_matcher(
    root: Path,
    *,
    project: Project | None = None,
    projects: list[Project] | None = None,
) -> IgnoreMatcher:
    if projects is None:
        projects = [project] if project is not None else None

    repo_root = project.effective_repo_root if project is not None else root
    return IgnoreMatcher(
        root,
        extra_predicates=(
            TransientPathMatcher(repo_root, projects=projects),
            SetupOwnedPathMatcher(repo_root, projects=projects),
        ),
    )


class TransientPathMatcher:
    def __init__(self, repo_root: Path, *, projects: list[Project] | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.projects = tuple(projects or [])

    def _normalize_path(self, path: Path | str) -> Path:
        absolute_path = Path(path)
        if not absolute_path.is_absolute():
            absolute_path = absolute_path.absolute()
        return absolute_path.resolve()

    def _matches_tmp_name(self, name: str) -> bool:
        return bool(_TMP_NAME_RE.fullmatch(name))

    def _is_project_build_temp(self, absolute_path: Path) -> bool:
        for project in self.projects:
            try:
                if not absolute_path.is_relative_to(project.path):
                    continue
            except ValueError:
                continue
            try:
                return project.get_coarse_file_scope(absolute_path) == CoarseFileScope.BUILD_TEMP
            except ValueError:
                continue
        return False

    def matches(self, path: Path | str, *, is_dir: bool) -> bool:
        absolute_path = self._normalize_path(path)
        try:
            relative = absolute_path.relative_to(self.repo_root)
        except ValueError:
            return False

        if any(self._matches_tmp_name(part) for part in relative.parts):
            return True

        name = absolute_path.name
        if not is_dir and (name.endswith(".bak") or self._matches_tmp_name(name)):
            return True

        return self._is_project_build_temp(absolute_path)

    def __call__(self, path: Path | str, is_dir: bool) -> bool:
        return self.matches(path, is_dir=is_dir)


def build_check_ignore_matcher(
    root: Path,
    *,
    project: Project | None = None,
    projects: list[Project] | None = None,
) -> IgnoreMatcher:
    if projects is None:
        projects = [project] if project is not None else None

    repo_root = project.effective_repo_root if project is not None else root
    return IgnoreMatcher(
        root,
        extra_predicates=(TransientPathMatcher(repo_root, projects=projects),),
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


def build_repo_layout(repo_root: Path, projects: Sequence[Project]) -> RepoLayout:
    expected_legal_paths: set[Path] = expected_repo_root_legal_paths(repo_root, projects)
    for project in projects:
        expected_legal_paths.update(build_project_layout(project).expected_legal_paths)
    return RepoLayout(
        repo_root=repo_root.resolve(),
        projects=tuple(projects),
        expected_legal_paths=frozenset(expected_legal_paths),
    )


def find_misplaced_legal_files(repo_root: Path, projects: Sequence[Project]) -> list[Path]:
    if not projects:
        return []
    repo_layout = build_repo_layout(repo_root, projects)
    matcher = IgnoreMatcher(repo_layout.repo_root)
    misplaced: list[Path] = []

    for current_root, dirnames, filenames in os.walk(repo_layout.repo_root):
        current_path = Path(current_root)
        dirnames[:] = [dirname for dirname in dirnames if not matcher.matches(current_path / dirname, is_dir=True)]
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


def cleanup_misplaced_legal_files(repo_root: Path, projects: Sequence[Project]) -> list[Path]:
    misplaced = find_misplaced_legal_files(repo_root, projects)
    for path in misplaced:
        delete_path_and_empty_parents(path, stop_at=repo_root)
    return misplaced
