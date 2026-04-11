from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from contextlib import nullcontext, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
import re

import dev.io
from dev.build_order import toposort_projects
from dev.config import (
    DataProject,
    DotnetProject,
    GradleProject,
    PremakeProject,
    Project,
    PurescriptProject,
    PythonProject,
    load_config,
)
from dev.dotnet import dotnet_project_file
from dev.failure_context import contextualize_failure
from dev.json_types import JSONObject, JSONValue
from dev.messages import error, info, success, warning
from dev.repo_resolution import inferred_project_targets, resolve_project_ids
from dev.tasks.build import gradle_command, gradle_task_name
from dev.tasks.publish import determine_publish_target


class ReleaseBundleError(Exception):
    pass


@dataclass(frozen=True)
class RepoBundlePlan:
    repo_root: Path
    repo_name: str
    github_repo: str | None
    version_label: str
    asset_prefix: str
    output_dir: Path


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


def _json_string(value: JSONValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _update_bundle_summary(payload: JSONObject) -> None:
    results_value = payload.get("results")
    if not isinstance(results_value, list):
        payload["summary"] = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "unsupported": 0,
        }
        return

    success_count = 0
    failed_count = 0
    skipped_count = 0
    unsupported_count = 0
    for result in results_value:
        if not isinstance(result, dict):
            continue
        match _json_string(result.get("status")):
            case "success":
                success_count += 1
            case "failed":
                failed_count += 1
            case "skipped":
                skipped_count += 1
            case "unsupported":
                unsupported_count += 1
            case _:
                continue

    payload["summary"] = {
        "total": len(results_value),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "unsupported": unsupported_count,
    }


def _command_failure_message(ex: subprocess.CalledProcessError) -> str:
    return f"Release bundling command failed with exit code {ex.returncode}."


def _run_python_module(
    module: str,
    args: list[str],
    *,
    cwd: Path,
    redirect_output: bool,
) -> None:
    command = [sys.executable, "-m", module, *args]
    if redirect_output:
        subprocess.run(command, cwd=cwd, check=True, stdout=sys.stderr, stderr=sys.stderr)
        return
    subprocess.run(command, cwd=cwd, check=True)


def _require_python_module(module: str) -> None:
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as ex:
        raise ReleaseBundleError(
            f"Missing Python dependency {module!r} in the current dev environment. "
            f"Install it with `{sys.executable} -m pip install {module}`."
        ) from ex


def _disable_local_overlay(gradle_root: Path) -> tuple[Path, Path] | None:
    overlay_path = gradle_root / "settings.local.gradle.kts"
    if not overlay_path.exists():
        return None

    backup_path = gradle_root / ".settings.local.gradle.kts.release-bundle.backup"
    suffix = 1
    while backup_path.exists():
        backup_path = gradle_root / f".settings.local.gradle.kts.release-bundle.backup.{suffix}"
        suffix += 1
    overlay_path.rename(backup_path)
    return overlay_path, backup_path


def _restore_local_overlay(overlay_state: tuple[Path, Path] | None) -> None:
    if overlay_state is None:
        return
    overlay_path, backup_path = overlay_state
    if overlay_path.exists():
        overlay_path.unlink()
    if backup_path.exists():
        backup_path.rename(overlay_path)


def _asset_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    collapsed = normalized.strip("-")
    return collapsed or "asset"


def _repo_name_for_projects(repo_root: Path, projects: Sequence[Project]) -> str:
    for project in projects:
        github_repo = project.github_repo
        if github_repo is None:
            continue
        _owner, _slash, repo_name = github_repo.partition("/")
        if repo_name:
            return repo_name
    return repo_root.name


def _repo_version_label(projects: Sequence[Project]) -> str:
    versions: set[str] = set()
    for project in projects:
        match project:
            case PythonProject(version=version) | GradleProject(version=version) | DotnetProject(version=version) | PurescriptProject(version=version) | PremakeProject(version=version) | DataProject(version=version):
                if version is not None:
                    versions.add(str(version))
            case _:
                continue
    sorted_versions = sorted(versions)
    if not sorted_versions:
        return "unversioned"
    if len(sorted_versions) == 1:
        return sorted_versions[0]
    return "mixed"


def _project_id(project: Project) -> str:
    return project.project_id or project.name


def _sha256_hex(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_bundle_zip(source_dir: Path, bundle_path: Path, *, archive_prefix: str) -> int:
    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        raise ReleaseBundleError(f"No release bundle inputs found under {source_dir}.")

    if not bundle_path.parent.exists():
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path(archive_prefix) / path.relative_to(source_dir))
    return len(files)


def _write_aggregate_zip(asset_paths: Sequence[Path], aggregate_path: Path) -> None:
    if not aggregate_path.parent.exists():
        aggregate_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(aggregate_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for asset_path in sorted(asset_paths):
            archive.write(asset_path, asset_path.name)


def _write_checksum_file(path: Path, asset_paths: Sequence[Path]) -> None:
    lines = [f"{_sha256_hex(asset_path)}  {asset_path.name}" for asset_path in sorted(asset_paths)]
    dev.io.write_text_file(path, "\n".join(lines) + "\n")


def _repo_bundle_plan(projects: Sequence[Project]) -> RepoBundlePlan:
    if not projects:
        raise ReleaseBundleError("Cannot create a release bundle plan without projects.")

    repo_root = projects[0].effective_repo_root.resolve()
    repo_name = _repo_name_for_projects(repo_root, projects)
    github_repo = next((project.github_repo for project in projects if project.github_repo is not None), None)
    version_label = _repo_version_label(projects)
    asset_prefix = f"{_asset_slug(repo_name)}-{_asset_slug(version_label)}"
    output_dir = repo_root / "build" / "releases"
    return RepoBundlePlan(
        repo_root=repo_root,
        repo_name=repo_name,
        github_repo=github_repo,
        version_label=version_label,
        asset_prefix=asset_prefix,
        output_dir=output_dir,
    )


def _prepare_output_dirs(plans: Sequence[RepoBundlePlan]) -> None:
    for plan in plans:
        dev.io.delete_if_exists(plan.output_dir)
        plan.output_dir.mkdir(parents=True, exist_ok=True)


def _bundle_path(plan: RepoBundlePlan, project: Project, *, variant_suffix: str | None = None) -> Path:
    base_name = f"{plan.asset_prefix}-{_asset_slug(_project_id(project))}"
    if variant_suffix is not None:
        base_name = f"{base_name}-{_asset_slug(variant_suffix)}"
    return plan.output_dir / f"{base_name}.zip"


def _bundle_python_project(
    project: PythonProject,
    *,
    plan: RepoBundlePlan,
    redirect_output: bool,
) -> JSONObject:
    publish_target = determine_publish_target(project)
    result: JSONObject = {
        "projectId": _project_id(project),
        "kind": "python",
        "path": str(project.path.resolve()),
        "publishTarget": publish_target,
    }

    if project.quarantine:
        result["status"] = "skipped"
        result["reason"] = "quarantined"
        return result
    if not project.publish:
        result["status"] = "skipped"
        result["reason"] = "publish-disabled"
        return result
    if publish_target != "pypi":
        result["status"] = "skipped"
        result["reason"] = "unsupported-publish-target"
        return result

    _require_python_module("build")

    bundle_path = _bundle_path(plan, project)
    with tempfile.TemporaryDirectory(prefix="release-bundle-python-") as temp_dir_name:
        source_dir = Path(temp_dir_name) / "dist"
        source_dir.mkdir(parents=True, exist_ok=True)
        _run_python_module(
            "build",
            ["--sdist", "--wheel", "--outdir", str(source_dir)],
            cwd=project.path,
            redirect_output=redirect_output,
        )
        entry_count = _write_bundle_zip(source_dir, bundle_path, archive_prefix="dist")

    result["bundle"] = {
        "path": str(bundle_path.resolve()),
        "bundleKind": "python-dist",
        "archivePrefix": "dist",
        "sha256": _sha256_hex(bundle_path),
        "sizeBytes": bundle_path.stat().st_size,
        "entryCount": entry_count,
    }
    result["status"] = "success"
    return result


def _bundle_gradle_project(
    project: GradleProject,
    *,
    plan: RepoBundlePlan,
    redirect_output: bool,
) -> JSONObject:
    publish_target = determine_publish_target(project)
    result: JSONObject = {
        "projectId": _project_id(project),
        "kind": "gradle",
        "path": str(project.path.resolve()),
        "publishTarget": publish_target,
    }

    if project.quarantine:
        result["status"] = "skipped"
        result["reason"] = "quarantined"
        return result
    if not project.publish:
        result["status"] = "skipped"
        result["reason"] = "publish-disabled"
        return result
    if publish_target == "skip":
        result["status"] = "skipped"
        result["reason"] = "unsupported-publish-target"
        return result

    match publish_target:
        case "maven-central" | "jitpack":
            tasks = [gradle_task_name(project, "build"), gradle_task_name(project, "publishToMavenLocal")]
            source_dir = project.path / "build" / "publications"
            bundle_kind = "gradle-publications"
            archive_prefix = "publications"
        case "intellij-marketplace":
            tasks = [gradle_task_name(project, "verifyPlugin"), gradle_task_name(project, "buildPlugin")]
            source_dir = project.path / "build" / "distributions"
            bundle_kind = "intellij-plugin"
            archive_prefix = "distributions"
        case _:
            result["status"] = "skipped"
            result["reason"] = "unsupported-publish-target"
            return result

    gradle_root = project.effective_gradle_root
    command = [*gradle_command(gradle_root), "--no-daemon", *tasks]
    result["command"] = command
    result["gradleRoot"] = str(gradle_root.resolve())

    overlay_state = _disable_local_overlay(gradle_root)
    result["localOverlayPresentBeforeBundle"] = overlay_state is not None

    try:
        if redirect_output:
            subprocess.run(command, cwd=gradle_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
        else:
            subprocess.run(command, cwd=gradle_root, check=True)
    finally:
        _restore_local_overlay(overlay_state)

    bundle_path = _bundle_path(plan, project)
    entry_count = _write_bundle_zip(source_dir, bundle_path, archive_prefix=archive_prefix)
    result["bundle"] = {
        "path": str(bundle_path.resolve()),
        "bundleKind": bundle_kind,
        "archivePrefix": archive_prefix,
        "sourceDir": str(source_dir.resolve()),
        "sha256": _sha256_hex(bundle_path),
        "sizeBytes": bundle_path.stat().st_size,
        "entryCount": entry_count,
    }
    result["status"] = "success"
    return result


def _bundle_dotnet_project(
    project: DotnetProject,
    *,
    plan: RepoBundlePlan,
    redirect_output: bool,
) -> JSONObject:
    publish_target = determine_publish_target(project)
    result: JSONObject = {
        "projectId": _project_id(project),
        "kind": "dotnet",
        "path": str(project.path.resolve()),
        "publishTarget": publish_target,
    }

    if project.quarantine:
        result["status"] = "skipped"
        result["reason"] = "quarantined"
        return result
    if not project.publish:
        result["status"] = "skipped"
        result["reason"] = "publish-disabled"
        return result
    if publish_target != "nuget":
        result["status"] = "skipped"
        result["reason"] = "unsupported-publish-target"
        return result

    bundle_path = _bundle_path(plan, project)
    project_file = dotnet_project_file(project)
    with tempfile.TemporaryDirectory(prefix="release-bundle-dotnet-") as temp_dir_name:
        source_dir = Path(temp_dir_name) / "packages"
        source_dir.mkdir(parents=True, exist_ok=True)
        command = [
            "dotnet",
            "pack",
            str(project_file),
            "-c",
            "Release",
            "--nologo",
            "--output",
            str(source_dir),
        ]
        result["command"] = command
        try:
            if redirect_output:
                subprocess.run(command, cwd=project.effective_repo_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
            else:
                subprocess.run(command, cwd=project.effective_repo_root, check=True)
        except subprocess.CalledProcessError as ex:
            raise ReleaseBundleError(_command_failure_message(ex)) from ex
        except FileNotFoundError as ex:
            raise ReleaseBundleError("dotnet CLI not found.") from ex

        entry_count = _write_bundle_zip(source_dir, bundle_path, archive_prefix="packages")

    result["bundle"] = {
        "path": str(bundle_path.resolve()),
        "bundleKind": "dotnet-nuget",
        "archivePrefix": "packages",
        "sha256": _sha256_hex(bundle_path),
        "sizeBytes": bundle_path.stat().st_size,
        "entryCount": entry_count,
    }
    result["status"] = "success"
    return result


def _aggregate_repo_bundles(
    plan: RepoBundlePlan,
    project_results: Sequence[JSONObject],
) -> JSONObject | None:
    asset_entries: list[JSONObject] = []
    bundle_paths: list[Path] = []

    for result in project_results:
        if _json_string(result.get("status")) != "success":
            continue

        bundle_value = result.get("bundle")
        if not isinstance(bundle_value, dict):
            continue

        bundle_path_value = bundle_value.get("path")
        match bundle_path_value:
            case str() as bundle_path_text:
                bundle_path = Path(bundle_path_text)
            case _:
                continue

        bundle_paths.append(bundle_path)
        asset_entries.append(
            {
                "projectId": result.get("projectId"),
                "kind": result.get("kind"),
                "publishTarget": result.get("publishTarget"),
                "fileName": bundle_path.name,
                "path": str(bundle_path.resolve()),
                "bundleKind": bundle_value.get("bundleKind"),
                "sha256": bundle_value.get("sha256"),
                "sizeBytes": bundle_value.get("sizeBytes"),
                "entryCount": bundle_value.get("entryCount"),
            }
        )

    if not bundle_paths:
        return None

    aggregate_path = plan.output_dir / f"{plan.asset_prefix}-all.zip"
    _write_aggregate_zip(bundle_paths, aggregate_path)

    checksum_path = plan.output_dir / "SHA256SUMS"
    checksum_assets = [*bundle_paths, aggregate_path]
    _write_checksum_file(checksum_path, checksum_assets)

    aggregate_entry: JSONObject = {
        "kind": "aggregate",
        "fileName": aggregate_path.name,
        "path": str(aggregate_path.resolve()),
        "sha256": _sha256_hex(aggregate_path),
        "sizeBytes": aggregate_path.stat().st_size,
        "contains": [path.name for path in sorted(bundle_paths)],
    }

    manifest_payload: JSONObject = {
        "repo": {
            "name": plan.repo_name,
            "githubRepo": plan.github_repo,
            "path": str(plan.repo_root),
            "versionLabel": plan.version_label,
        },
        "assets": [*asset_entries, aggregate_entry],
    }
    manifest_path = plan.output_dir / "release-manifest.json"
    dev.io.write_text_file(manifest_path, json.dumps(manifest_payload, indent=2) + "\n")

    return {
        "repo": manifest_payload["repo"],
        "outputDir": str(plan.output_dir.resolve()),
        "manifestPath": str(manifest_path.resolve()),
        "checksumsPath": str(checksum_path.resolve()),
        "aggregateBundle": aggregate_entry,
        "projectBundles": asset_entries,
    }


def release_bundle(projects: str | list[str] | None = None, *, json_output: bool = False) -> int:
    requested_projects = [projects] if isinstance(projects, str) else projects
    payload: JSONObject = {
        "requestedTargets": list(requested_projects or []),
        "inferredTargets": [],
        "resolvedTargets": [],
        "topologicalOrder": [],
        "results": [],
        "repos": [],
    }
    results_payload: list[JSONObject] = []
    repo_payloads: list[JSONObject] = []
    payload["results"] = results_payload
    payload["repos"] = repo_payloads

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
                if not json_output:
                    error(contextualize_failure(str(ex), ["release", "bundle", *effective_requested_projects]))
                _update_bundle_summary(payload)
                return 1

        if selected_project_names is not None:
            payload["resolvedTargets"] = list(selected_project_names)

        order = toposort_projects(config.defined_projects, target_project=selected_project_names)
        payload["topologicalOrder"] = list(order)
        if not order:
            message = (
                "No projects found to bundle for release."
                if selected_project_names is None
                else f"No projects found for release bundle target(s): {', '.join(selected_project_names)}"
            )
            payload["error"] = message
            if not json_output:
                error(message)
            _update_bundle_summary(payload)
            return 1

        if not json_output:
            info("Topological order of projects to bundle:\n  " + ", ".join(order))

        repo_groups: dict[Path, list[Project]] = {}
        for name in order:
            project = config.defined_projects[name]
            repo_root = project.effective_repo_root.resolve()
            if repo_root not in repo_groups:
                repo_groups[repo_root] = []
            repo_groups[repo_root].append(project)

        repo_plans = {repo_root: _repo_bundle_plan(projects) for repo_root, projects in repo_groups.items()}
        _prepare_output_dirs(list(repo_plans.values()))

        failures = 0
        for name in order:
            project = config.defined_projects[name]
            plan = repo_plans[project.effective_repo_root.resolve()]
            result: JSONObject
            try:
                match project:
                    case PythonProject():
                        result = _bundle_python_project(project, plan=plan, redirect_output=json_output)
                    case DotnetProject():
                        result = _bundle_dotnet_project(project, plan=plan, redirect_output=json_output)
                    case GradleProject():
                        result = _bundle_gradle_project(project, plan=plan, redirect_output=json_output)
                    case PurescriptProject() | PremakeProject() | DataProject():
                        result = {
                            "projectId": _project_id(project),
                            "kind": _project_kind(project),
                            "path": str(project.path.resolve()),
                            "publishTarget": determine_publish_target(project),
                            "status": "unsupported",
                            "reason": "release-bundling-not-implemented",
                        }
                    case _:
                        result = {
                            "projectId": _project_id(project),
                            "kind": _project_kind(project),
                            "path": str(project.path.resolve()),
                            "publishTarget": determine_publish_target(project),
                            "status": "unsupported",
                            "reason": "unknown-project-type",
                        }
            except ReleaseBundleError as ex:
                result = {
                    "projectId": _project_id(project),
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": str(ex),
                }
            except subprocess.CalledProcessError as ex:
                result = {
                    "projectId": _project_id(project),
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": _command_failure_message(ex),
                    "returnCode": ex.returncode,
                }
            except FileNotFoundError as ex:
                result = {
                    "projectId": _project_id(project),
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": str(ex),
                }

            results_payload.append(result)
            match _json_string(result.get("status")):
                case "success":
                    if not json_output:
                        bundle_value = result.get("bundle")
                        match bundle_value:
                            case {"path": str() as bundle_path_text}:
                                success(f"Release bundle created for {name}: {bundle_path_text}")
                            case _:
                                success(f"Release bundle created for {name}.")
                case "skipped":
                    if not json_output:
                        warning(f"Skipping {name}: {result.get('reason')}")
                case "unsupported":
                    if not json_output:
                        warning(f"Unsupported release bundle target for {name}: {result.get('kind')}")
                case _:
                    failures += 1
                    if not json_output:
                        error(f"{name}: {result.get('error', 'Release bundling failed.')}")

        for repo_root, plan in repo_plans.items():
            repo_projects = repo_groups[repo_root]
            project_results = [
                result
                for result in results_payload
                if isinstance(result.get("projectId"), str)
                and any(result.get("projectId") == _project_id(project) for project in repo_projects)
            ]
            repo_summary = _aggregate_repo_bundles(plan, project_results)
            if repo_summary is not None:
                repo_payloads.append(repo_summary)
                if not json_output:
                    success(f"Aggregate release bundle created for {plan.repo_name}: {repo_summary['outputDir']}")

        _update_bundle_summary(payload)
        if failures:
            payload["error"] = f"Release bundling failed for {failures} project(s)."
            if not json_output:
                error(payload["error"])
            return 1

        if not json_output:
            success("Release bundling completed successfully.")
        return 0

    output_context = redirect_stdout(sys.stderr) if json_output else nullcontext()
    with output_context:
        exit_code = run()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code


__all__ = ["release_bundle"]
