from __future__ import annotations

import json
from pathlib import Path

from git import Repo

from dev.messages import error, info
from dev.repo_resolution import resolve_repo_targets


def status(targets: str | list[str], *, json_output: bool = False) -> int:
    requested_targets = [targets] if isinstance(targets, str) else targets
    payload: dict[str, object] = {
        "requestedTargets": list(requested_targets),
        "repos": [],
    }
    try:
        resolved_targets = resolve_repo_targets(requested_targets)
    except ValueError as ex:
        payload["error"] = str(ex)
        if json_output:
            print(json.dumps(payload, indent=2))
            return 1
        error(str(ex))
        return 1

    exit_code = 0
    for index, resolved_target in enumerate(resolved_targets):
        path = resolved_target.path
        repo_payload = {
            "name": resolved_target.name,
            "path": str(Path(path).resolve()),
            "trackedChanges": [],
        }
        if not path.exists():
            repo_payload["error"] = "Path does not exist."
            payload["repos"].append(repo_payload)
            exit_code = 1
            if not json_output:
                error(f"Project {resolved_target.name} does not exist")
            continue
        repo = Repo(path, search_parent_directories=True)
        tracked_changes = [item.a_path for item in repo.index.diff(None)]
        repo_payload["trackedChanges"] = tracked_changes
        payload["repos"].append(repo_payload)

        if json_output:
            repo.close()
            continue

        if index:
            print()
        info(f"Status for {resolved_target.name}")
        for item_path in tracked_changes:
            print(f"  {item_path}")
        repo.close()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code
