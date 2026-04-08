from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev.config import CodeOwner, Config, OwnershipType, Project, project_repo_root

DEFAULT_EDITORCONFIG_LINE_LENGTH = 120


@dataclass(frozen=True)
class RepoMetadataPlan:
    repo_root: Path
    github_repo: str | None
    code_owners: tuple[CodeOwner, ...]
    editorconfig_line_length: int
    requires_editorconfig: bool
    requires_github_metadata: bool
    requires_ci_workflows: bool


def _coerce_line_length(value: int | str | None) -> int:
    if value is None:
        return DEFAULT_EDITORCONFIG_LINE_LENGTH
    if isinstance(value, int):
        return value
    normalized = value.strip()
    if normalized.isdigit():
        return int(normalized)
    raise ValueError(f"python-defaults.line-length must be an integer, got {value!r}")


def repo_projects_for_root(config: Config, repo_root: Path) -> list[Project]:
    resolved_root = repo_root.resolve()
    return sorted(
        [
            project
            for project in config.defined_projects.values()
            if project_repo_root(project).resolve() == resolved_root
        ],
        key=lambda project: (
            project.project_id or "",
            project.path.as_posix(),
        ),
    )


def repo_github_repo(config: Config, repo_root: Path, projects: list[Project]) -> str | None:
    resolved_root = repo_root.resolve()
    for repo_definition in config.defined_repos.values():
        if repo_definition.path.resolve() == resolved_root:
            return repo_definition.github_repo
    for project in projects:
        if project.github_repo is not None:
            return project.github_repo
    return None


def build_repo_metadata_plan(
    config: Config,
    repo_root: Path,
    projects: list[Project] | None = None,
) -> RepoMetadataPlan | None:
    repo_projects = projects if projects is not None else repo_projects_for_root(config, repo_root)
    if not repo_projects:
        return None

    managed_projects = [project for project in repo_projects if project.ownership == OwnershipType.WABBIT]
    if not managed_projects:
        return None

    github_repo = repo_github_repo(config, repo_root, repo_projects)
    requires_ci_workflows = github_repo is not None and any(
        not project.quarantine and (project.publish or project.docs_enabled)
        for project in managed_projects
    )

    return RepoMetadataPlan(
        repo_root=repo_root.resolve(),
        github_repo=github_repo,
        code_owners=tuple(config.default_code_owners),
        editorconfig_line_length=_coerce_line_length(config.python_defaults.line_length),
        requires_editorconfig=True,
        requires_github_metadata=github_repo is not None,
        requires_ci_workflows=requires_ci_workflows,
    )


def expected_repo_metadata_paths(plan: RepoMetadataPlan) -> list[Path]:
    paths: list[Path] = []
    if plan.requires_editorconfig:
        paths.append(plan.repo_root / ".editorconfig")
    if not plan.requires_github_metadata:
        return paths

    github_root = plan.repo_root / ".github"
    if plan.code_owners:
        paths.append(github_root / "CODEOWNERS")
    paths.extend(
        [
            github_root / "SECURITY.md",
            github_root / "pull_request_template.md",
            github_root / "ISSUE_TEMPLATE" / "bug_report.yml",
            github_root / "ISSUE_TEMPLATE" / "feature_request.yml",
        ]
    )
    return paths


__all__ = [
    "DEFAULT_EDITORCONFIG_LINE_LENGTH",
    "RepoMetadataPlan",
    "build_repo_metadata_plan",
    "expected_repo_metadata_paths",
    "repo_github_repo",
    "repo_projects_for_root",
]
