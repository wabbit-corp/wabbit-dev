from pathlib import Path

from git import Repo

from dev.messages import error, success


def commit(project_name: str, message: str) -> None:
    path = Path(project_name)
    if not path.exists():
        error(f"Project {project_name} does not exist")
    else:
        repo = Repo(path)
        repo.index.add(repo.untracked_files)
        repo.index.add([item.a_path for item in repo.index.diff(None)])
        repo.index.commit(message)
        success(f"Committed changes for {project_name}")
        repo.close()
