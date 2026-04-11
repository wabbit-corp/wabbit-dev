from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
from collections.abc import Iterator
from contextlib import nullcontext, redirect_stdout
from pathlib import Path

from dev.build_order import toposort_projects
from dev.config import (
    Config,
    DotnetProject,
    GradleProject,
    Project,
    PythonProject,
    get_gradle_plugin_applications,
    load_config,
    resolve_kotlin_plugin_compiler_plugin_project,
)
from dev.dotnet import dotnet_project_file, nuget_source_args, workspace_local_nuget_feed
from dev.failure_context import contextualize_failure
from dev.json_types import JSONObject, JSONValue
from dev.messages import error, info, success, warning
from dev.repo_resolution import inferred_project_targets, resolve_project_ids


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
        dirnames[:] = [dirname for dirname in dirnames if dirname not in ignore_dirs and not dirname.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            yield path / filename


def _project_kind(project: Project) -> str:
    match project:
        case GradleProject():
            return "gradle"
        case DotnetProject():
            return "dotnet"
        case PythonProject():
            return "python"
        case _:
            return type(project).__name__.removesuffix("Project").lower()


def _compile_python_project(project: PythonProject, *, emit_messages: bool = True) -> tuple[bool, JSONObject]:
    source_count = 0
    details: JSONObject = {
        "kind": "python",
        "path": str(project.path.resolve()),
        "sourceCount": 0,
    }
    for source_path in _python_source_files(project.path):
        source_count += 1
        try:
            py_compile.compile(str(source_path), doraise=True)
        except py_compile.PyCompileError as ex:
            details["sourceCount"] = source_count
            details["error"] = str(ex)
            details["failedSource"] = str(source_path.resolve())
            if emit_messages:
                error(f"{project.name}: failed to compile {source_path}")
                error(str(ex))
            return False, details

    if source_count == 0:
        details["warning"] = "No Python source files found for compilation."
        if emit_messages:
            warning(f"{project.name}: no Python source files found for compilation")

    details["sourceCount"] = source_count
    return True, details


def gradle_command(gradle_root: Path) -> list[str]:
    wrapper_path = gradle_root / "gradlew"
    if wrapper_path.is_file():
        if os.name == "nt":
            return ["./gradlew.bat"]
        return ["./gradlew"]
    return ["gradle"]


def gradle_task_name(project: GradleProject, task: str) -> str:
    if project.effective_gradle_root == project.path:
        return task
    return f":{project.effective_gradle_project_name}:{task}"


def build_gradle_project(
    project: GradleProject,
    *,
    emit_messages: bool = True,
    redirect_output: bool = False,
) -> tuple[bool, JSONObject]:
    gradle_root = project.effective_gradle_root
    command = [*gradle_command(gradle_root), "--no-daemon", gradle_task_name(project, "build")]
    details: JSONObject = {
        "kind": "gradle",
        "gradleRoot": str(gradle_root.resolve()),
        "command": command,
    }
    if emit_messages:
        info(f"Running Gradle build for {project.name}: {' '.join(command)}")
    try:
        if redirect_output:
            subprocess.run(command, cwd=gradle_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
        else:
            subprocess.run(command, cwd=gradle_root, check=True)
    except subprocess.CalledProcessError as ex:
        details["error"] = f"Build failed with exit code {ex.returncode}."
        details["returnCode"] = ex.returncode
        if emit_messages:
            error(f"{project.name}: build failed with exit code {ex.returncode}")
        return False, details
    except FileNotFoundError:
        details["error"] = f"Gradle wrapper or command not found (checked: {gradle_root / 'gradlew'})."
        if emit_messages:
            error(f"{project.name}: gradle wrapper or command not found (checked: {gradle_root / 'gradlew'})")
        return False, details
    return True, details


def _pack_dotnet_project_to_local_feed(
    config: Config,
    project: DotnetProject,
    *,
    emit_messages: bool,
    redirect_output: bool,
) -> tuple[bool, JSONObject]:
    workspace_root = config.workspace_root
    feed_path = None if workspace_root is None else workspace_local_nuget_feed(workspace_root)
    if feed_path is None or not project.packable:
        return True, {
            "packedToLocalFeed": False,
        }

    feed_path.mkdir(parents=True, exist_ok=True)
    project_file = dotnet_project_file(project)
    command = [
        "dotnet",
        "pack",
        str(project_file),
        "-c",
        "Debug",
        "--nologo",
        "--no-build",
        "--output",
        str(feed_path),
    ]
    if emit_messages:
        info(f"Packing local NuGet package for {project.name}: {' '.join(command)}")
    details: JSONObject = {
        "packedToLocalFeed": True,
        "localFeed": str(feed_path.resolve()),
        "packCommand": command,
    }
    try:
        if redirect_output:
            subprocess.run(command, cwd=project.effective_repo_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
        else:
            subprocess.run(command, cwd=project.effective_repo_root, check=True)
    except subprocess.CalledProcessError as ex:
        details["error"] = f"Local NuGet pack failed with exit code {ex.returncode}."
        details["returnCode"] = ex.returncode
        if emit_messages:
            error(f"{project.name}: local NuGet pack failed with exit code {ex.returncode}")
        return False, details
    except FileNotFoundError:
        details["error"] = "dotnet CLI not found."
        if emit_messages:
            error(f"{project.name}: dotnet CLI not found")
        return False, details
    return True, details


def build_dotnet_project(
    config: Config,
    project: DotnetProject,
    *,
    emit_messages: bool = True,
    redirect_output: bool = False,
) -> tuple[bool, JSONObject]:
    project_file = dotnet_project_file(project)
    workspace_root = config.workspace_root
    restore_command = [
        "dotnet",
        "restore",
        str(project_file),
        "--nologo",
        *nuget_source_args(workspace_root=workspace_root, include_local=True),
    ]
    build_command = [
        "dotnet",
        "build",
        str(project_file),
        "-c",
        "Debug",
        "--nologo",
        "--no-restore",
    ]
    details: JSONObject = {
        "kind": "dotnet",
        "projectFile": str(project_file.resolve()),
        "restoreCommand": restore_command,
        "command": build_command,
    }
    if workspace_root is not None:
        details["localFeed"] = str(workspace_local_nuget_feed(workspace_root).resolve())
    try:
        if emit_messages:
            info(f"Running dotnet restore for {project.name}: {' '.join(restore_command)}")
        if redirect_output:
            subprocess.run(
                restore_command,
                cwd=project.effective_repo_root,
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
            if emit_messages:
                info(f"Running dotnet build for {project.name}: {' '.join(build_command)}")
            subprocess.run(
                build_command,
                cwd=project.effective_repo_root,
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
        else:
            subprocess.run(restore_command, cwd=project.effective_repo_root, check=True)
            if emit_messages:
                info(f"Running dotnet build for {project.name}: {' '.join(build_command)}")
            subprocess.run(build_command, cwd=project.effective_repo_root, check=True)
    except subprocess.CalledProcessError as ex:
        details["error"] = f"Build failed with exit code {ex.returncode}."
        details["returnCode"] = ex.returncode
        if emit_messages:
            error(f"{project.name}: build failed with exit code {ex.returncode}")
        return False, details
    except FileNotFoundError:
        details["error"] = "dotnet CLI not found."
        if emit_messages:
            error(f"{project.name}: dotnet CLI not found")
        return False, details

    pack_ok, pack_details = _pack_dotnet_project_to_local_feed(
        config,
        project,
        emit_messages=emit_messages,
        redirect_output=redirect_output,
    )
    details.update(pack_details)
    return pack_ok, details


def _publish_local_compiler_plugins(
    config: Config,
    project: GradleProject,
    *,
    published: set[str],
    emit_messages: bool = True,
    redirect_output: bool = False,
) -> tuple[bool, list[JSONObject], str | None]:
    if not (project.effective_gradle_root / "settings.local.gradle.kts").is_file():
        return True, [], None

    compiler_projects: list[GradleProject] = []
    seen: set[str] = set()
    for application in get_gradle_plugin_applications(project):
        definition = config.plugins[application.name]
        candidate = resolve_kotlin_plugin_compiler_plugin_project(config, definition)
        if candidate is None:
            continue
        candidate_key = candidate.project_id or str(candidate.path.resolve())
        if candidate_key in seen or candidate_key in published:
            continue
        seen.add(candidate_key)
        compiler_projects.append(candidate)

    actions: list[JSONObject] = []
    for compiler_project in compiler_projects:
        gradle_root = compiler_project.effective_gradle_root
        command = [
            *gradle_command(gradle_root),
            "--no-daemon",
            gradle_task_name(compiler_project, "publishToMavenLocal"),
        ]
        actions.append(
            {
                "projectId": compiler_project.project_id,
                "gradleRoot": str(gradle_root.resolve()),
                "command": command,
            }
        )
        if emit_messages:
            info(f"Publishing local compiler plugin for {project.name}: {' '.join(command)}")
        try:
            if redirect_output:
                subprocess.run(command, cwd=gradle_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
            else:
                subprocess.run(command, cwd=gradle_root, check=True)
        except subprocess.CalledProcessError as ex:
            message = f"{compiler_project.name}: publishToMavenLocal failed with exit code {ex.returncode}"
            if emit_messages:
                error(message)
            return False, actions, message
        except FileNotFoundError:
            message = (
                f"{compiler_project.name}: gradle wrapper or command not found (checked: {gradle_root / 'gradlew'})"
            )
            if emit_messages:
                error(message)
            return False, actions, message
        published.add(compiler_project.project_id or str(compiler_project.path.resolve()))

    return True, actions, None


def _json_string(value: JSONValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _update_build_summary(payload: JSONObject) -> None:
    results = payload.get("results")
    if not isinstance(results, list):
        payload["summary"] = {
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
        }
        return

    success_count = 0
    skipped_count = 0
    failed_count = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        match _json_string(result.get("status")):
            case "success":
                success_count += 1
            case "skipped":
                skipped_count += 1
            case "failed":
                failed_count += 1
            case _:
                continue
    payload["summary"] = {
        "total": len(results),
        "success": success_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }


def build(projects: str | list[str] | None = None, *, json_output: bool = False) -> int:
    requested_projects = [projects] if isinstance(projects, str) else projects
    results_payload: list[JSONObject] = []
    payload: JSONObject = {
        "requestedTargets": list(requested_projects or []),
        "inferredTargets": [],
        "resolvedTargets": [],
        "topologicalOrder": [],
        "results": results_payload,
    }

    def run() -> int:
        config = load_config()
        effective_requested_projects = inferred_project_targets(config, requested_projects)
        if requested_projects is None and effective_requested_projects is not None:
            payload["inferredTargets"] = list(effective_requested_projects)

        selected_project_names: list[str] | None = None
        if effective_requested_projects:
            try:
                selected_project_names = resolve_project_ids(config, effective_requested_projects)
            except ValueError as ex:
                payload["error"] = str(ex)
                error(contextualize_failure(str(ex), ["build", *effective_requested_projects]))
                _update_build_summary(payload)
                return 1

        if selected_project_names is not None:
            payload["resolvedTargets"] = list(selected_project_names)

        order = toposort_projects(config.defined_projects, target_project=selected_project_names)
        payload["topologicalOrder"] = list(order)
        if not order:
            if selected_project_names is None:
                message = "No projects found to build or cycle in dependencies."
            else:
                message = f"No projects found for build target(s): {', '.join(selected_project_names)}"
            payload["error"] = message
            error(message)
            _update_build_summary(payload)
            return 1

        if selected_project_names is None:
            target_project_name = None
        else:
            target_project_name = selected_project_names[0]
        target_project = config.defined_projects[target_project_name] if target_project_name is not None else None
        if target_project is not None and not isinstance(target_project, (GradleProject, DotnetProject, PythonProject)):
            assert target_project_name is not None
            message = f"Project {target_project_name} is not buildable in this command."
            payload["error"] = message
            error(message)
            _update_build_summary(payload)
            return 1

        if selected_project_names is not None and len(selected_project_names) > 1:
            unsupported_targets = [
                project_name
                for project_name in selected_project_names
                if not isinstance(config.defined_projects[project_name], (GradleProject, DotnetProject, PythonProject))
            ]
            if unsupported_targets:
                message = "Unsupported build target(s): " + ", ".join(unsupported_targets)
                payload["error"] = message
                error(message)
                _update_build_summary(payload)
                return 1

        if not json_output:
            info("Topological order of projects to build:\n  " + ", ".join(order))
        published_local_compiler_plugins: set[str] = set()

        for name in order:
            project = config.defined_projects[name]
            result: JSONObject = {
                "projectId": name,
                "kind": _project_kind(project),
            }
            result["path"] = str(project.path.resolve())

            if project.quarantine:
                result["status"] = "skipped"
                result["reason"] = "quarantined"
                results_payload.append(result)
                warning(f"Skipping {name}: quarantined")
                continue

            match project:
                case GradleProject():
                    ok_publish, compiler_actions, publish_error = _publish_local_compiler_plugins(
                        config,
                        project,
                        published=published_local_compiler_plugins,
                        emit_messages=not json_output,
                        redirect_output=json_output,
                    )
                    if compiler_actions:
                        result["localCompilerPluginPublishes"] = compiler_actions
                    if not ok_publish:
                        result["status"] = "failed"
                        result["error"] = publish_error
                        results_payload.append(result)
                        payload["error"] = f"Build failed for {name}."
                        error(f"Build failed for {name}.")
                        _update_build_summary(payload)
                        return 1
                    ok, details = build_gradle_project(
                        project,
                        emit_messages=not json_output,
                        redirect_output=json_output,
                    )
                case DotnetProject():
                    ok, details = build_dotnet_project(
                        config,
                        project,
                        emit_messages=not json_output,
                        redirect_output=json_output,
                    )
                case PythonProject():
                    ok, details = _compile_python_project(project, emit_messages=not json_output)
                case _:
                    if target_project is not None:
                        message = f"{name} is not buildable by this command."
                        result["status"] = "failed"
                        result["error"] = message
                        results_payload.append(result)
                        payload["error"] = message
                        error(message)
                        _update_build_summary(payload)
                        return 1
                    result["status"] = "skipped"
                    result["reason"] = "unsupported"
                    results_payload.append(result)
                    warning(f"Skipping unsupported project type for build: {name}")
                    continue

            result.update(details)
            result["status"] = "success" if ok else "failed"
            results_payload.append(result)

            if not ok:
                payload["error"] = f"Build failed for {name}."
                error(f"Build failed for {name}.")
                _update_build_summary(payload)
                return 1

        _update_build_summary(payload)
        executed_count = sum(1 for result in results_payload if _json_string(result.get("status")) == "success")
        if executed_count == 0:
            warning(
                "No build command executed for "
                f"{', '.join(selected_project_names) if selected_project_names else 'requested projects'}."
            )
        else:
            success("Build completed successfully in topological order.")
        return 0

    output_context = redirect_stdout(sys.stderr) if json_output else nullcontext()
    with output_context:
        exit_code = run()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code


__all__ = ["build", "build_gradle_project", "gradle_command", "gradle_task_name"]
