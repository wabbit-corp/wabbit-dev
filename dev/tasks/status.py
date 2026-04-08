from __future__ import annotations

import json
from pathlib import Path

from git import Repo

from dev.config import find_workspace_root, load_config
from dev.messages import accent, error, heading, info, muted, success
from dev.repo_resolution import configured_repo_targets, inferred_repo_targets, resolve_repo_targets


def status(targets: str | list[str] | None, *, json_output: bool = False) -> int:
    requested_targets = [targets] if isinstance(targets, str) else targets
    payload: dict[str, object] = {
        "requestedTargets": list(requested_targets or []),
        "inferredTargets": [],
        "repos": [],
    }
    config = load_config() if find_workspace_root() is not None else None
    effective_targets = inferred_repo_targets(config, requested_targets) if config is not None else list(requested_targets or [])
    if requested_targets is None and config is not None and effective_targets is not None:
        payload["inferredTargets"] = list(effective_targets)

    if not effective_targets:
        if config is None:
            payload["error"] = "No config file found. Pass an explicit repo target or run inside a configured workspace."
            if json_output:
                print(json.dumps(payload, indent=2))
                return 1
            error(payload["error"])
            return 1
        resolved_targets = configured_repo_targets(config)
    else:
        try:
            resolved_targets = resolve_repo_targets(effective_targets, config=config)
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
        repo_header = f"{heading('Status for')} {accent(resolved_target.name)}"
        repo_path = muted(Path(path).resolve())
        if tracked_changes:
            info(f"{repo_header} ({repo_path})")
            for item_path in tracked_changes:
                print(f"  {accent(item_path, 'yellow')}")
        else:
            success(f"{repo_header} ({repo_path})")
            print(f"  {muted('Working tree clean.')}")
        repo.close()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code
