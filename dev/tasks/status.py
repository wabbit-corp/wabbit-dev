from pathlib import Path

from git import Repo

from dev.messages import error, info


def status(project_name: str, path: Path) -> None:
    if not path.exists():
        error(f"Project {project_name} does not exist")
    else:
        repo = Repo(path, search_parent_directories=True)
        info(f"Status for {project_name}")
        for item in repo.index.diff(None):
            print(f"  {item.a_path}")
