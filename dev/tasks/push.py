from git import Repo

from dev.config import load_config
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, info, muted, success
from dev.repo_resolution import configured_repo_targets, resolve_repo_targets


def push(targets: str | list[str] | None = None, *, dry_run: bool = False) -> int:
    requested_targets = [targets] if isinstance(targets, str) else targets
    if not requested_targets or requested_targets == ["."]:
        config = load_config()
        repo_targets = [
            repo_target
            for repo_target in configured_repo_targets(config)
            if any(
                config.defined_projects[project_id].github_repo is not None
                for project_id in repo_target.project_ids
                if project_id in config.defined_projects
            )
        ]
    else:
        if "." in requested_targets:
            error("`push .` cannot be combined with other targets.")
            return 1
        try:
            repo_targets = resolve_repo_targets(requested_targets, config=load_config())
        except ValueError as ex:
            error(contextualize_failure(str(ex), ["push", *requested_targets]))
            return 1

    if dry_run:
        info(f"Dry run: would push {len(repo_targets)} repository/repositories")
        for resolved_target in repo_targets:
            print(
                f"  {accent(resolved_target.name)}: " f"{muted('origin master + tags')} ({muted(resolved_target.path)})"
            )
        return 0

    for resolved_target in repo_targets:
        path = resolved_target.path
        if not path.exists():
            error(f"Project {resolved_target.name} does not exist")
            continue
        repo = Repo(path, search_parent_directories=True)
        repo.git.push("origin", "master")
        repo.git.push(tags=True)
        success(f"Pushed changes for {resolved_target.name}")
        repo.close()
    return 0
