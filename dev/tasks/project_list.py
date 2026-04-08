from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dev.config import (
    Config,
    DataProject,
    Dependency,
    GradleProject,
    PremakeProject,
    Project,
    PurescriptProject,
    PythonProject,
    load_config,
)
from dev.discoverability import require_project
from dev.jvms import resolve_project_jvm_policy
from dev.messages import style
from dev.repo_resolution import (
    ResolvedRepoTarget,
    contextualize_resolution_error,
    inferred_project_targets,
    inferred_repo_targets,
    resolve_project_ids,
    resolve_workspace_context,
)


def _colored(text: str, color: str, *, attrs: tuple[str, ...] = ()) -> str:
    return style(text, color, attrs=attrs)


def _project_type_label(project: Project) -> str:
    if isinstance(project, PythonProject):
        return "python"
    if isinstance(project, GradleProject):
        if "scala" in project.resolved_features:
            return "scala/kmp" if project.is_kmp else "scala/jvm"
        if "kotlin" in project.resolved_features or project.is_kmp:
            return "kotlin/kmp" if project.is_kmp else "kotlin/jvm"
        return "gradle/kmp" if project.is_kmp else "gradle/jvm"
    if isinstance(project, PurescriptProject):
        return "purescript"
    if isinstance(project, PremakeProject):
        return "premake"
    if isinstance(project, DataProject):
        return "data"
    return type(project).__name__.removesuffix("Project").lower()


def _project_type_color(project_type: str) -> str:
    if project_type == "python":
        return "green"
    if project_type.endswith("/kmp"):
        return "magenta"
    if project_type.endswith("/jvm"):
        return "blue"
    if project_type == "purescript":
        return "yellow"
    return "cyan"


def _target_platform_color(platform: str) -> str:
    if platform == "jvm":
        return "blue"
    if platform == "android":
        return "green"
    if platform.startswith("ios"):
        return "magenta"
    if platform.startswith("macos"):
        return "cyan"
    if platform.startswith("linux") or platform.startswith("mingw"):
        return "yellow"
    return "white"


def _project_display_name(project: Project) -> str:
    project_id = project.project_id
    if not project.is_repo_managed:
        return project_id if project_id is not None else project.path.as_posix()

    relative_path = project.path.relative_to(project.effective_repo_root)
    return f"  {relative_path.as_posix()}"


def _repo_display_name(project: Project) -> str:
    repo_id = project.repo_id
    if repo_id is not None:
        return f"{repo_id}/"
    return f"{project.effective_repo_root.name}/"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolved_publish_target(project: Project) -> str:
    if isinstance(project, GradleProject):
        if project.publish_target == "jetbrains-marketplace" or "intellij-plugin" in project.resolved_features:
            return "intellij-marketplace"
        if project.publish_target == "jitpack":
            return "jitpack"
        if project.publish_target == "maven-central":
            return "maven-central"
        return "skip"
    if isinstance(project, PythonProject):
        if project.publish_target == "pypi":
            return "pypi"
        return "skip"
    return "skip"


def _docs_summary(project: Project) -> str:
    if not project.docs_enabled:
        return "disabled"
    if project.docs_system is None:
        return "enabled"
    return project.docs_system


def _dependency_summary(dep: Dependency) -> str:
    scope = dep.scope or "implementation"
    return f"{scope}: {dep.name}"


def _dependency_payload(dep: Dependency) -> dict[str, str]:
    scope = dep.scope or "implementation"
    payload = {
        "scope": scope,
        "name": dep.name,
        "targetType": type(dep.target).__name__.removesuffix("DependencyTarget").lower(),
    }
    target = dep.target
    if hasattr(target, "project"):
        payload["project"] = target.project
    if hasattr(target, "artifact") and target.artifact is not None:
        payload["artifact"] = target.artifact
    if hasattr(target, "package"):
        payload["package"] = target.package
    if hasattr(target, "version"):
        payload["version"] = target.version
    if hasattr(target, "path"):
        payload["path"] = str(target.path.resolve())
    return payload


def _absolute_path(path: Path) -> str:
    return str(path.resolve())


@dataclass(frozen=True)
class ManagedFileHint:
    path: Path
    note: str | None = None


def _managed_file_hints(project: Project) -> list[ManagedFileHint]:
    hints: list[ManagedFileHint] = []
    if isinstance(project, PythonProject):
        hints.extend(
            [
                ManagedFileHint(project.path / "pyproject.toml"),
                ManagedFileHint(project.path / "requirements-dev.txt"),
            ]
        )
        if project.docs_enabled and project.docs_system == "mkdocs":
            hints.extend(
                [
                    ManagedFileHint(project.path / "mkdocs.yml"),
                    ManagedFileHint(project.path / "docs" / "index.md"),
                ]
            )
        return hints

    if isinstance(project, GradleProject):
        hints.append(ManagedFileHint(project.path / "build.gradle.kts"))
        hints.append(ManagedFileHint(project.effective_gradle_root / "settings.gradle.kts"))
        hints.append(
            ManagedFileHint(
                project.effective_gradle_root / "settings.local.gradle.kts",
                note="written in --local mode",
            )
        )
        if project.docs_enabled and project.docs_system == "dokka":
            hints.append(ManagedFileHint(project.path / "docs" / "dokka-module.md"))
        return hints

    return hints


def project_show_payload(project_id: str, config: Config) -> dict[str, object]:
    project = require_project(config, project_id)
    repo_definition = config.defined_repos.get(project.repo_id) if project.repo_id is not None else None
    payload: dict[str, object] = {
        "projectId": project.project_id or project.path.as_posix(),
        "type": _project_type_label(project),
        "path": _absolute_path(project.path),
        "repoRoot": _absolute_path(project.effective_repo_root),
        "repoId": project.repo_id,
        "managedBySetup": project.managed_by_setup,
        "publishTarget": _resolved_publish_target(project),
        "docsSystem": _docs_summary(project),
        "resolvedDependencies": [_dependency_payload(dep) for dep in project.resolved_dependencies],
        "generatedFiles": [
            {
                "path": _absolute_path(hint.path),
                "exists": hint.path.exists(),
                "note": hint.note,
            }
            for hint in _managed_file_hints(project)
        ],
    }

    if isinstance(project, GradleProject):
        repo_policy = repo_definition.jvm_policy if repo_definition is not None else None
        payload["jvmPolicy"] = resolve_project_jvm_policy(
            project,
            task_name=None,
            repo_policy=repo_policy,
            global_jvm_version=config.jvm_version,
        )
        payload["jvmTaskOverrides"] = dict(sorted(project.jvm_task_policies.items()))
    else:
        payload["jvmPolicy"] = None
        payload["jvmTaskOverrides"] = {}

    return payload


def project_dependency_payload(project_id: str, config: Config) -> dict[str, object]:
    project = require_project(config, project_id)
    return {
        "projectId": project.project_id or project.path.as_posix(),
        "resolvedDependencies": [_dependency_payload(dep) for dep in project.resolved_dependencies],
    }


def _kmp_project_payload(project_id: str, config: Config) -> dict[str, object]:
    project = require_project(config, project_id)
    if not isinstance(project, GradleProject) or not project.is_kmp:
        raise ValueError(f"Project {project_id!r} is not a Kotlin Multiplatform project.")
    return {
        "projectId": project.project_id or project.path.as_posix(),
        "type": _project_type_label(project),
        "path": _absolute_path(project.path),
        "repoId": project.repo_id,
        "platforms": list(project.platforms),
        "targetKinds": [target.kind for target in project.targets],
    }


def render_project_show_lines(project_id: str, config: Config, *, colorize: bool = True) -> list[str]:
    project = require_project(config, project_id)
    project_type = _project_type_label(project)
    type_label = project_type
    if colorize:
        type_label = _colored(project_type, _project_type_color(project_type), attrs=("bold",))

    repo_definition = config.defined_repos.get(project.repo_id) if project.repo_id is not None else None
    lines = [
        f"Project: {project.project_id or project.path.as_posix()}",
        f"Type: {type_label}",
        f"Path: {_display_path(project.path)}",
        f"Repo root: {_display_path(project.effective_repo_root)}",
        f"Repo ID: {project.repo_id or '-'}",
        f"Managed by setup: {'yes' if project.managed_by_setup else 'no'}",
        f"Publish target: {_resolved_publish_target(project)}",
        f"Docs system: {_docs_summary(project)}",
    ]

    if isinstance(project, GradleProject):
        repo_policy = repo_definition.jvm_policy if repo_definition is not None else None
        policy = resolve_project_jvm_policy(
            project,
            task_name=None,
            repo_policy=repo_policy,
            global_jvm_version=config.jvm_version,
        )
        lines.append(f"JVM policy: {policy}")
        if project.jvm_task_policies:
            lines.append(
                "JVM task overrides: "
                + ", ".join(f"{pattern} -> {policy}" for pattern, policy in sorted(project.jvm_task_policies.items()))
            )
    else:
        lines.append("JVM policy: n/a")

    if project.resolved_dependencies:
        lines.append(f"Resolved dependencies ({len(project.resolved_dependencies)}):")
        lines.extend(f"  - {_dependency_summary(dep)}" for dep in project.resolved_dependencies)
    else:
        lines.append("Resolved dependencies: none")

    managed_files = _managed_file_hints(project)
    if managed_files:
        lines.append("Relevant generated files:")
        for hint in managed_files:
            suffix_parts: list[str] = []
            if hint.note is not None:
                suffix_parts.append(hint.note)
            if not hint.path.exists():
                suffix_parts.append("not present")
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            lines.append(f"  - {_display_path(hint.path)}{suffix}")
    else:
        lines.append("Relevant generated files: none")

    return lines


def render_project_dependency_lines(project_id: str, config: Config) -> list[str]:
    project = require_project(config, project_id)
    lines = [f"Project: {project.project_id or project.path.as_posix()}"]
    if project.resolved_dependencies:
        lines.append(f"Resolved dependencies ({len(project.resolved_dependencies)}):")
        lines.extend(f"  - {_dependency_summary(dep)}" for dep in project.resolved_dependencies)
    else:
        lines.append("Resolved dependencies: none")
    return lines


def render_project_target_lines(project_id: str, config: Config, *, colorize: bool = True) -> list[str]:
    project = require_project(config, project_id)
    if not isinstance(project, GradleProject) or not project.is_kmp:
        raise ValueError(f"Project {project_id!r} is not a Kotlin Multiplatform project.")

    project_type = _project_type_label(project)
    rendered_type = project_type
    if colorize:
        rendered_type = _colored(project_type, _project_type_color(project_type), attrs=("bold",))

    lines = [f"{project.project_id or project.path.as_posix()}  {rendered_type}"]
    for platform in project.platforms:
        rendered_platform = platform
        if colorize:
            rendered_platform = _colored(platform, _target_platform_color(platform), attrs=("bold",))
        lines.append(f"  {rendered_platform}")
    return lines


def _repo_target_from_project(project: Project, config: Config) -> ResolvedRepoTarget:
    if project.repo_id is not None and project.repo_id in config.defined_repos:
        repo_definition = config.defined_repos[project.repo_id]
        return ResolvedRepoTarget(
            name=project.repo_id,
            path=repo_definition.path,
            repo_id=project.repo_id,
            project_ids=tuple(repo_definition.project_ids),
        )
    project_id = project.project_id or project.path.as_posix()
    return ResolvedRepoTarget(
        name=project_id,
        path=project.effective_repo_root,
        repo_id=project.repo_id,
        project_ids=(project_id,),
    )


def project_repo_payload(repo_target: ResolvedRepoTarget, config: Config) -> dict[str, object]:
    repo_definition = config.defined_repos.get(repo_target.repo_id) if repo_target.repo_id is not None else None
    if repo_definition is not None:
        repo_label = repo_definition.repo_id
        repo_path = repo_definition.path
        github_repo = repo_definition.github_repo
        gradle_root_project = repo_definition.gradle_root_project_name
        docs_project = repo_definition.docs_project_id
        project_ids = list(repo_definition.project_ids)
    else:
        project_ids = list(repo_target.project_ids)
        representative_project = require_project(config, project_ids[0]) if project_ids else None
        repo_label = repo_target.name
        repo_path = repo_target.path
        github_repo = representative_project.github_repo if representative_project is not None else None
        gradle_root_project = None
        docs_project = None

    return {
        "repo": repo_label,
        "path": _absolute_path(repo_path),
        "repoId": repo_target.repo_id,
        "githubRepo": github_repo,
        "gradleRootProject": gradle_root_project,
        "docsProject": docs_project,
        "projects": project_ids,
    }


def render_project_repo_lines(repo_target: ResolvedRepoTarget, config: Config) -> list[str]:
    repo_definition = config.defined_repos.get(repo_target.repo_id) if repo_target.repo_id is not None else None
    if repo_definition is not None:
        repo_label = repo_definition.repo_id
        repo_path = repo_definition.path
        github_repo = repo_definition.github_repo
        gradle_root_project = repo_definition.gradle_root_project_name
        docs_project = repo_definition.docs_project_id
        project_ids = list(repo_definition.project_ids)
    else:
        project_ids = list(repo_target.project_ids)
        representative_project = require_project(config, project_ids[0]) if project_ids else None
        repo_label = repo_target.name
        repo_path = repo_target.path
        github_repo = representative_project.github_repo if representative_project is not None else None
        gradle_root_project = None
        docs_project = None

    lines = [
        f"Repo: {repo_label}",
        f"Path: {_display_path(repo_path)}",
        f"Repo ID: {repo_target.repo_id or '-'}",
        f"GitHub repo: {github_repo or '-'}",
        f"Gradle root project: {gradle_root_project or '-'}",
        f"Docs project: {docs_project or '-'}",
    ]
    if project_ids:
        lines.append(f"Projects ({len(project_ids)}):")
        lines.extend(f"  - {project_id}" for project_id in project_ids)
    else:
        lines.append("Projects: none")
    return lines


def render_project_list_lines(config: Config, *, colorize: bool = True) -> list[str]:
    display_rows: list[tuple[str, str]] = []
    for project in config.defined_projects.values():
        display_rows.append((_project_display_name(project), _project_type_label(project)))

    width = max((len(label) for label, _project_type in display_rows), default=0)

    lines: list[str] = []
    active_repo_key: str | None = None
    for project in config.defined_projects.values():
        if project.is_repo_managed:
            repo_key = project.repo_id or project.effective_repo_root.as_posix()
            if repo_key != active_repo_key:
                repo_name = _repo_display_name(project)
                if colorize:
                    repo_name = _colored(repo_name, "cyan", attrs=("bold",))
                lines.append(repo_name)
                active_repo_key = repo_key
        else:
            active_repo_key = None

        label = _project_display_name(project)
        project_type = _project_type_label(project)
        padded_label = label.ljust(width)
        rendered_type = project_type
        if colorize:
            rendered_type = _colored(project_type, _project_type_color(project_type), attrs=("bold",))
        lines.append(f"{padded_label}  {rendered_type}")

    return lines


def list_projects(config: Config | None = None) -> None:
    active_config = load_config() if config is None else config
    for line in render_project_list_lines(active_config):
        print(line)


def show_projects(project_targets: list[str], config: Config | None = None, *, json_output: bool = False) -> None:
    active_config = load_config() if config is None else config
    requested_targets = inferred_project_targets(active_config, project_targets)
    if requested_targets is None:
        context = resolve_workspace_context(config=active_config)
        raise ValueError(
            contextualize_resolution_error(
                "No target was provided, and the current directory does not map to a configured project or repo. "
                "Use `where` or pass an explicit target.",
                context,
            )
        )
    project_ids = resolve_project_ids(active_config, requested_targets)
    if json_output:
        print(
            json.dumps(
                {"projects": [project_show_payload(project_id, active_config) for project_id in project_ids]},
                indent=2,
            )
        )
        return
    for index, project_id in enumerate(project_ids):
        if index:
            print()
        for line in render_project_show_lines(project_id, active_config):
            print(line)


def show_project(project_id: str, config: Config | None = None, *, json_output: bool = False) -> None:
    show_projects([project_id], config, json_output=json_output)


def show_project_dependencies(
    project_targets: list[str],
    config: Config | None = None,
    *,
    json_output: bool = False,
) -> None:
    active_config = load_config() if config is None else config
    requested_targets = inferred_project_targets(active_config, project_targets)
    if requested_targets is None:
        context = resolve_workspace_context(config=active_config)
        raise ValueError(
            contextualize_resolution_error(
                "No target was provided, and the current directory does not map to a configured project or repo. "
                "Use `where` or pass an explicit target.",
                context,
            )
        )
    project_ids = resolve_project_ids(active_config, requested_targets)
    if json_output:
        print(
            json.dumps(
                {"projects": [project_dependency_payload(project_id, active_config) for project_id in project_ids]},
                indent=2,
            )
        )
        return
    for index, project_id in enumerate(project_ids):
        if index:
            print()
        for line in render_project_dependency_lines(project_id, active_config):
            print(line)


def show_project_repos(project_targets: list[str], config: Config | None = None, *, json_output: bool = False) -> None:
    active_config = load_config() if config is None else config
    requested_targets = inferred_repo_targets(active_config, project_targets)
    project_ids = resolve_project_ids(active_config, requested_targets)
    seen_repo_keys: set[Path] = set()
    repo_targets: list[ResolvedRepoTarget] = []
    for project_id in project_ids:
        project = require_project(active_config, project_id)
        repo_target = _repo_target_from_project(project, active_config)
        repo_key = repo_target.path.resolve()
        if repo_key in seen_repo_keys:
            continue
        seen_repo_keys.add(repo_key)
        repo_targets.append(repo_target)

    if json_output:
        print(json.dumps({"repos": [project_repo_payload(repo_target, active_config) for repo_target in repo_targets]}, indent=2))
        return

    for index, repo_target in enumerate(repo_targets):
        if index:
            print()
        for line in render_project_repo_lines(repo_target, active_config):
            print(line)


def show_project_targets(
    project_targets: list[str] | None = None,
    config: Config | None = None,
    *,
    json_output: bool = False,
) -> None:
    active_config = load_config() if config is None else config
    requested_targets = inferred_project_targets(active_config, project_targets)
    resolved_project_ids = resolve_project_ids(active_config, requested_targets) if requested_targets else list(active_config.defined_projects.keys())
    kmp_project_ids = [
        project_id
        for project_id in resolved_project_ids
        if isinstance(active_config.defined_projects[project_id], GradleProject)
        and active_config.defined_projects[project_id].is_kmp
    ]

    if json_output:
        print(json.dumps({"projects": [_kmp_project_payload(project_id, active_config) for project_id in kmp_project_ids]}, indent=2))
        return

    if not kmp_project_ids:
        print("No Kotlin Multiplatform projects matched the selected targets.")
        return

    for index, project_id in enumerate(kmp_project_ids):
        if index:
            print()
        for line in render_project_target_lines(project_id, active_config):
            print(line)
