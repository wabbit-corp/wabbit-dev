from __future__ import annotations

from dataclasses import dataclass, field

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from dev.base import Scope
from dev.build_order import toposort_projects
from dev.config import Project, load_config
from dev.messages import error, info
from dev.tasks.setup import (
    RepoSetupMode,
    commit_repo_changes,
    create_repo_setup_context,
    setup_project,
)


@dataclass
class RepoCommitPlan:
    repo: Repo
    projects: list[Project] = field(default_factory=list)


def _repo_key(repo: Repo) -> str | None:
    if repo.working_tree_dir is None:
        return None
    return str(repo.working_tree_dir)


def commit(project_name: str | None = None) -> None:
    with Scope() as scope:
        config = load_config()
        if project_name is not None and project_name not in config.defined_projects:
            error(f"Project {project_name} is not defined in the config")
            return

        if config.openai_key is None:
            error("OpenAI key is required to generate commit messages.")
            return

        order = toposort_projects(config.defined_projects, target_project=project_name)
        if not order:
            if project_name is None:
                error("No projects found for commit")
            else:
                error(f"No projects found for commit target {project_name}")
            return

        setup_context = create_repo_setup_context(config, RepoSetupMode.PROD)
        repo_plans: dict[str, RepoCommitPlan] = {}

        info("Running PROD setup before commit:\n  " + ", ".join(order))
        for name in order:
            project = config.defined_projects[name]
            setup_project(setup_context, project, interactive=False, commit_changes=False, allow_push=False)

            try:
                repo = Repo(project.path)
            except (InvalidGitRepositoryError, NoSuchPathError) as ex:
                error(f"Skipping commit for {project.name}: failed to open repository ({ex})")
                continue
            scope.defer(repo.close)

            key = _repo_key(repo)
            if key is None:
                error(f"Skipping commit for {project.name}: repository has no working tree")
                continue

            if key not in repo_plans:
                repo_plans[key] = RepoCommitPlan(repo=repo, projects=[project])
            else:
                repo_plans[key].projects.append(project)

        if not repo_plans:
            error("No git repositories found to commit.")
            return

        info(f"Committing changes for {len(repo_plans)} repository/repositories")
        for plan in repo_plans.values():
            representative = next((proj for proj in plan.projects if not proj.quarantine), plan.projects[0])
            commit_repo_changes(
                project=representative,
                repo=plan.repo,
                openai_key=config.openai_key,
                interactive=False,
                add_files=True,
            )
