from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dev.config import Config, DotnetProject, GradleProject, Project, PythonProject, RepoDefinition


@dataclass(frozen=True)
class RepoDocsEntry:
    kind: str
    title: str
    description: str
    published_path: str
    relative_project_path: str | None = None
    relative_output_path: str | None = None
    gradle_task: str | None = None
    has_changelog_guard_script: bool = False
    has_generate_api_docs_script: bool = False
    has_docs_links_script: bool = False
    has_docs_snippets_test: bool = False


@dataclass(frozen=True)
class RepoDocsPlan:
    repo_id: str
    root_path: Path
    github_repo: str | None
    entries: list[RepoDocsEntry]
    needs_repo_workflows: bool
    needs_java: bool
    needs_python: bool
    needs_android: bool
    needs_dotnet: bool


def _sanitize_published_path(text: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-.")
    if sanitized:
        return sanitized
    return "docs"


def _repo_pages_url(repo_full_name: str) -> str | None:
    owner, _, repo_name = repo_full_name.partition("/")
    if not owner or not repo_name:
        return None
    return f"https://{owner}.github.io/{repo_name}/"


def _repo_projects(config: Config, repo_definition: RepoDefinition) -> list[Project]:
    projects: list[Project] = []
    for project_id in repo_definition.project_ids:
        project = config.defined_projects.get(project_id)
        if project is not None:
            projects.append(project)
    return projects


def _gradle_docs_task(project: GradleProject) -> str:
    if project.effective_gradle_root != project.path:
        return f":{project.effective_gradle_project_name}:dokkaGeneratePublicationHtml"
    return "dokkaGeneratePublicationHtml"


def _gradle_docs_output_path(root_path: Path, project: GradleProject) -> str:
    return project.path.joinpath("build", "dokka", "html").relative_to(root_path).as_posix()


def _supports_repo_docs_project(project: Project) -> bool:
    match project:
        case GradleProject():
            return project.docs_enabled and project.docs_system == "dokka"
        case DotnetProject():
            return project.docs_enabled and project.docs_system == "mkdocs"
        case PythonProject():
            return project.docs_enabled and project.docs_system == "mkdocs"
        case _:
            return False


def _project_docs_entry(root_path: Path, project: Project) -> RepoDocsEntry | None:
    default_description = project.description or f"Documentation for {project.name}."
    published_path = _sanitize_published_path(project.name)
    relative_project_path = project.path.relative_to(root_path).as_posix()

    match project:
        case GradleProject() if project.docs_enabled and project.docs_system == "dokka":
            return RepoDocsEntry(
                kind="gradle-dokka",
                title=project.name,
                description=default_description,
                published_path=published_path,
                relative_project_path=relative_project_path,
                relative_output_path=_gradle_docs_output_path(root_path, project),
                gradle_task=_gradle_docs_task(project),
            )
        case DotnetProject() if project.docs_enabled and project.docs_system == "mkdocs":
            return RepoDocsEntry(
                kind="dotnet-mkdocs",
                title=project.name,
                description=default_description,
                published_path=published_path,
                relative_project_path=relative_project_path,
                has_changelog_guard_script=(project.path / "scripts" / "check_changelog_guard.py").is_file(),
                has_generate_api_docs_script=(project.path / "scripts" / "generate_api_docs.py").is_file(),
                has_docs_links_script=(project.path / "scripts" / "check_docs_links.py").is_file(),
                has_docs_snippets_test=(project.path / "tests" / "test_docs_snippets.py").is_file(),
            )
        case PythonProject() if project.docs_enabled and project.docs_system == "mkdocs":
            return RepoDocsEntry(
                kind="python-mkdocs",
                title=project.name,
                description=default_description,
                published_path=published_path,
                relative_project_path=relative_project_path,
                has_changelog_guard_script=(project.path / "scripts" / "check_changelog_guard.py").is_file(),
                has_generate_api_docs_script=(project.path / "scripts" / "generate_api_docs.py").is_file(),
                has_docs_links_script=(project.path / "scripts" / "check_docs_links.py").is_file(),
                has_docs_snippets_test=(project.path / "tests" / "test_docs_snippets.py").is_file(),
            )
        case _:
            return None


def _has_repo_markdown_content(root_path: Path) -> bool:
    direct_candidates = (
        root_path / "README.md",
        root_path / "CHANGELOG.md",
        root_path / "NOTICE.md",
        root_path / "docs",
    )
    if any(candidate.exists() for candidate in direct_candidates):
        return True

    for child in root_path.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in {"build", ".gradle"}:
            continue
        if (child / "README.md").is_file() or (child / "CHANGELOG.md").is_file() or (child / "docs").is_dir():
            return True
    return False


def _repo_docs_plan_for_projects(
    *,
    repo_id: str,
    root_path: Path,
    github_repo: str | None,
    projects: list[Project],
) -> RepoDocsPlan:
    project_entries: list[RepoDocsEntry] = []
    for project in projects:
        entry = _project_docs_entry(root_path, project)
        if entry is not None:
            project_entries.append(entry)

    used_paths: set[str] = set()
    entries: list[RepoDocsEntry] = []
    for entry in project_entries:
        published_path = entry.published_path
        if published_path in used_paths:
            relative_project_path = entry.relative_project_path or entry.title
            published_path = _sanitize_published_path(relative_project_path.replace("/", "-"))
        used_paths.add(published_path)
        entries.append(
            RepoDocsEntry(
                kind=entry.kind,
                title=entry.title,
                description=entry.description,
                published_path=published_path,
                relative_project_path=entry.relative_project_path,
                relative_output_path=entry.relative_output_path,
                gradle_task=entry.gradle_task,
                has_changelog_guard_script=entry.has_changelog_guard_script,
                has_generate_api_docs_script=entry.has_generate_api_docs_script,
                has_docs_links_script=entry.has_docs_links_script,
                has_docs_snippets_test=entry.has_docs_snippets_test,
            )
        )

    project_paths = {
        entry.relative_project_path
        for entry in entries
        if entry.kind != "repo-markdown-site" and entry.relative_project_path is not None
    }
    has_gradle_docs = any(entry.kind == "gradle-dokka" for entry in entries)
    has_project_entries = bool(project_paths)
    needs_repo_workflows = has_project_entries and (
        has_gradle_docs or len(project_paths) > 1 or "." not in project_paths
    )
    if needs_repo_workflows and _has_repo_markdown_content(root_path):
        entries.insert(
            0,
            RepoDocsEntry(
                kind="repo-markdown-site",
                title="Guides",
                description="Repo guides, reference docs, and module notes.",
                published_path="docs",
            ),
        )
    needs_android = any(
        isinstance(project, GradleProject)
        and project.docs_enabled
        and project.docs_system == "dokka"
        and any(target.kind.startswith("android-") for target in project.targets)
        for project in projects
    )
    return RepoDocsPlan(
        repo_id=repo_id,
        root_path=root_path,
        github_repo=github_repo,
        entries=entries,
        needs_repo_workflows=needs_repo_workflows,
        needs_java=has_gradle_docs,
        needs_python=bool(entries),
        needs_android=needs_android,
        needs_dotnet=any(entry.kind == "dotnet-mkdocs" for entry in entries),
    )


def repo_docs_plan(config: Config, repo_definition: RepoDefinition) -> RepoDocsPlan:
    return _repo_docs_plan_for_projects(
        repo_id=repo_definition.repo_id,
        root_path=repo_definition.path,
        github_repo=repo_definition.github_repo,
        projects=_repo_projects(config, repo_definition),
    )


def repo_definition_docs_workflows_owned_by_repo(config: Config, repo_definition: RepoDefinition) -> bool:
    return repo_docs_plan(config, repo_definition).needs_repo_workflows


def standalone_project_repo_docs_plan(project: Project) -> RepoDocsPlan | None:
    match project:
        case GradleProject() if (
                project.docs_enabled
                and project.docs_system == "dokka"
                and project.github_repo is not None
                and project.effective_gradle_root == project.path
            ):
            return _repo_docs_plan_for_projects(
                repo_id=project.project_id or project.name,
                root_path=project.path,
                github_repo=project.github_repo,
                projects=[project],
            )
        case DotnetProject() if (
                project.docs_enabled
                and project.docs_system == "mkdocs"
                and project.github_repo is not None
        ):
            return _repo_docs_plan_for_projects(
                repo_id=project.project_id or project.name,
                root_path=project.path,
                github_repo=project.github_repo,
                projects=[project],
            )
        case _:
            return None


def repo_docs_workflows_owned_by_repo(config: Config, project: Project) -> bool:
    repo_id = project.repo_id
    if repo_id is None:
        standalone_plan = standalone_project_repo_docs_plan(project)
        if standalone_plan is None:
            return False
        return standalone_plan.needs_repo_workflows
    repo_definition = config.defined_repos.get(repo_id)
    if repo_definition is None:
        return False
    return repo_definition_docs_workflows_owned_by_repo(config, repo_definition)


def project_repo_docs_published_path(config: Config, project: Project) -> str | None:
    repo_id = project.repo_id
    if repo_id is None:
        return None
    repo_definition = config.defined_repos.get(repo_id)
    if repo_definition is None:
        return None
    for entry in repo_docs_plan(config, repo_definition).entries:
        if entry.relative_project_path != project.path.relative_to(repo_definition.path).as_posix():
            continue
        if entry.kind == "repo-markdown-site":
            continue
        return entry.published_path
    return None


def repo_docs_site_url(config: Config, project: Project) -> str | None:
    repo_id = project.repo_id
    if repo_id is None:
        return None
    repo_definition = config.defined_repos.get(repo_id)
    if repo_definition is None or repo_definition.github_repo is None:
        return None
    base_url = _repo_pages_url(repo_definition.github_repo)
    if base_url is None:
        return None
    if not repo_docs_workflows_owned_by_repo(config, project):
        return base_url
    published_path = project_repo_docs_published_path(config, project)
    if published_path is None:
        return base_url
    return f"{base_url}{published_path}/"


__all__ = [
    "RepoDocsEntry",
    "RepoDocsPlan",
    "project_repo_docs_published_path",
    "repo_definition_docs_workflows_owned_by_repo",
    "repo_docs_plan",
    "repo_docs_site_url",
    "repo_docs_workflows_owned_by_repo",
    "standalone_project_repo_docs_plan",
]
