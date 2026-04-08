from __future__ import annotations

from git import Repo

from dev.messages import error, info
from dev.repo_resolution import resolve_repo_targets


def status(targets: str | list[str]) -> None:
    requested_targets = [targets] if isinstance(targets, str) else targets
    try:
        resolved_targets = resolve_repo_targets(requested_targets)
    except ValueError as ex:
        error(str(ex))
        return

    for index, resolved_target in enumerate(resolved_targets):
        path = resolved_target.path
        if not path.exists():
            error(f"Project {resolved_target.name} does not exist")
            continue
        if index:
            print()
        repo = Repo(path, search_parent_directories=True)
        info(f"Status for {resolved_target.name}")
        for item in repo.index.diff(None):
            print(f"  {item.a_path}")
        repo.close()
