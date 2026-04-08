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


def _configured_target_names(config: Config) -> list[str]:
    return list(dict.fromkeys([*config.defined_projects.keys(), *config.defined_repos.keys()]))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolved_path(path: Path) -> Path:
    return path.resolve()


def _repo_project_ids(config: Config, repo_id: str) -> list[str]:
    repo_definition = config.defined_repos[repo_id]
    if repo_definition.project_ids:
        return list(repo_definition.project_ids)
    return [
        project_id
        for project_id, project in config.defined_projects.items()
        if project.repo_id == repo_id
    ]


def _deepest_matching_projects(config: Config, path: Path) -> list[Project]:
    matches = [
        project
        for project in config.defined_projects.values()
        if _is_within(path, _resolved_path(project.path))
    ]
    if not matches:
        return []
    deepest = max(len(_resolved_path(project.path).parts) for project in matches)
    return [
        project
        for project in matches
        if len(_resolved_path(project.path).parts) == deepest
    ]


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


def _normalize_lookup_target(target: str) -> tuple[str, bool]:
    if target.startswith(":") and target != ":root":
        return target[1:], True
    return target, False


def resolve_project_ids(config: Config, targets: Sequence[str] | None = None) -> list[str]:
    if not targets:
        return list(config.defined_projects.keys())

    resolved_project_ids: list[str] = []
    seen: set[str] = set()

    for target in targets:
        normalized_target, had_prefix = _normalize_lookup_target(target)

        project_ids: list[str] | None = None
        if normalized_target in config.defined_projects:
            project_ids = [normalized_target]
        elif normalized_target in config.defined_repos:
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
                            project.project_id
                            for project in project_matches
                            if project.project_id is not None
                        ]
                    else:
                        repo_id = _deepest_repo_id_for_path(config, resolved_path)
                        if repo_id is not None:
                            project_ids = _repo_project_ids(config, repo_id)
                        else:
                            raise ValueError(
                                f"Path does not map to a configured project or repo: {target!r}."
                            )

        if project_ids is None:
            lookup_target = normalized_target if had_prefix else target
            raise ValueError(unknown_name_message("project or repo", lookup_target, _configured_target_names(config)))

        for project_id in project_ids:
            if project_id in seen:
                continue
            seen.add(project_id)
            resolved_project_ids.append(project_id)

    return resolved_project_ids


def resolve_check_paths(target: str, config: Config | None = None) -> list[Path]:
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
    raise ValueError(unknown_name_message("project or repo", lookup_target, _configured_target_names(config)))


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
        "Target does not exist as a path and is not a configured project or repo: "
        f"{lookup_target!r}.{did_you_mean_suffix(lookup_target, _configured_target_names(active_config))}"
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
    "ResolvedRepoTarget",
    "configured_repo_targets",
    "resolve_check_paths",
    "resolve_project_ids",
    "resolve_repo_target",
    "resolve_repo_targets",
]
