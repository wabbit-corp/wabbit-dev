from pathlib import Path

from git import Repo

from dev.config import load_config, project_repo_root
from dev.messages import error, success
from dev.repo_resolution import resolve_repo_target


def push(project_name: str) -> None:
    if project_name == ".":
        # Push all projects
        config = load_config()
        pushed_repo_paths: set[Path] = set()
        for name, project in config.defined_projects.items():
            path = project_repo_root(project)

            if not path.exists():
                error(f"Project {name} does not exist")
            else:
                if project.github_repo is not None:
                    if path in pushed_repo_paths:
                        continue
                    repo = Repo(path)
                    repo.git.push("origin", "master")
                    repo.git.push(tags=True)
                    success(f"Pushed changes for {name}")
                    repo.close()
                    pushed_repo_paths.add(path)
    else:
        try:
            _resolved_name, path = resolve_repo_target(project_name)
        except ValueError as ex:
            error(str(ex))
            return
        if not path.exists():
            error(f"Project {project_name} does not exist")
        else:
            repo = Repo(path, search_parent_directories=True)
            repo.git.push("origin", "master")
            repo.git.push(tags=True)
            success(f"Pushed changes for {project_name}")
            repo.close()
