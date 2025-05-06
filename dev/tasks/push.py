from pathlib import Path

from git import Repo

from dev.messages import error, success
from dev.config import load_config


def push(project_name: str) -> None:
    if project_name == '.':
        # Push all projects
        config = load_config()
        for name, project_name in config.defined_projects.items():
            path = project_name.path

            if not path.exists():
                error(f"Project {name} does not exist")
            else:
                if project_name.github_repo is not None:
                    repo = Repo(path)
                    repo.git.push('origin', 'master')
                    repo.git.push(tags=True)
                    success(f"Pushed changes for {name}")
                    repo.close()
    else:
        path = Path(project_name)
        if not path.exists():
            error(f"Project {project_name} does not exist")
        else:
            repo = Repo(path)
            repo.git.push('origin', 'master')
            repo.git.push(tags=True)
            success(f"Pushed changes for {project_name}")
            repo.close()
