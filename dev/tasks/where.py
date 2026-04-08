from __future__ import annotations

import json
from pathlib import Path

from dev.config import find_workspace_root, load_config
from dev.messages import accent, command_text, heading, muted
from dev.repo_resolution import inferred_project_targets, inferred_repo_targets, resolve_workspace_context

PROJECT_DEFAULT_COMMANDS: tuple[str, ...] = (
    "setup",
    "build",
    "clean",
    "cloc",
    "dep graph",
    "project show",
    "project deps",
    "project targets",
    "check",
    "spdx headers",
    "secrets scan",
)

REPO_DEFAULT_COMMANDS: tuple[str, ...] = (
    "project repo",
    "status",
)

def _path_string(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path.resolve())


def where_payload() -> dict[str, object]:
    config_error: str | None = None
    config = None
    workspace_root = find_workspace_root()
    if workspace_root is not None:
        try:
            config = load_config()
        except Exception as ex:
            config_error = str(ex)

    context = resolve_workspace_context(config=config)
    default_project_targets = inferred_project_targets(config, None) if config is not None else None
    default_repo_targets = inferred_repo_targets(config, None) if config is not None else None

    return {
        "cwd": str(context.cwd),
        "workspaceRoot": _path_string(context.workspace_root),
        "configError": config_error,
        "currentProject": (
            {
                "projectId": context.current_project_id,
                "path": _path_string(context.current_project_path),
            }
            if context.current_project_id is not None and context.current_project_path is not None
            else None
        ),
        "currentRepo": (
            {
                "target": context.current_repo_target,
                "repoId": context.current_repo_id,
                "path": _path_string(context.current_repo_path),
            }
            if context.current_repo_target is not None and context.current_repo_path is not None
            else None
        ),
        "defaultProjectTarget": default_project_targets[0] if default_project_targets else None,
        "defaultRepoTarget": default_repo_targets[0] if default_repo_targets else None,
        "projectDefaultCommands": list(PROJECT_DEFAULT_COMMANDS),
        "repoDefaultCommands": list(REPO_DEFAULT_COMMANDS),
    }


def render_where_lines() -> list[str]:
    payload = where_payload()
    lines = [
        f"{heading('Current directory')}: {payload['cwd']}",
        f"{heading('Workspace root')}: {payload['workspaceRoot'] or '-'}",
    ]

    config_error = payload["configError"]
    if config_error is not None:
        lines.append(f"{accent('Config load error', 'red')}: {config_error}")

    current_project = payload["currentProject"]
    if isinstance(current_project, dict):
        lines.append(
            f"{heading('Current project')}: "
            f"{accent(current_project['projectId'])} ({muted(current_project['path'])})"
        )
    else:
        lines.append(f"{heading('Current project')}: -")

    current_repo = payload["currentRepo"]
    if isinstance(current_repo, dict):
        lines.append(
            f"{heading('Current repo')}: "
            f"{accent(current_repo['target'])} ({muted(current_repo['path'])})"
        )
    else:
        lines.append(f"{heading('Current repo')}: -")

    project_target = payload["defaultProjectTarget"] or "-"
    repo_target = payload["defaultRepoTarget"] or "-"
    lines.append(f"{heading('Implicit project target')}: {accent(project_target) if project_target != '-' else '-'}")
    lines.append(f"{heading('Implicit repo target')}: {accent(repo_target) if repo_target != '-' else '-'}")
    lines.append(
        f"{heading('Project-default commands')}: "
        + ", ".join(command_text(command) for command in payload["projectDefaultCommands"])
    )
    lines.append(
        f"{heading('Repo-default commands')}: "
        + ", ".join(command_text(command) for command in payload["repoDefaultCommands"])
    )
    return lines


def show_where(*, json_output: bool = False) -> int:
    if json_output:
        print(json.dumps(where_payload(), indent=2))
        return 0

    for line in render_where_lines():
        print(line)
    return 0


__all__ = [
    "PROJECT_DEFAULT_COMMANDS",
    "REPO_DEFAULT_COMMANDS",
    "render_where_lines",
    "show_where",
    "where_payload",
]
