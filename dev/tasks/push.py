from git import Repo

from dev.config import load_config
from dev.messages import error, success
from dev.repo_resolution import configured_repo_targets, resolve_repo_targets


def push(targets: str | list[str] | None = None) -> None:
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
            return
        try:
            repo_targets = resolve_repo_targets(requested_targets, config=load_config())
        except ValueError as ex:
            error(str(ex))
            return

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
