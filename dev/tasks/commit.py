from pathlib import Path

from git import Repo

from dev.messages import error, success
from dev.config import load_config
from dev.base import Scope


def commit(project_name: str) -> None:
    with Scope() as scope:
        config = load_config()
        if project_name not in config.defined_projects:
            error(f"Project {project_name} is not defined in the config")
            return

        project = config.defined_projects[project_name]
        if not project.path.exists():
            error(f"Project {project_name} does not exist")
            return


        from dev.tasks.setup import commit_repo_changes

        try:
            repo = Repo(project.path)
        except Exception as e:
            error(f"Failed to open repository: {e}")
            return
        scope.defer(lambda: repo.close())

        commit_repo_changes(
            project=project,
            repo=repo,
            openai_key=config.openai_key,
            interactive=True,
            add_files=True
        )

    # repo = Repo(path)
    # repo.index.add(repo.untracked_files)
    # repo.index.add([item.a_path for item in repo.index.diff(None)])
    # repo.index.commit(message)
    # success(f"Committed changes for {project_name}")
    # repo.close()
