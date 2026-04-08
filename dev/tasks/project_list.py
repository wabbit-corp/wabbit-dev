from __future__ import annotations

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


def _colored(text: str, color: str, *, attrs: tuple[str, ...] = ()) -> str:
    try:
        from termcolor import colored
    except ImportError:
        return text
    return colored(text, color, attrs=list(attrs))


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


def show_project(project_id: str, config: Config | None = None) -> None:
    active_config = load_config() if config is None else config
    for line in render_project_show_lines(project_id, active_config):
        print(line)
