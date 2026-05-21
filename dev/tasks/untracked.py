from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from dev.config import Config, load_config, project_repo_root
from dev.messages import accent, heading, muted, success

PathKind = Literal["dir", "file", "symlink", "other"]

DEFAULT_IGNORED_NAMES: frozenset[str] = frozenset(
    {
        ".DS_Store",
        ".git",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".venv",
        ".vscode",
        "dev",
        "dev.py",
        "root.clj",
        "root.private.clj",
    }
)


@dataclass(frozen=True)
class UntrackedWorkspacePath:
    relative_path: str
    absolute_path: Path
    kind: PathKind


class UntrackedPathPayload(TypedDict):
    path: str
    absolutePath: str
    kind: PathKind


class UntrackedPayload(TypedDict):
    workspaceRoot: str
    includeIgnored: bool
    coveredPathCount: int
    paths: list[UntrackedPathPayload]


def _resolved(path: Path) -> Path:
    return path.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_kind(path: Path) -> PathKind:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "file"
    return "other"


def _covered_paths(config: Config) -> frozenset[Path]:
    paths: set[Path] = set()
    for repo_definition in config.defined_repos.values():
        paths.add(_resolved(repo_definition.path))
    for project in config.defined_projects.values():
        paths.add(_resolved(project.path))
        paths.add(_resolved(project_repo_root(project)))
    return frozenset(paths)


def _is_covered(path: Path, covered_paths: frozenset[Path]) -> bool:
    return any(_is_within(path, covered_path) for covered_path in covered_paths)


def _has_covered_descendant(path: Path, covered_paths: frozenset[Path]) -> bool:
    return any(_is_within(covered_path, path) for covered_path in covered_paths)


def _is_ignored(path: Path, workspace_root: Path) -> bool:
    try:
        relative = path.relative_to(workspace_root)
    except ValueError:
        return False
    if not relative.parts:
        return False
    return relative.parts[0] in DEFAULT_IGNORED_NAMES or relative.parts[0].startswith(".")


def _display_path(path: Path, workspace_root: Path) -> str:
    return path.relative_to(workspace_root).as_posix()


def find_untracked_workspace_paths(
    config: Config,
    *,
    include_ignored: bool = False,
) -> list[UntrackedWorkspacePath]:
    workspace_root = config.workspace_root
    if workspace_root is None:
        raise ValueError("Config has no workspace root.")

    root = workspace_root.resolve()
    covered_paths = _covered_paths(config)
    results: list[UntrackedWorkspacePath] = []

    def visit(path: Path) -> None:
        resolved_path = _resolved(path)
        if not include_ignored and _is_ignored(path, root):
            return
        if _is_covered(resolved_path, covered_paths):
            return
        if path.is_dir() and _has_covered_descendant(resolved_path, covered_paths):
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child)
            return
        results.append(
            UntrackedWorkspacePath(
                relative_path=_display_path(path, root),
                absolute_path=resolved_path,
                kind=_path_kind(path),
            )
        )

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        visit(child)

    return results


def _payload_for(config: Config, *, include_ignored: bool) -> UntrackedPayload:
    paths = find_untracked_workspace_paths(config, include_ignored=include_ignored)
    workspace_root = config.workspace_root
    if workspace_root is None:
        raise ValueError("Config has no workspace root.")
    return {
        "workspaceRoot": str(workspace_root.resolve()),
        "includeIgnored": include_ignored,
        "coveredPathCount": len(_covered_paths(config)),
        "paths": [
            {
                "path": path.relative_path,
                "absolutePath": str(path.absolute_path),
                "kind": path.kind,
            }
            for path in paths
        ],
    }


def _kind_label(kind: PathKind) -> str:
    match kind:
        case "dir":
            return accent("dir  ", "cyan")
        case "file":
            return accent("file ", "green")
        case "symlink":
            return accent("link ", "magenta")
        case "other":
            return accent("other", "yellow")


def untracked(*, json_output: bool = False, include_ignored: bool = False) -> int:
    config = load_config()
    payload = _payload_for(config, include_ignored=include_ignored)

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    paths = payload["paths"]
    if not paths:
        success("All workspace paths are tracked by root.clj.")
        return 0

    print(f"{heading('Paths not tracked by root.clj')}: {muted(payload['workspaceRoot'])}")
    for item in paths:
        print(f"  {_kind_label(item['kind'])} {accent(item['path'])}")
    return 0


__all__ = [
    "DEFAULT_IGNORED_NAMES",
    "UntrackedWorkspacePath",
    "find_untracked_workspace_paths",
    "untracked",
]
