from __future__ import annotations

import os
import py_compile
import subprocess
from collections.abc import Iterator
from pathlib import Path

from dev.build_order import toposort_projects
from dev.config import (
    Config,
    GradleProject,
    PythonProject,
    get_gradle_plugin_applications,
    load_config,
    resolve_kotlin_plugin_compiler_plugin_project,
)
from dev.messages import error, info, success, warning
from dev.repo_resolution import resolve_project_ids


def _python_source_files(root: Path) -> Iterator[Path]:
    ignore_dirs = {
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".tox",
        "build",
        "dist",
        "node_modules",
        "__pycache__",
        ".ipynb_checkpoints",
        "venv",
        ".vscode",
        "tmp",
    }

    for dirpath, dirnames, filenames in os.walk(root):
        path = Path(dirpath)
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in ignore_dirs and not dirname.startswith(".")
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            yield path / filename


def _compile_python_project(project: PythonProject) -> bool:
    source_count = 0
    for source_path in _python_source_files(project.path):
        source_count += 1
        try:
            py_compile.compile(str(source_path), doraise=True)
        except py_compile.PyCompileError as ex:
            error(f"{project.name}: failed to compile {source_path}")
            error(str(ex))
            return False

    if source_count == 0:
        warning(f"{project.name}: no Python source files found for compilation")

    return True


def _gradle_command(gradle_root: Path) -> list[str]:
    wrapper_path = gradle_root / "gradlew"
    if wrapper_path.is_file():
        if os.name == "nt":
            return ["./gradlew.bat"]
        return ["./gradlew"]
    return ["gradle"]


def _gradle_task_name(project: GradleProject, task: str) -> str:
    if project.effective_gradle_root == project.path:
        return task
    return f":{project.effective_gradle_project_name}:{task}"


def _build_gradle_project(project: GradleProject) -> bool:
    gradle_root = project.effective_gradle_root
    command = [*_gradle_command(gradle_root), "--no-daemon", _gradle_task_name(project, "build")]
    info(f"Running Gradle build for {project.name}: {' '.join(command)}")
    try:
        subprocess.run(command, cwd=gradle_root, check=True)
    except subprocess.CalledProcessError as ex:
        error(f"{project.name}: build failed with exit code {ex.returncode}")
        return False
    except FileNotFoundError:
        error(f"{project.name}: gradle wrapper or command not found (checked: {gradle_root / 'gradlew'})")
        return False
    return True


def _publish_local_compiler_plugins(
    config: Config,
    project: GradleProject,
    *,
    published: set[str],
) -> bool:
    if not (project.effective_gradle_root / "settings.local.gradle.kts").is_file():
        return True

    compiler_projects: list[GradleProject] = []
    seen: set[str] = set()
    for application in get_gradle_plugin_applications(project):
        definition = config.plugins[application.name]
        candidate = resolve_kotlin_plugin_compiler_plugin_project(config, definition)
        if candidate is None:
            continue
        if candidate.project_id in seen or candidate.project_id in published:
            continue
        seen.add(candidate.project_id)
        compiler_projects.append(candidate)

    for compiler_project in compiler_projects:
        gradle_root = compiler_project.effective_gradle_root
        command = [*_gradle_command(gradle_root), "--no-daemon", _gradle_task_name(compiler_project, "publishToMavenLocal")]
        info(f"Publishing local compiler plugin for {project.name}: {' '.join(command)}")
        try:
            subprocess.run(command, cwd=gradle_root, check=True)
        except subprocess.CalledProcessError as ex:
            error(f"{compiler_project.name}: publishToMavenLocal failed with exit code {ex.returncode}")
            return False
        except FileNotFoundError:
            error(f"{compiler_project.name}: gradle wrapper or command not found (checked: {gradle_root / 'gradlew'})")
            return False
        published.add(compiler_project.project_id)

    return True


def build(projects: str | list[str] | None = None) -> None:
    config = load_config()
    requested_projects = [projects] if isinstance(projects, str) else projects
    selected_project_names: list[str] | None = None
    if requested_projects:
        try:
            selected_project_names = resolve_project_ids(config, requested_projects)
        except ValueError as ex:
            error(str(ex))
            return

    order = toposort_projects(config.defined_projects, target_project=selected_project_names)
    if not order:
        if selected_project_names is None:
            error("No projects found to build or cycle in dependencies.")
            return
        error(f"No projects found for build target(s): {', '.join(selected_project_names)}")
        return

    target_project = config.defined_projects[selected_project_names[0]] if selected_project_names else None
    if target_project is not None and not isinstance(target_project, (GradleProject, PythonProject)):
        error(f"Project {selected_project_names[0]} is not buildable in this command.")
        return

    if selected_project_names is not None and len(selected_project_names) > 1:
        unsupported_targets = [
            project_name
            for project_name in selected_project_names
            if not isinstance(config.defined_projects[project_name], (GradleProject, PythonProject))
        ]
        if unsupported_targets:
            error("Unsupported build target(s): " + ", ".join(unsupported_targets))
            return

    info("Topological order of projects to build:\n  " + ", ".join(order))
    executed_count = 0
    published_local_compiler_plugins: set[str] = set()

    for name in order:
        project = config.defined_projects[name]
        if project.quarantine:
            warning(f"Skipping {name}: quarantined")
            continue

        match project:
            case GradleProject():
                if not _publish_local_compiler_plugins(
                    config,
                    project,
                    published=published_local_compiler_plugins,
                ):
                    error(f"Build failed for {name}.")
                    return
                ok = _build_gradle_project(project)
            case PythonProject():
                ok = _compile_python_project(project)
            case _:
                if target_project is not None:
                    error(f"{name} is not buildable by this command.")
                    return
                warning(f"Skipping unsupported project type for build: {name}")
                continue

        executed_count += 1

        if not ok:
            error(f"Build failed for {name}.")
            return

    if executed_count == 0:
        warning(
            "No build command executed for "
            f"{', '.join(selected_project_names) if selected_project_names else 'requested projects'}."
        )
    else:
        success("Build completed successfully in topological order.")


__all__ = ["build"]
