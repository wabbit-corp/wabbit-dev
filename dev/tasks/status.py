from git import Repo

from dev.messages import error, info
from dev.repo_resolution import resolve_repo_target


def status(target: str) -> None:
    try:
        project_name, path = resolve_repo_target(target)
    except ValueError as ex:
        error(str(ex))
        return
    if not path.exists():
        error(f"Project {project_name} does not exist")
    else:
        repo = Repo(path, search_parent_directories=True)
        info(f"Status for {project_name}")
        for item in repo.index.diff(None):
            print(f"  {item.a_path}")
        repo.close()
