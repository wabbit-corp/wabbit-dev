from __future__ import annotations

import io
import importlib
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from contextlib import nullcontext, redirect_stdout
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from functools import lru_cache
from pathlib import Path, PurePosixPath

from dev.build_order import toposort_projects
from dev.config import (
    Config,
    DataProject,
    Dependency,
    DependencyTarget,
    GradleProject,
    IntellijPlugin,
    PremakeProject,
    Project,
    PurescriptProject,
    PythonProject,
    load_config,
)
from dev.failure_context import contextualize_failure
from dev.json_types import JSONObject, JSONValue
from dev.maven import MavenMetadata
from dev.messages import error, info, success, warning
from dev.python_sdist_policy import python_check_manifest_ignore_patterns
from dev.repo_resolution import inferred_project_targets, resolve_project_ids
from dev.tasks.build import gradle_command, gradle_task_name
from dev.tasks.publish import determine_publish_target

MAVEN_CENTRAL_BASE_URL = (
    "https://repo1.maven.org/maven2/"  # check:ignore E_HARDCODED_URL value=https://repo1.maven.org/maven2/
)


class ReleaseVerifyError(Exception):
    pass


def _project_kind(project: Project) -> str:
    if isinstance(project, GradleProject):
        return "gradle"
    if isinstance(project, PythonProject):
        return "python"
    return type(project).__name__.removesuffix("Project").lower()


def _iter_project_dependencies(project: GradleProject) -> list[Dependency]:
    dependencies = list(project.resolved_dependencies)
    for source_set_dependencies in project.source_set_dependencies.values():
        dependencies.extend(source_set_dependencies)
    return dependencies


def _direct_gradle_dependency_projects(config: Config, project: GradleProject) -> list[GradleProject]:
    dependency_projects: list[GradleProject] = []
    seen: set[str] = set()
    defined_projects = config.defined_projects

    for dependency in _iter_project_dependencies(project):
        target = dependency.target
        if not isinstance(target, DependencyTarget.Project):
            continue
        dependency_project = defined_projects.get(target.project)
        if not isinstance(dependency_project, GradleProject):
            continue
        dependency_key = dependency_project.project_id or dependency_project.name
        if dependency_key in seen:
            continue
        seen.add(dependency_key)
        dependency_projects.append(dependency_project)
    return dependency_projects


def _reachable_gradle_dependency_projects(config: Config, project: GradleProject) -> list[GradleProject]:
    reachable: list[GradleProject] = []
    seen: set[str] = set()
    queue = _direct_gradle_dependency_projects(config, project)

    while queue:
        dependency_project = queue.pop(0)
        dependency_key = dependency_project.project_id or dependency_project.name
        if dependency_key in seen:
            continue
        seen.add(dependency_key)
        reachable.append(dependency_project)
        queue.extend(_direct_gradle_dependency_projects(config, dependency_project))
    return reachable


def _dependency_coordinate_on_maven_central(project: GradleProject) -> tuple[str, str, str] | None:
    version = project.version
    if version is None:
        return None
    return project.group_name, project.effective_artifact_id, str(version)


def _cross_repo_gradle_dependencies_for_prod(config: Config, project: GradleProject) -> list[GradleProject]:
    current_repo_root = project.effective_repo_root.resolve()
    return [
        dependency_project
        for dependency_project in _reachable_gradle_dependency_projects(config, project)
        if dependency_project.effective_repo_root.resolve() != current_repo_root
    ]


@lru_cache(maxsize=256)
def _fetch_maven_central_metadata(group_id: str, artifact_id: str) -> MavenMetadata:
    import requests

    url = f"{MAVEN_CENTRAL_BASE_URL}{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return MavenMetadata.parse(response.text)


def _maven_central_preflight_for_gradle_project(config: Config, project: GradleProject) -> JSONObject:
    checked: list[JSONObject] = []
    missing: list[JSONObject] = []
    unavailable: list[JSONObject] = []

    for dependency_project in _cross_repo_gradle_dependencies_for_prod(config, project):
        project_id = dependency_project.project_id or dependency_project.name
        publish_target = determine_publish_target(dependency_project)
        coordinate = _dependency_coordinate_on_maven_central(dependency_project)

        base_entry: JSONObject = {
            "projectId": project_id,
            "path": str(dependency_project.path.resolve()),
            "publishTarget": publish_target,
        }

        if dependency_project.github_repo is None:
            missing.append(
                {
                    **base_entry,
                    "reason": "cross-repo dependency has no github_repo and cannot resolve as a published artifact",
                }
            )
            continue

        if coordinate is None:
            missing.append(
                {
                    **base_entry,
                    "reason": "cross-repo dependency has no publishable Maven coordinate",
                }
            )
            continue

        group_id, artifact_id, version = coordinate
        entry = {
            **base_entry,
            "coordinate": f"{group_id}:{artifact_id}:{version}",
        }

        try:
            metadata = _fetch_maven_central_metadata(group_id, artifact_id)
        except Exception as ex:
            status_code: int | None = None
            try:
                import requests

                if isinstance(ex, requests.HTTPError) and ex.response is not None:
                    status_code = ex.response.status_code
            except ModuleNotFoundError:
                status_code = None
            if status_code == 404:
                missing.append(
                    {
                        **entry,
                        "reason": "artifact is not present on Maven Central",
                    }
                )
            else:
                unavailable.append(
                    {
                        **entry,
                        "reason": f"could not query Maven Central metadata: {ex}",
                    }
                )
            continue

        available = version in metadata.versions
        checked.append(
            {
                **entry,
                "available": available,
            }
        )
        if not available:
            missing.append(
                {
                    **entry,
                    "reason": "artifact version is not present on Maven Central",
                }
            )

    status = "pass"
    if missing:
        status = "missing"
    elif unavailable:
        status = "unknown"

    return {
        "status": status,
        "checked": checked,
        "missing": missing,
        "unavailable": unavailable,
    }


def _disable_local_overlay(gradle_root: Path) -> tuple[Path, Path] | None:
    overlay_path = gradle_root / "settings.local.gradle.kts"
    if not overlay_path.exists():
        return None

    backup_path = gradle_root / ".settings.local.gradle.kts.release-verify.backup"
    suffix = 1
    while backup_path.exists():
        backup_path = gradle_root / f".settings.local.gradle.kts.release-verify.backup.{suffix}"
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
        package_name = "check-manifest" if module == "check_manifest" else module
        raise ReleaseVerifyError(
            f"Missing Python dependency {package_name!r} in the current dev environment. "
            f"Install it with `{sys.executable} -m pip install {package_name}`."
        ) from ex


def _find_first_file(project_path: Path, *names: str) -> Path | None:
    for name in names:
        candidate = project_path / name
        if candidate.is_file():
            return candidate
    return None


def _normalized_url(url: str | None) -> str | None:
    if url is None:
        return None
    normalized = url.strip()
    if not normalized:
        return None
    return normalized.rstrip("/")


def _expected_metadata_urls(project: PythonProject) -> set[str]:
    expected: set[str] = set()
    for candidate in (project.homepage, project.repository):
        normalized = _normalized_url(candidate)
        if normalized is not None:
            expected.add(normalized)
    if project.github_repo:
        expected.add(f"https://github.com/{project.github_repo}".rstrip("/"))
    return expected


def _parse_metadata_urls(metadata: EmailMessage) -> set[str]:
    home_page = metadata.get("Home-page")
    values: set[str] = set()
    normalized = _normalized_url(home_page)
    if normalized is not None:
        values.add(normalized)
    for value in metadata.get_all("Project-URL", []):
        _label, _comma, url = value.partition(",")
        normalized_url = _normalized_url(url)
        if normalized_url is not None:
            values.add(normalized_url)
    return values


def _wheel_contains_test_modules(names: list[str]) -> list[str]:
    suspicious: list[str] = []
    for name in names:
        path = PurePosixPath(name)
        if path.suffix != ".py":
            continue
        if path.name == "tests.py" or path.name.startswith("test_"):
            suspicious.append(name)
            continue
        if any(part in {"test", "tests"} for part in path.parts[:-1]):
            suspicious.append(name)
    return suspicious


def _read_wheel_metadata(wheel_path: Path) -> tuple[EmailMessage, list[str], str]:
    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()
        metadata_path = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        if metadata_path is None:
            raise ReleaseVerifyError(f"{wheel_path.name} is missing a .dist-info/METADATA file.")
        metadata_bytes = archive.read(metadata_path)
    metadata = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
    return metadata, names, metadata_path


def _sdist_entries(sdist_path: Path) -> list[str]:
    suffixes = sdist_path.suffixes
    if suffixes[-2:] == [".tar", ".gz"] or suffixes[-1:] == [".tgz"]:
        with tarfile.open(sdist_path, "r:*") as archive:
            return [member.name for member in archive.getmembers() if member.name]
    if sdist_path.suffix == ".zip":
        with zipfile.ZipFile(sdist_path) as archive:
            return archive.namelist()
    raise ReleaseVerifyError(f"Unsupported sdist format for {sdist_path.name}.")


def _sdist_contains(entries: list[str], *, basename: str) -> bool:
    expected = basename.casefold()
    return any(PurePosixPath(entry).name.casefold() == expected for entry in entries)


def _summarize_python_artifacts(project: PythonProject, out_dir: Path) -> JSONObject:
    wheels = sorted(out_dir.glob("*.whl"))
    sdists = sorted([*out_dir.glob("*.tar.gz"), *out_dir.glob("*.zip")])
    if not wheels:
        raise ReleaseVerifyError(f"No wheel was produced for {project.name}.")
    if not sdists:
        raise ReleaseVerifyError(f"No source distribution was produced for {project.name}.")

    readme_path = _find_first_file(project.path, "README.md", "README.rst", "README.txt")
    changelog_path = _find_first_file(project.path, "CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md", "CHANGES.rst")
    license_path = _find_first_file(project.path, "LICENSE.md", "LICENSE", "COPYING.md", "COPYING")

    if readme_path is None:
        raise ReleaseVerifyError(f"{project.name} is missing README.md or another supported README file.")
    if changelog_path is None:
        raise ReleaseVerifyError(f"{project.name} is missing CHANGELOG.md or another supported changelog file.")
    if license_path is None:
        raise ReleaseVerifyError(f"{project.name} is missing LICENSE.md or another supported license file.")

    wheel_path = wheels[0]
    sdist_path = sdists[0]
    metadata, wheel_entries, metadata_path = _read_wheel_metadata(wheel_path)
    sdist_entries = _sdist_entries(sdist_path)

    license_value = metadata.get("License")
    license_expression = metadata.get("License-Expression")
    classifiers = metadata.get_all("Classifier", [])
    has_license_metadata = bool(license_value or license_expression) or any(
        value.startswith("License ::") for value in classifiers
    )
    if not has_license_metadata:
        raise ReleaseVerifyError(f"{wheel_path.name} is missing license metadata in METADATA.")

    description_content_type = metadata.get("Description-Content-Type")
    description_body = metadata.get_payload()
    if description_content_type is None or not description_content_type.strip():
        raise ReleaseVerifyError(f"{wheel_path.name} is missing Description-Content-Type metadata for the README.")
    if not isinstance(description_body, str) or not description_body.strip():
        raise ReleaseVerifyError(f"{wheel_path.name} is missing the rendered long description body.")

    expected_urls = _expected_metadata_urls(project)
    metadata_urls = _parse_metadata_urls(metadata)
    if expected_urls and not (expected_urls & metadata_urls):
        expected_text = ", ".join(sorted(expected_urls))
        raise ReleaseVerifyError(
            f"{wheel_path.name} is missing expected homepage/repository metadata. Expected one of: {expected_text}."
        )

    suspicious_test_entries = _wheel_contains_test_modules(wheel_entries)
    if suspicious_test_entries:
        sample = ", ".join(suspicious_test_entries[:3])
        raise ReleaseVerifyError(f"{wheel_path.name} appears to package test modules: {sample}.")

    for required_name in ("pyproject.toml", readme_path.name, changelog_path.name, license_path.name):
        if not _sdist_contains(sdist_entries, basename=required_name):
            raise ReleaseVerifyError(f"{sdist_path.name} is missing {required_name}.")

    return {
        "wheel": {
            "path": str(wheel_path.resolve()),
            "metadataPath": metadata_path,
            "entryCount": len(wheel_entries),
        },
        "sdist": {
            "path": str(sdist_path.resolve()),
            "entryCount": len(sdist_entries),
        },
        "metadata": {
            "licensePresent": True,
            "descriptionContentType": description_content_type,
            "urls": sorted(metadata_urls),
        },
    }


def _verify_python_project(
    project: PythonProject,
    *,
    redirect_output: bool,
) -> JSONObject:
    result: JSONObject = {
        "projectId": project.project_id or project.name,
        "kind": "python",
        "path": str(project.path.resolve()),
        "publishTarget": determine_publish_target(project),
        "checks": [],
    }

    if project.quarantine:
        result["status"] = "skipped"
        result["reason"] = "quarantined"
        return result
    if not project.publish:
        result["status"] = "skipped"
        result["reason"] = "publish-disabled"
        return result
    if determine_publish_target(project) != "pypi":
        result["status"] = "skipped"
        result["reason"] = "unsupported-publish-target"
        return result

    for module in ("build", "twine", "check_manifest"):
        _require_python_module(module)

    result["checks"] = [
        {"name": "build", "status": "pass"},
        {"name": "twine-check", "status": "pass"},
        {"name": "check-manifest", "status": "pass"},
        {"name": "artifact-sanity", "status": "pass"},
    ]

    with tempfile.TemporaryDirectory(prefix="release-verify-") as temp_dir_name:
        out_dir = Path(temp_dir_name)
        _run_python_module(
            "build",
            ["--sdist", "--wheel", "--outdir", str(out_dir)],
            cwd=project.path,
            redirect_output=redirect_output,
        )
        built_artifacts = sorted(str(path.resolve()) for path in out_dir.iterdir() if path.is_file())
        if not built_artifacts:
            raise ReleaseVerifyError(f"No build artifacts were produced for {project.name}.")
        artifacts: JSONObject = {"built": built_artifacts}
        result["artifacts"] = artifacts

        _run_python_module(
            "twine",
            ["check", *built_artifacts],
            cwd=project.path,
            redirect_output=redirect_output,
        )
        _run_python_module(
            "check_manifest",
            [
                "--ignore",
                ",".join(python_check_manifest_ignore_patterns(project.path)),
            ],
            cwd=project.path,
            redirect_output=redirect_output,
        )
        artifacts.update(_summarize_python_artifacts(project, out_dir))

    result["status"] = "success"
    return result


def _intellij_feature(project: GradleProject) -> IntellijPlugin:
    feature = project.resolved_features.get("intellij-plugin")
    match feature:
        case IntellijPlugin() as intellij_feature:
            return intellij_feature
        case _:
            raise ReleaseVerifyError(f"{project.name} is missing required intellij-plugin feature metadata.")


def _normalized_xml_text(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed if collapsed else None


def _display_optional_text(value: str | None) -> str:
    return value if value is not None else "(missing)"


def _packaged_plugin_xml_text(root: ET.Element, tag: str) -> str | None:
    element = root.find(tag)
    if element is None:
        return None
    return _normalized_xml_text(element.text)


def _summarize_intellij_plugin_artifacts(project: GradleProject) -> JSONObject:
    feature = _intellij_feature(project)
    distributions_dir = project.path / "build" / "distributions"
    if not distributions_dir.is_dir():
        raise ReleaseVerifyError(f"{project.name} is missing build/distributions after buildPlugin.")

    built_archives = sorted(path for path in distributions_dir.iterdir() if path.is_file() and path.suffix == ".zip")
    if not built_archives:
        raise ReleaseVerifyError(f"{project.name} did not produce a plugin ZIP in build/distributions.")

    distribution_path = built_archives[0]
    with zipfile.ZipFile(distribution_path) as distribution_archive:
        distribution_entries = distribution_archive.namelist()
        plugin_jar_entry: str | None = None
        plugin_jar_entries: list[str] = []
        plugin_xml_root: ET.Element | None = None

        for entry_name in distribution_entries:
            if not entry_name.endswith(".jar"):
                continue
            with zipfile.ZipFile(io.BytesIO(distribution_archive.read(entry_name))) as jar_archive:
                jar_entries = jar_archive.namelist()
                if "META-INF/plugin.xml" not in jar_entries:
                    continue
                plugin_jar_entry = entry_name
                plugin_jar_entries = jar_entries
                try:
                    plugin_xml_root = ET.fromstring(jar_archive.read("META-INF/plugin.xml").decode("utf-8"))
                except (UnicodeDecodeError, ET.ParseError) as ex:
                    raise ReleaseVerifyError(f"{distribution_path.name} contains an unreadable META-INF/plugin.xml: {ex}.") from ex
                break

    if plugin_jar_entry is None or plugin_xml_root is None:
        raise ReleaseVerifyError(f"{distribution_path.name} does not package META-INF/plugin.xml inside any plugin JAR.")

    expected_id = _normalized_xml_text(feature.pluginId) or f"{project.group_name}.{project.name}"
    actual_id = _packaged_plugin_xml_text(plugin_xml_root, "id")
    if actual_id != expected_id:
        raise ReleaseVerifyError(
            f"{distribution_path.name} packages plugin id {_display_optional_text(actual_id)!r}; expected {expected_id!r}."
        )

    expected_name = _normalized_xml_text(feature.pluginName)
    actual_name = _packaged_plugin_xml_text(plugin_xml_root, "name")
    if expected_name is not None and actual_name != expected_name:
        raise ReleaseVerifyError(
            f"{distribution_path.name} packages plugin name {_display_optional_text(actual_name)!r}; expected {expected_name!r}."
        )

    expected_version = str(project.version) if project.version is not None else None
    actual_version = _packaged_plugin_xml_text(plugin_xml_root, "version")
    if expected_version is not None and actual_version != expected_version:
        raise ReleaseVerifyError(
            f"{distribution_path.name} packages plugin version {_display_optional_text(actual_version)!r}; expected {expected_version!r}."
        )

    if "META-INF/pluginIcon.svg" not in plugin_jar_entries:
        raise ReleaseVerifyError(
            f"{distribution_path.name} does not package META-INF/pluginIcon.svg in {plugin_jar_entry}."
        )

    return {
        "distribution": {
            "path": str(distribution_path.resolve()),
            "entryCount": len(distribution_entries),
        },
        "packagedPlugin": {
            "jarPath": plugin_jar_entry,
            "id": actual_id or "",
            "name": actual_name or "",
            "version": actual_version or "",
            "hasPluginIcon": True,
        },
    }


def _verify_gradle_project(
    config: Config,
    project: GradleProject,
    *,
    redirect_output: bool,
) -> JSONObject:
    publish_target = determine_publish_target(project)
    result: JSONObject = {
        "projectId": project.project_id or project.name,
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

    if publish_target == "maven-central":
        preflight = _maven_central_preflight_for_gradle_project(config, project)
        result["preflight"] = {"mavenCentral": preflight}
        if preflight["status"] == "missing":
            result["status"] = "skipped"
            result["reason"] = "external-project-dependencies-missing-from-maven-central"
            result["missingDependencies"] = preflight["missing"]
            return result
        if project.is_kmp:
            tasks = [gradle_task_name(project, "publishKotlinMultiplatformPublicationToMavenLocal")]
        else:
            tasks = [gradle_task_name(project, "build"), gradle_task_name(project, "publishToMavenLocal")]
    elif publish_target == "intellij-marketplace":
        tasks = [gradle_task_name(project, "verifyPlugin"), gradle_task_name(project, "buildPlugin")]
    else:
        tasks = [gradle_task_name(project, "build")]

    gradle_root = project.effective_gradle_root
    command = [*gradle_command(gradle_root), "--no-daemon", *tasks]
    result["command"] = command
    result["gradleRoot"] = str(gradle_root.resolve())

    overlay_state = _disable_local_overlay(gradle_root)
    result["localOverlayPresentBeforeVerify"] = overlay_state is not None

    try:
        if redirect_output:
            subprocess.run(command, cwd=gradle_root, check=True, stdout=sys.stderr, stderr=sys.stderr)
        else:
            subprocess.run(command, cwd=gradle_root, check=True)
    finally:
        _restore_local_overlay(overlay_state)

    if publish_target == "intellij-marketplace":
        result["artifacts"] = _summarize_intellij_plugin_artifacts(project)

    result["status"] = "success"
    return result


def _json_string(value: JSONValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _update_release_summary(payload: JSONObject) -> None:
    results = payload.get("results")
    if not isinstance(results, list):
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
    for result in results:
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
        "total": len(results),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "unsupported": unsupported_count,
    }


def _command_failure_message(ex: subprocess.CalledProcessError) -> str:
    return f"Verification command failed with exit code {ex.returncode}."


def release_verify(projects: str | list[str] | None = None, *, json_output: bool = False) -> int:
    requested_projects = [projects] if isinstance(projects, str) else projects
    payload: JSONObject = {
        "requestedTargets": list(requested_projects or []),
        "inferredTargets": [],
        "resolvedTargets": [],
        "topologicalOrder": [],
        "results": [],
    }
    results_payload: list[JSONObject] = []
    payload["results"] = results_payload

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
                    error(contextualize_failure(str(ex), ["release", "verify", *effective_requested_projects]))
                _update_release_summary(payload)
                return 1

        if selected_project_names is not None:
            payload["resolvedTargets"] = list(selected_project_names)

        order = toposort_projects(config.defined_projects, target_project=selected_project_names)
        payload["topologicalOrder"] = list(order)
        if not order:
            message = (
                "No projects found to verify for release."
                if selected_project_names is None
                else f"No projects found for release verification target(s): {', '.join(selected_project_names)}"
            )
            payload["error"] = message
            if not json_output:
                error(message)
            _update_release_summary(payload)
            return 1

        if not json_output:
            info("Topological order of projects to verify:\n  " + ", ".join(order))

        failures = 0
        for name in order:
            project = config.defined_projects[name]
            result: JSONObject
            try:
                match project:
                    case PythonProject():
                        result = _verify_python_project(project, redirect_output=json_output)
                    case GradleProject():
                        result = _verify_gradle_project(config, project, redirect_output=json_output)
                    case PurescriptProject() | PremakeProject() | DataProject():
                        result = {
                            "projectId": project.project_id or project.name,
                            "kind": _project_kind(project),
                            "path": str(project.path.resolve()),
                            "publishTarget": determine_publish_target(project),
                            "status": "unsupported",
                            "reason": "release-verification-not-implemented",
                        }
                    case _:
                        result = {
                            "projectId": project.project_id or project.name,
                            "kind": _project_kind(project),
                            "path": str(project.path.resolve()),
                            "publishTarget": determine_publish_target(project),
                            "status": "unsupported",
                            "reason": "unknown-project-type",
                        }
            except ReleaseVerifyError as ex:
                result = {
                    "projectId": project.project_id or project.name,
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": str(ex),
                }
            except subprocess.CalledProcessError as ex:
                result = {
                    "projectId": project.project_id or project.name,
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": _command_failure_message(ex),
                    "returnCode": ex.returncode,
                }
            except FileNotFoundError as ex:
                result = {
                    "projectId": project.project_id or project.name,
                    "kind": _project_kind(project),
                    "path": str(project.path.resolve()),
                    "publishTarget": determine_publish_target(project),
                    "status": "failed",
                    "error": str(ex),
                }

            results_payload.append(result)
            status = _json_string(result.get("status"))
            if status == "success":
                if not json_output:
                    success(f"Release verification passed for {name}.")
            elif status == "skipped":
                if not json_output:
                    warning(f"Skipping {name}: {result.get('reason')}")
            elif status == "unsupported":
                if not json_output:
                    warning(f"Unsupported release verification target for {name}: {result.get('kind')}")
            else:
                failures += 1
                if not json_output:
                    error(f"{name}: {result.get('error', 'Release verification failed.')}")

        _update_release_summary(payload)
        if failures:
            payload["error"] = f"Release verification failed for {failures} project(s)."
            if not json_output:
                error(payload["error"])
            return 1

        if not json_output:
            success("Release verification completed successfully.")
        return 0

    output_context = redirect_stdout(sys.stderr) if json_output else nullcontext()
    with output_context:
        exit_code = run()

    if json_output:
        print(json.dumps(payload, indent=2))
    return exit_code


__all__ = ["release_verify"]
