from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dev.config import Config, Project, find_workspace_root, load_config, project_repo_root
from dev.discoverability import did_you_mean_suffix, unknown_name_message


@dataclass(frozen=True)
class ResolvedRepoTarget:
    name: str
    path: Path
    repo_id: str | None = None
    project_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceResolutionContext:
    cwd: Path
    workspace_root: Path | None
    current_project_id: str | None = None
    current_project_path: Path | None = None
    current_repo_target: str | None = None
    current_repo_id: str | None = None
    current_repo_path: Path | None = None


def _configured_target_names(config: Config) -> list[str]:
    defined_projects = getattr(config, "defined_projects", {})
    defined_repos = getattr(config, "defined_repos", {})
    return list(dict.fromkeys([*defined_projects.keys(), *defined_repos.keys()]))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolved_path(path: Path) -> Path:
    return path.resolve()


def _normalized_start_path(start: str | Path | None = None) -> Path:
    current = Path.cwd() if start is None else Path(start)
    if current.is_file():
        current = current.parent
    return current.resolve()


def _repo_project_ids(config: Config, repo_id: str) -> list[str]:
    repo_definition = config.defined_repos[repo_id]
    if repo_definition.project_ids:
        return list(repo_definition.project_ids)
    return [project_id for project_id, project in config.defined_projects.items() if project.repo_id == repo_id]


def _deepest_matching_projects(config: Config, path: Path) -> list[Project]:
    matches = [
        project for project in config.defined_projects.values() if _is_within(path, _resolved_path(project.path))
    ]
    if not matches:
        return []
    deepest = max(len(_resolved_path(project.path).parts) for project in matches)
    return [project for project in matches if len(_resolved_path(project.path).parts) == deepest]


def _exact_repo_id_for_path(config: Config, path: Path) -> str | None:
    for repo_id, repo_definition in config.defined_repos.items():
        if _resolved_path(repo_definition.path) == path:
            return repo_id
    return None


def _deepest_repo_id_for_path(config: Config, path: Path) -> str | None:
    matches = [
        repo_id
        for repo_id, repo_definition in config.defined_repos.items()
        if _is_within(path, _resolved_path(repo_definition.path))
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda repo_id: len(_resolved_path(config.defined_repos[repo_id].path).parts),
    )


def resolve_workspace_context(
    start: str | Path | None = None,
    *,
    config: Config | None = None,
) -> WorkspaceResolutionContext:
    cwd = _normalized_start_path(start)
    workspace_root = find_workspace_root(cwd)
    active_config = config

    if active_config is None and workspace_root is not None:
        try:
            active_config = load_config(cwd)
        except Exception:
            active_config = None

    if active_config is None:
        return WorkspaceResolutionContext(cwd=cwd, workspace_root=workspace_root)

    defined_repos = active_config.defined_repos
    project_matches = _deepest_matching_projects(active_config, cwd)
    current_project = next((project for project in project_matches if project.project_id is not None), None)

    repo_id = _deepest_repo_id_for_path(active_config, cwd)
    repo_target = repo_id
    repo_path = defined_repos[repo_id].path if repo_id is not None and repo_id in defined_repos else None

    if current_project is not None and current_project.repo_id is not None and current_project.repo_id in defined_repos:
        repo_id = current_project.repo_id
        repo_target = repo_id
        repo_path = defined_repos[repo_id].path
    elif current_project is not None and current_project.project_id is not None:
        repo_target = current_project.project_id
        repo_path = current_project.effective_repo_root

    return WorkspaceResolutionContext(
        cwd=cwd,
        workspace_root=workspace_root.resolve() if workspace_root is not None else None,
        current_project_id=current_project.project_id if current_project is not None else None,
        current_project_path=current_project.path if current_project is not None else None,
        current_repo_target=repo_target,
        current_repo_id=repo_id,
        current_repo_path=repo_path,
    )


def inferred_project_targets(
    config: Config,
    targets: Sequence[str] | None = None,
    *,
    start: str | Path | None = None,
) -> list[str] | None:
    if targets:
        return list(targets)

    context = resolve_workspace_context(start, config=config)
    if context.workspace_root is None or context.cwd == context.workspace_root:
        return None
    if context.current_project_id is not None:
        return [context.current_project_id]
    if context.current_repo_target is not None:
        return [context.current_repo_target]
    return None


def inferred_repo_targets(
    config: Config,
    targets: Sequence[str] | None = None,
    *,
    start: str | Path | None = None,
) -> list[str] | None:
    if targets:
        return list(targets)

    context = resolve_workspace_context(start, config=config)
    if context.workspace_root is None or context.cwd == context.workspace_root:
        return None
    if context.current_repo_target is not None:
        return [context.current_repo_target]
    if context.current_project_id is not None:
        return [context.current_project_id]
    return None


def format_workspace_context(context: WorkspaceResolutionContext) -> str:
    project_line = "-"
    if context.current_project_id is not None and context.current_project_path is not None:
        project_line = f"{context.current_project_id} ({context.current_project_path})"

    repo_line = "-"
    if context.current_repo_target is not None and context.current_repo_path is not None:
        repo_line = f"{context.current_repo_target} ({context.current_repo_path})"

    workspace_root = str(context.workspace_root) if context.workspace_root is not None else "-"
    return "\n".join(
        [
            "Resolved context:",
            f"  cwd: {context.cwd}",
            f"  workspace root: {workspace_root}",
            f"  current project: {project_line}",
            f"  current repo: {repo_line}",
        ]
    )


def contextualize_resolution_error(
    message: str,
    context: WorkspaceResolutionContext,
) -> str:
    return f"{message}\n{format_workspace_context(context)}"


def _normalize_lookup_target(target: str) -> tuple[str, bool]:
    if target.startswith(":") and target != ":root":
        return target[1:], True
    return target, False


def resolve_project_ids(config: Config, targets: Sequence[str] | None = None) -> list[str]:
    context = resolve_workspace_context(config=config)
    defined_projects = config.defined_projects
    defined_repos = config.defined_repos
    if not targets:
        return list(defined_projects.keys())

    resolved_project_ids: list[str] = []
    seen: set[str] = set()

    for target in targets:
        normalized_target, had_prefix = _normalize_lookup_target(target)

        project_ids: list[str] | None = None
        if normalized_target in defined_projects:
            project_ids = [normalized_target]
        elif normalized_target in defined_repos:
            project_ids = _repo_project_ids(config, normalized_target)
        else:
            path = Path(target)
            if path.exists():
                resolved_path = _resolved_path(path)
                exact_repo_id = _exact_repo_id_for_path(config, resolved_path)
                if exact_repo_id is not None:
                    project_ids = _repo_project_ids(config, exact_repo_id)
                else:
                    project_matches = _deepest_matching_projects(config, resolved_path)
                    if project_matches:
                        project_ids = [
                            project.project_id for project in project_matches if project.project_id is not None
                        ]
                    else:
                        repo_id = _deepest_repo_id_for_path(config, resolved_path)
                        if repo_id is not None:
                            project_ids = _repo_project_ids(config, repo_id)
                        else:
                            raise ValueError(
                                contextualize_resolution_error(
                                    f"Path does not map to a configured project or repo: {target!r}.",
                                    context,
                                )
                            )

        if project_ids is None:
            lookup_target = normalized_target if had_prefix else target
            raise ValueError(
                contextualize_resolution_error(
                    unknown_name_message("project or repo", lookup_target, _configured_target_names(config)),
                    context,
                )
            )

        for project_id in project_ids:
            if project_id in seen:
                continue
            seen.add(project_id)
            resolved_project_ids.append(project_id)

    return resolved_project_ids


def resolve_check_paths(target: str, config: Config | None = None) -> list[Path]:
    context = resolve_workspace_context(config=config) if config is not None else resolve_workspace_context()
    if target == ":root":
        if config is None:
            raise ValueError("No config file found. Cannot resolve project paths.")
        return [project.path for project in config.defined_projects.values()]

    normalized_target, had_prefix = _normalize_lookup_target(target)
    if config is not None:
        if normalized_target in config.defined_projects:
            return [config.defined_projects[normalized_target].path]
        if normalized_target in config.defined_repos:
            return [config.defined_repos[normalized_target].path]

    path = Path(target)
    if path.exists():
        return [path]

    if config is None:
        raise ValueError(f"Path does not exist: {path}.")

    lookup_target = normalized_target if had_prefix else target
    raise ValueError(
        contextualize_resolution_error(
            unknown_name_message("project or repo", lookup_target, _configured_target_names(config)),
            context,
        )
    )


def _resolved_repo_target_from_project(project: Project) -> ResolvedRepoTarget:
    project_id = project.project_id or project.path.as_posix()
    return ResolvedRepoTarget(
        name=project.repo_id or project_id,
        path=project_repo_root(project),
        repo_id=project.repo_id,
        project_ids=(project_id,),
    )


def _resolved_repo_target_from_repo(config: Config, repo_id: str) -> ResolvedRepoTarget:
    repo_definition = config.defined_repos[repo_id]
    return ResolvedRepoTarget(
        name=repo_id,
        path=repo_definition.path,
        repo_id=repo_id,
        project_ids=tuple(_repo_project_ids(config, repo_id)),
    )


def _load_config_if_available() -> Config | None:
    if find_workspace_root() is None:
        return None
    try:
        return load_config()
    except Exception:
        return None


def resolve_repo_target(target: str, *, config: Config | None = None) -> ResolvedRepoTarget:
    active_config = config if config is not None else _load_config_if_available()
    context = (
        resolve_workspace_context(config=active_config) if active_config is not None else resolve_workspace_context()
    )
    normalized_target, had_prefix = _normalize_lookup_target(target)

    if active_config is not None:
        if normalized_target in active_config.defined_repos:
            return _resolved_repo_target_from_repo(active_config, normalized_target)
        if normalized_target in active_config.defined_projects:
            project = active_config.defined_projects[normalized_target]
            return _resolved_repo_target_from_project(project)

    path = Path(target)
    if path.exists():
        if active_config is not None:
            resolved_path = _resolved_path(path)
            exact_repo_id = _exact_repo_id_for_path(active_config, resolved_path)
            if exact_repo_id is not None:
                return _resolved_repo_target_from_repo(active_config, exact_repo_id)

            project_matches = _deepest_matching_projects(active_config, resolved_path)
            if project_matches:
                return _resolved_repo_target_from_project(project_matches[0])

            repo_id = _deepest_repo_id_for_path(active_config, resolved_path)
            if repo_id is not None:
                return _resolved_repo_target_from_repo(active_config, repo_id)

        return ResolvedRepoTarget(name=target, path=path)

    if active_config is None:
        raise ValueError(f"Target does not exist as a path: {target!r}.")

    lookup_target = normalized_target if had_prefix else target
    raise ValueError(
        contextualize_resolution_error(
            "Target does not exist as a path and is not a configured project or repo: "
            f"{lookup_target!r}.{did_you_mean_suffix(lookup_target, _configured_target_names(active_config))}",
            context,
        )
    )


def resolve_repo_targets(targets: Sequence[str], *, config: Config | None = None) -> list[ResolvedRepoTarget]:
    resolved_targets: list[ResolvedRepoTarget] = []
    seen_paths: set[Path] = set()

    for target in targets:
        resolved_target = resolve_repo_target(target, config=config)
        path_key = _resolved_path(resolved_target.path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        resolved_targets.append(resolved_target)

    return resolved_targets


def configured_repo_targets(config: Config) -> list[ResolvedRepoTarget]:
    repo_targets: list[ResolvedRepoTarget] = []
    seen_paths: set[Path] = set()

    for project in config.defined_projects.values():
        resolved_target = (
            _resolved_repo_target_from_repo(config, project.repo_id)
            if project.repo_id is not None and project.repo_id in config.defined_repos
            else _resolved_repo_target_from_project(project)
        )
        path_key = _resolved_path(resolved_target.path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        repo_targets.append(resolved_target)

    return repo_targets


__all__ = [
    "WorkspaceResolutionContext",
    "ResolvedRepoTarget",
    "configured_repo_targets",
    "contextualize_resolution_error",
    "format_workspace_context",
    "inferred_project_targets",
    "inferred_repo_targets",
    "resolve_check_paths",
    "resolve_project_ids",
    "resolve_workspace_context",
    "resolve_repo_target",
    "resolve_repo_targets",
]
