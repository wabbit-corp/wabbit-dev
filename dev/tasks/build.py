from __future__ import annotations

import os
import py_compile
import subprocess
from pathlib import Path
from collections.abc import Iterator

from dev.build_order import toposort_projects
from dev.config import GradleProject, PythonProject, load_config
from dev.messages import error, info, success, warning


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
        return [str(wrapper_path)]
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


def build(projects: list[str] | None = None) -> None:
    config = load_config()
    if projects:
        missing_projects = [project_name for project_name in projects if project_name not in config.defined_projects]
        if missing_projects:
            missing = ", ".join(missing_projects)
            error(f"No such project(s): {missing}")
            return

    order = toposort_projects(config.defined_projects, target_project=projects or None)
    if not order:
        if projects is None or not projects:
            error("No projects found to build or cycle in dependencies.")
            return
        error(f"No projects found for build target(s): {', '.join(projects)}")
        return

    target_project = config.defined_projects[projects[0]] if projects else None
    if target_project is not None and not isinstance(target_project, (GradleProject, PythonProject)):
        error(f"Project {projects[0]} is not buildable in this command.")
        return

    if projects is not None and len(projects) > 1:
        unsupported_targets = [
            project_name
            for project_name in projects
            if not isinstance(config.defined_projects[project_name], (GradleProject, PythonProject))
        ]
        if unsupported_targets:
            error("Unsupported build target(s): " + ", ".join(unsupported_targets))
            return

    info("Topological order of projects to build:\n  " + ", ".join(order))
    executed_count = 0

    for name in order:
        project = config.defined_projects[name]
        if project.quarantine:
            warning(f"Skipping {name}: quarantined")
            continue

        match project:
            case GradleProject():
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
        warning(f"No build command executed for {', '.join(projects) if projects else 'requested projects'}.")
    else:
        success("Build completed successfully in topological order.")


__all__ = ["build"]
