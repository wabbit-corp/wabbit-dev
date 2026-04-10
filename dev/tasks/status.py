from __future__ import annotations

import json
from pathlib import Path

from git import Repo

from dev.config import find_workspace_root, load_config
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, heading, info, muted, success
from dev.repo_resolution import configured_repo_targets, inferred_repo_targets, resolve_repo_targets


def _status_lists(repo: Repo) -> tuple[list[str], list[str], list[str]]:
    staged: list[str] = []
    unstaged: list[str] = []
    untracked = sorted(repo.untracked_files)

    porcelain = repo.git.status("--porcelain=1", "--untracked-files=all")
    for raw_line in porcelain.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip()
        if not path_text:
            continue
        if status == "??":
            continue
        if status[0] != " ":
            staged.append(path_text)
        if status[1] != " ":
            unstaged.append(path_text)

    return sorted(dict.fromkeys(staged)), sorted(dict.fromkeys(unstaged)), untracked


def status(targets: str | list[str] | None, *, json_output: bool = False) -> int:
    requested_targets = [targets] if isinstance(targets, str) else targets
    repos_payload: list[dict[str, object]] = []
    payload: dict[str, object] = {
        "requestedTargets": list(requested_targets or []),
        "inferredTargets": [],
        "repos": repos_payload,
    }
    config = load_config() if find_workspace_root() is not None else None
    effective_targets = (
        inferred_repo_targets(config, requested_targets) if config is not None else list(requested_targets or [])
    )
    if requested_targets is None and config is not None and effective_targets is not None:
        payload["inferredTargets"] = list(effective_targets)

    if not effective_targets:
        if config is None:
            payload["error"] = (
                "No config file found. Pass an explicit repo target or run inside a configured workspace."
            )
            if json_output:
                print(json.dumps(payload, indent=2))
                return 1
            error(contextualize_failure(str(payload["error"]), ["status"]))
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
            error(contextualize_failure(str(ex), ["status", *effective_targets]))
            return 1

    exit_code = 0
    for index, resolved_target in enumerate(resolved_targets):
        path = resolved_target.path
        repo_payload: dict[str, object] = {
            "name": resolved_target.name,
            "path": str(Path(path).resolve()),
            "stagedChanges": [],
            "unstagedChanges": [],
            "untrackedFiles": [],
        }
        if not path.exists():
            repo_payload["error"] = "Path does not exist."
            repos_payload.append(repo_payload)
            exit_code = 1
            if not json_output:
                error(f"Project {resolved_target.name} does not exist")
            continue
        repo = Repo(path, search_parent_directories=True)
        staged_changes, unstaged_changes, untracked_files = _status_lists(repo)
        repo_payload["stagedChanges"] = staged_changes
        repo_payload["unstagedChanges"] = unstaged_changes
        repo_payload["trackedChanges"] = unstaged_changes
        repo_payload["untrackedFiles"] = untracked_files
        repo_payload["isClean"] = not (staged_changes or unstaged_changes or untracked_files)
        repos_payload.append(repo_payload)

        if json_output:
            repo.close()
            continue

        if index:
            print()
        repo_header = f"{heading('Status for')} {accent(resolved_target.name)}"
        repo_path = muted(Path(path).resolve())
        if staged_changes or unstaged_changes or untracked_files:
            info(f"{repo_header} ({repo_path})")
            if staged_changes:
                print(f"  {heading('Staged')}:")
                for item_path in staged_changes:
                    print(f"    {accent(item_path, 'green')}")
            if unstaged_changes:
                print(f"  {heading('Unstaged')}:")
                for item_path in unstaged_changes:
                    print(f"    {accent(item_path, 'yellow')}")
            if untracked_files:
                print(f"  {heading('Untracked')}:")
                for item_path in untracked_files:
                    print(f"    {accent(item_path, 'magenta')}")
        else:
            success(f"{repo_header} ({repo_path})")
            print(f"  {muted('Working tree clean.')}")
        repo.close()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code
