from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from dev.base import Scope
from dev.build_order import toposort_projects
from dev.config import Project, load_config, project_repo_root
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, info, muted, warning
from dev.repo_resolution import resolve_project_ids
from dev.tasks.setup import (
    RepoSetupMode,
    commit_repo_changes,
    create_repo_setup_context,
    setup_project,
)


@dataclass
class RepoCommitPlan:
    repo_root: Path
    projects: list[Project] = field(default_factory=list)
    repo: Repo | None = None


def _repo_key(repo: Repo) -> str | None:
    if repo.working_tree_dir is None:
        return None
    return str(repo.working_tree_dir)


def _resolve_target_projects(projects: str | list[str] | None = None) -> tuple[object, list[str] | None]:
    config = load_config()
    requested_projects = [projects] if isinstance(projects, str) else projects
    selected_project_names: list[str] | None = None
    if requested_projects:
        selected_project_names = resolve_project_ids(config, requested_projects)
    return config, selected_project_names


def _build_repo_plans(order: list[str], *, config: object) -> dict[str, RepoCommitPlan]:
    repo_plans: dict[str, RepoCommitPlan] = {}
    defined_projects = config.defined_projects
    for name in order:
        project = defined_projects[name]
        repo_root = project_repo_root(project)
        key = str(repo_root.resolve())
        if key not in repo_plans:
            repo_plans[key] = RepoCommitPlan(repo_root=repo_root, projects=[project])
        else:
            repo_plans[key].projects.append(project)
    return repo_plans


def commit(projects: str | list[str] | None = None, *, dry_run: bool = False) -> int:
    with Scope() as scope:
        try:
            config, selected_project_names = _resolve_target_projects(projects)
        except ValueError as ex:
            requested_projects = [projects] if isinstance(projects, str) else list(projects or [])
            error(contextualize_failure(str(ex), ["commit", *requested_projects]))
            return 1

        if getattr(config, "openai_key", None) is None:
            if dry_run:
                warning("OpenAI key is not configured. A real commit run would fail before generating messages.")
            else:
                error("OpenAI key is required to generate commit messages.")
                return 1

        order = toposort_projects(config.defined_projects, target_project=selected_project_names)
        if not order:
            if selected_project_names is None:
                error("No projects found for commit")
            else:
                error("No projects found for commit target(s): " + ", ".join(selected_project_names))
            return 1

        repo_plans = _build_repo_plans(order, config=config)

        if dry_run:
            info("Dry run: would run PROD setup for:\n  " + ", ".join(accent(name) for name in order))
            info(f"Dry run: would create commits for {len(repo_plans)} repository/repositories")
            for plan in repo_plans.values():
                print(
                    f"  {muted(plan.repo_root)}: "
                    + ", ".join(accent(project.name) for project in plan.projects)
                )
            return 0

        setup_context = create_repo_setup_context(config, RepoSetupMode.PROD)
        info("Running PROD setup before commit:\n  " + ", ".join(accent(name) for name in order))
        for name in order:
            project = config.defined_projects[name]
            setup_project(setup_context, project, interactive=False, commit_changes=False, allow_push=False)

        ready_plans_by_key: dict[str, RepoCommitPlan] = {}
        for plan in repo_plans.values():
            representative = plan.projects[0]
            try:
                repo = Repo(plan.repo_root)
            except (InvalidGitRepositoryError, NoSuchPathError) as ex:
                error(f"Skipping commit for {representative.name}: failed to open repository ({ex})")
                continue
            scope.defer(repo.close)

            key = _repo_key(repo)
            if key is None:
                error(f"Skipping commit for {representative.name}: repository has no working tree")
                continue
            existing = ready_plans_by_key.get(key)
            if existing is None:
                plan.repo = repo
                ready_plans_by_key[key] = plan
            else:
                existing.projects.extend(plan.projects)
                repo.close()

        ready_plans = list(ready_plans_by_key.values())
        if not ready_plans:
            error("No git repositories found to commit.")
            return 1

        info(f"Committing changes for {len(ready_plans)} repository/repositories")
        for plan in ready_plans:
            representative = next((proj for proj in plan.projects if not proj.quarantine), plan.projects[0])
            assert plan.repo is not None
            commit_repo_changes(
                project=representative,
                repo=plan.repo,
                openai_key=config.openai_key,
                interactive=False,
                add_files=True,
            )

    return 0
