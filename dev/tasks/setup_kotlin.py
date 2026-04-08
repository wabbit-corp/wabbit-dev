from __future__ import annotations

import os
import re
import shlex
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
from dev.config import (
    Config,
    DataProject,
    Dependency,
    DependencyTarget,
    GradleProject,
    GradleTargetSpec,
    IntellijPlugin,
    JarFileDependencyTarget,
    KmpAndroidLibrary,
    KmpJvmRuns,
    KotlinCompilerGradlePlugin,
    KotlinCompilerPlugin,
    MavenDependencyTarget,
    NpmDependencyTarget,
    PremakeProject,
    Project,
    ProjectDependencyTarget,
    PurescriptProject,
    PythonProject,
    RepoDefinition,
    get_gradle_plugin_applications,
    resolve_kotlin_compiler_plugin_id,
    resolve_kotlin_plugin_id,
    resolve_kotlin_plugin_version,
)
from dev.licenses import canonicalize_license_key, license_display_name, license_spdx_url
from dev.messages import error, warning
from dev.tasks.setup_common import RepoSetupMode, clean_text, render_template, write_banner, write_wabbit_legal_files

ANDROID_GRADLE_PLUGIN_VERSION = "8.12.0"
DEFAULT_COMPOSE_PLUGIN_VERSION = "1.9.1"
DOKKA_PLUGIN_VERSION = "2.0.0"
KOVER_PLUGIN_VERSION = "0.9.3"
INTELLIJ_GRADLE_PLUGIN_VERSION = "1.17.2"
INTELLIJ_PLATFORM_GRADLE_PLUGIN_VERSION = "2.10.4"
PAPERWEIGHT_USERDEV_PLUGIN_VERSION = "2.0.0-beta.17"
BUKKIT_PLUGIN_YML_VERSION = "0.6.0"
VANNIKTECH_MAVEN_PUBLISH_PLUGIN_VERSION = "0.36.0"
DEFAULT_PAPER_DEV_BUNDLE_VERSION = "1.21.1-R0.1-SNAPSHOT"
CONTEXT_PARAMETERS_COMPILER_FLAG = "-Xcontext-parameters"
GITHUB_SOURCE_ROOT = "https://github.com"
GITHUB_DEFAULT_BRANCH = "master"
COMPOSE_ACCESSOR_PREFIXES: tuple[tuple[str, str], ...] = (
    ("org.jetbrains.compose.runtime:runtime:", "compose.runtime"),
    ("org.jetbrains.compose.foundation:foundation:", "compose.foundation"),
    ("org.jetbrains.compose.material3:material3:", "compose.material3"),
    ("org.jetbrains.compose.material:material-icons-extended:", "compose.materialIconsExtended"),
    ("org.jetbrains.compose.ui:ui:", "compose.ui"),
    ("org.jetbrains.compose.components:components-resources:", "compose.components.resources"),
    ("org.jetbrains.compose.components:components-ui-tooling-preview:", "compose.components.uiToolingPreview"),
    ("org.jetbrains.compose.desktop:desktop-jvm:", "compose.desktop.currentOs"),
)

BUILTIN_GRADLE_PLUGIN_IDS_BY_FEATURE: dict[str, tuple[str, ...]] = {
    "kotlin": ("org.jetbrains.kotlin.jvm",),
    "kotlin-serialization": ("org.jetbrains.kotlin.plugin.serialization",),
    "kmp-compose": ("org.jetbrains.compose", "org.jetbrains.kotlin.plugin.compose"),
    "shadow-jar": ("com.gradleup.shadow",),
    "intellij-plugin": ("org.jetbrains.intellij", "org.jetbrains.intellij.platform"),
    "paper-plugin": ("io.papermc.paperweight.userdev", "net.minecrell.plugin-yml.bukkit"),
}

DEFAULT_INTELLIJ_BUNDLED_PLUGIN = "com.intellij.java"


def _parse_intellij_platform_version(version: str | None) -> tuple[int, int] | None:
    if version is None:
        return None
    match = re.fullmatch(r"(\d{4})\.(\d+)", version.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _uses_intellij_platform_gradle_plugin_v2(feature: IntellijPlugin) -> bool:
    parsed_version = _parse_intellij_platform_version(feature.ideaVersion)
    if parsed_version is not None and parsed_version >= (2025, 3):
        return True
    since_build = (feature.sinceBuild or "").strip()
    if since_build.isdigit() and int(since_build) >= 253:
        return True
    return False


def _effective_intellij_bundled_plugins(feature: IntellijPlugin) -> list[str]:
    if feature.bundledPlugins:
        return feature.bundledPlugins
    inferred_plugins = [dep for dep in feature.depends or [] if not dep.startswith("com.intellij.modules.")]
    return inferred_plugins or [DEFAULT_INTELLIJ_BUNDLED_PLUGIN]


def _renderable_gradle_features(features: Mapping[str, object]) -> dict[str, object]:
    rendered_features = dict(features)
    intellij_feature = rendered_features.get("intellij-plugin")
    if isinstance(intellij_feature, IntellijPlugin):
        rendered_features["intellij-plugin"] = replace(
            intellij_feature,
            bundledPlugins=_effective_intellij_bundled_plugins(intellij_feature),
        )
    return rendered_features


def _materialize_gradle_plugin_version_resources(project: GradleProject) -> None:
    if project.gradle_plugin_id is None:
        return
    resources_dir = project.path / "src" / "main" / "resources"
    if not resources_dir.exists():
        return

    project_version = str(project.version)
    for properties_file in resources_dir.rglob("*gradle-plugin.properties"):
        if not properties_file.is_file():
            continue
        content = properties_file.read_text(encoding="utf-8")
        updated_content = content.replace("${projectVersion}", project_version)
        updated_content = re.sub(r"(?m)^version=.*$", f"version={project_version}", updated_content)
        if updated_content != content:
            dev.io.write_text_file(properties_file, updated_content)


class GradleSetupContext(Protocol):
    @property
    def config(self) -> Config: ...

    @property
    def mode(self) -> RepoSetupMode: ...

    @property
    def repo_template(self) -> Path: ...

    @property
    def licenses(self) -> dict[str, str]: ...

    @property
    def coc(self) -> jinja2.Template: ...

    @property
    def cla(self) -> jinja2.Template: ...

    @property
    def cla_explanations(self) -> jinja2.Template: ...

    @property
    def contributor_privacy_policy(self) -> jinja2.Template: ...

    @property
    def subproject_build_template(self) -> jinja2.Template: ...

    @property
    def subproject_build_kmp_template(self) -> jinja2.Template: ...

    @property
    def gradle_release_publish_workflow_template(self) -> jinja2.Template: ...

    @property
    def gradle_snapshot_publish_workflow_template(self) -> jinja2.Template: ...

    @property
    def gradle_compiler_plugin_release_publish_workflow_template(self) -> jinja2.Template: ...

    @property
    def gradle_compiler_plugin_snapshot_publish_workflow_template(self) -> jinja2.Template: ...

    @property
    def gradle_docs_quality_workflow_template(self) -> jinja2.Template: ...

    @property
    def gradle_docs_deploy_workflow_template(self) -> jinja2.Template: ...

    @property
    def settings_template(self) -> jinja2.Template: ...

    @property
    def subproject_settings_template(self) -> jinja2.Template: ...

    @property
    def gitignore_template(self) -> jinja2.Template: ...

    @property
    def gradle_gitignore_template(self) -> jinja2.Template: ...

    @property
    def gradle_properties_template(self) -> jinja2.Template: ...


def _project_dependency_string(dependency: Dependency, gradle_project_name: str) -> str:
    modifier = dependency.scope or "implementation"
    return f'{modifier}(project(":{gradle_project_name}"))'


def _project_version_for_comment(project: Project) -> object | None:
    if isinstance(project, (GradleProject, PythonProject, PurescriptProject, PremakeProject, DataProject)):
        return project.version
    return None


def _repo_definition_for_project(ctx: GradleSetupContext, project: Project) -> RepoDefinition | None:
    if not isinstance(project, GradleProject):
        return None
    repo_id = project.repo_id
    if repo_id is None:
        return None
    return ctx.config.defined_repos.get(repo_id)


def _project_uses_repo_kotlin_version(ctx: GradleSetupContext, project: Project) -> bool:
    repo_definition = _repo_definition_for_project(ctx, project)
    return repo_definition is not None and repo_definition.default_kotlin_version is not None


def _project_uses_repo_base_version(project: GradleProject) -> bool:
    return (
        project.version_from_repo
        or "kotlin-compiler-plugin" in project.resolved_features
        or "kotlin-compiler-gradle-plugin" in project.resolved_features
    )


def _dynamic_kotlin_artifact_coordinate(artifact: str) -> str | None:
    parts = artifact.split(":")
    if len(parts) < 3 or parts[0] != "org.jetbrains.kotlin":
        return None
    group_id, artifact_id, _version, *suffix = parts
    return ":".join([group_id, artifact_id, "$kotlinVersion", *suffix])


def _render_dependency_for_mode(ctx: GradleSetupContext, project: Project, dependency: Dependency) -> str:
    target = dependency.target
    if isinstance(target, MavenDependencyTarget):
        if isinstance(project, GradleProject) and target.artifact and _project_uses_repo_kotlin_version(ctx, project):
            dynamic_artifact = _dynamic_kotlin_artifact_coordinate(target.artifact)
            if dynamic_artifact is not None:
                modifier = dependency.scope or "implementation"
                return f'{modifier}("{dynamic_artifact}")'
        if isinstance(project, GradleProject) and "kmp-compose" in project.resolved_features and target.artifact:
            for prefix, accessor in COMPOSE_ACCESSOR_PREFIXES:
                if target.artifact.startswith(prefix):
                    modifier = dependency.scope or "implementation"
                    return f"{modifier}({accessor})"
        return dependency.as_string()
    if isinstance(target, JarFileDependencyTarget):
        return dependency.as_string()
    if isinstance(target, NpmDependencyTarget):
        return dependency.as_string()

    if isinstance(target, ProjectDependencyTarget):
        name = target.project
        subproject = ctx.config.defined_projects.get(name)
        if subproject is None:
            error(f"Unknown subproject dependency: {name}")
            return dependency.as_string()

        has_github_repo = subproject.github_repo is not None
        if isinstance(subproject, GradleProject):
            artifact_name = subproject.artifact_name
            dependency_string = _project_dependency_string(dependency, subproject.effective_gradle_project_name)
        else:
            artifact_name = subproject.name
            dependency_string = dependency.as_string()

        project_version = _project_version_for_comment(subproject)
        same_repo = project.effective_repo_root == subproject.effective_repo_root

        artifact_dependency = Dependency(
            scope=dependency.scope,
            target=DependencyTarget.Maven(artifact=artifact_name, maven_repo=None),
        )

        if same_repo and isinstance(subproject, GradleProject):
            return f"{dependency_string} // {project_version}"
        if has_github_repo:
            return artifact_dependency.as_string()
        return f"{dependency_string} // {project_version}"

    error(f"Unsupported dependency target type: {type(target).__name__}")
    return dependency.as_string()


def _make_dependency_strings(ctx: GradleSetupContext, project: Project) -> tuple[list[str], list[str]]:
    other_dependencies: list[str] = []
    project_dependencies: list[str] = []
    for dep in project.resolved_dependencies:
        target = dep.target
        if isinstance(target, MavenDependencyTarget) or isinstance(target, JarFileDependencyTarget) or isinstance(
            target, NpmDependencyTarget
        ):
            other_dependencies.append(_render_dependency_for_mode(ctx, project, dep))
            continue

        if isinstance(target, ProjectDependencyTarget):
            project_dependencies.append(_render_dependency_for_mode(ctx, project, dep))
            continue

        error(f"Unsupported dependency target type: {type(target).__name__}")

    return project_dependencies, other_dependencies


def _make_source_set_dependency_strings(ctx: GradleSetupContext, project: GradleProject) -> dict[str, list[str]]:
    source_set_dependency_strings: dict[str, list[str]] = {}
    for source_set_name, dependencies in project.source_set_dependencies.items():
        source_set_dependency_strings[source_set_name] = [
            _render_dependency_for_mode(ctx, project, dependency) for dependency in dependencies
        ]
    return source_set_dependency_strings


def _compose_plugin_version(ctx: GradleSetupContext) -> str:
    compose_library = ctx.config.libraries.get("compose-runtime")
    if compose_library is not None:
        return compose_library.maven_urn.version
    return DEFAULT_COMPOSE_PLUGIN_VERSION


def _library_version(ctx: GradleSetupContext, name: str, fallback: str) -> str:
    library = ctx.config.libraries.get(name)
    if library is None:
        return fallback
    return library.maven_urn.version


def _paper_dev_bundle_version(ctx: GradleSetupContext) -> str:
    return _library_version(ctx, "paper-api", DEFAULT_PAPER_DEV_BUNDLE_VERSION)


def _builtin_gradle_plugin_ids(project: GradleProject) -> set[str]:
    builtins: set[str] = {"org.jetbrains.kotlin.multiplatform" if project.is_kmp else "org.jetbrains.kotlin.jvm"}
    for feature_name, plugin_ids in BUILTIN_GRADLE_PLUGIN_IDS_BY_FEATURE.items():
        if feature_name in project.resolved_features:
            builtins.update(plugin_ids)
    return builtins


def _extra_gradle_plugins_for_projects(
    ctx: GradleSetupContext,
    projects: Sequence[GradleProject],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    plugin_specs: list[dict[str, str]] = []
    repositories: list[dict[str, str]] = []
    seen_plugin_ids: set[str] = set()
    seen_repositories: set[str] = set()

    for project in projects:
        builtin_plugin_ids = _builtin_gradle_plugin_ids(project)
        for application in get_gradle_plugin_applications(project):
            definition = ctx.config.plugins[application.name]
            plugin_id = resolve_kotlin_plugin_id(ctx.config, definition)
            if plugin_id in builtin_plugin_ids or plugin_id in seen_plugin_ids:
                continue
            seen_plugin_ids.add(plugin_id)
            plugin_specs.append(
                {
                    "alias": application.name,
                    "plugin_id": plugin_id,
                    "version": resolve_kotlin_plugin_version(ctx.config, definition),
                }
            )
            if definition.repo is None:
                continue
            repository = ctx.config.repositories[definition.repo]
            if repository.url in seen_repositories:
                continue
            seen_repositories.add(repository.url)
            repositories.append({"name": repository.name, "url": repository.url})

    return plugin_specs, repositories


def _kotlin_compiler_plugin_options_for_project(
    ctx: GradleSetupContext,
    project: GradleProject,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for application in get_gradle_plugin_applications(project):
        if not application.compilerOptions:
            continue
        definition = ctx.config.plugins[application.name]
        compiler_plugin_id = resolve_kotlin_compiler_plugin_id(ctx.config, definition)
        for option_name, option_value in application.compilerOptions.items():
            options.append(
                {
                    "plugin_id": compiler_plugin_id,
                    "option_name": option_name,
                    "option_value": option_value,
                }
            )
    return options


def _identifier_words(value: str) -> list[str]:
    return [word for word in re.split(r"[^A-Za-z0-9]+", value) if word]


def _pascal_case(value: str) -> str:
    return "".join(word[:1].upper() + word[1:] for word in _identifier_words(value))


def _camel_case(value: str) -> str:
    words = _identifier_words(value)
    if not words:
        return "plugin"
    head, *tail = words
    return head.lower() + "".join(word[:1].upper() + word[1:] for word in tail)


def _humanize_identifier(value: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in _identifier_words(value))


def _gradle_plugin_project_context(project: GradleProject) -> dict[str, str] | None:
    plugin_id = project.gradle_plugin_id
    if plugin_id is None:
        return None

    plugin_tail = plugin_id.rsplit(".", 1)[-1]
    plugin_class_prefix = _pascal_case(plugin_tail) or "Plugin"
    plugin_label = _humanize_identifier(plugin_tail) or "Plugin"

    return {
        "gradle_plugin_id": plugin_id,
        "gradle_plugin_declaration_name": _camel_case(plugin_tail),
        "gradle_plugin_implementation_class": f"{_package_safe_name(plugin_id)}.gradle.{plugin_class_prefix}GradlePlugin",
        "gradle_plugin_display_name": f"{plugin_label} Gradle plugin",
        "gradle_plugin_description": project.description or f"Gradle plugin for {plugin_id}.",
    }


def _version_property_context(ctx: GradleSetupContext, project: GradleProject) -> dict[str, object]:
    repo_definition = _repo_definition_for_project(ctx, project)
    base_version_fallback = str(project.version) if project.version is not None else "0.0.1"
    kotlin_version_fallback = ctx.config.plugins["kotlin-jvm"].version
    if repo_definition is not None and repo_definition.default_kotlin_version is not None:
        kotlin_version_fallback = repo_definition.default_kotlin_version

    return {
        "uses_repo_base_version": _project_uses_repo_base_version(project),
        "base_version_fallback": base_version_fallback,
        "uses_repo_kotlin_version": _project_uses_repo_kotlin_version(ctx, project),
        "repo_kotlin_version_fallback": kotlin_version_fallback,
    }


def _sorted_compiler_compatibility_sources(feature: KotlinCompilerPlugin) -> list[dict[str, str]]:
    return [
        {
            "version_prefix": entry.kotlinVersionPrefix,
            "path": entry.path,
        }
        for entry in sorted(
            feature.compatibilitySources,
            key=lambda entry: (-len(entry.kotlinVersionPrefix), entry.kotlinVersionPrefix),
        )
    ]


def _kotlin_compiler_plugin_context(project: GradleProject) -> dict[str, object]:
    feature = project.resolved_features.get("kotlin-compiler-plugin")
    if not isinstance(feature, KotlinCompilerPlugin):
        return {}

    return {
        "is_kotlin_compiler_plugin_project": True,
        "compiler_plugin_publish_version_with_kotlin": feature.publishVersionWithKotlin,
        "compiler_plugin_compatibility_sources": _sorted_compiler_compatibility_sources(feature),
    }


def _snake_case_upper(value: str) -> str:
    words = _identifier_words(value)
    if not words:
        return "PLUGIN"
    return "_".join(word.upper() for word in words)


def _package_safe_name(value: str) -> str:
    segments = [segment for segment in value.split(".") if segment]
    cleaned_segments: list[str] = []
    for segment in segments:
        words = _identifier_words(segment)
        cleaned_segments.append("".join(words) if words else "plugin")
    return ".".join(cleaned_segments)


def _kotlin_compiler_gradle_plugin_context(project: GradleProject) -> dict[str, object]:
    feature = project.resolved_features.get("kotlin-compiler-gradle-plugin")
    if not isinstance(feature, KotlinCompilerGradlePlugin):
        return {}

    plugin_context = _gradle_plugin_project_context(project)
    if plugin_context is None:
        raise ValueError(f"{project.name} uses kotlin-compiler-gradle-plugin but has no gradle_plugin_id")

    plugin_tail = project.gradle_plugin_id.rsplit(".", 1)[-1] if project.gradle_plugin_id is not None else project.name
    version_package = feature.versionPackage or f"{_package_safe_name(project.gradle_plugin_id)}.gradle"
    version_class_name = feature.versionClassName or f"{_pascal_case(plugin_tail) or 'Plugin'}GradlePluginVersion"
    version_constant_name = feature.versionConstantName or f"{_snake_case_upper(plugin_tail)}_GRADLE_PLUGIN_VERSION"

    return {
        "is_kotlin_compiler_gradle_plugin_project": True,
        "linked_compiler_plugin_project_id": feature.compilerPluginProject,
        "compiler_gradle_version_package": version_package,
        "compiler_gradle_version_class_name": version_class_name,
        "compiler_gradle_version_constant_name": version_constant_name,
    }


def settings_plugin_versions(ctx: GradleSetupContext) -> dict[str, str]:
    def plugin_version(name: str, fallback: str) -> str:
        plugin = ctx.config.plugins.get(name)
        if plugin is None:
            return fallback
        return resolve_kotlin_plugin_version(ctx.config, plugin)

    kotlin_jvm_version = plugin_version("kotlin-jvm", "2.3.10")
    return {
        "kotlin_jvm_version": kotlin_jvm_version,
        "kotlin_js_version": plugin_version("kotlin-js", kotlin_jvm_version),
        "kotlin_mp_version": plugin_version("kotlin-mp", kotlin_jvm_version),
        "kotlin_serialization_version": plugin_version("kotlin-serialization", kotlin_jvm_version),
        "android_gradle_version": ANDROID_GRADLE_PLUGIN_VERSION,
        "compose_plugin_version": _compose_plugin_version(ctx),
        "shadow_version": plugin_version("shadow", "8.3.0"),
        "dokka_version": DOKKA_PLUGIN_VERSION,
        "kover_version": KOVER_PLUGIN_VERSION,
        "maven_publish_plugin_version": VANNIKTECH_MAVEN_PUBLISH_PLUGIN_VERSION,
        "intellij_gradle_plugin_version": INTELLIJ_GRADLE_PLUGIN_VERSION,
        "intellij_platform_gradle_plugin_version": INTELLIJ_PLATFORM_GRADLE_PLUGIN_VERSION,
        "paperweight_userdev_plugin_version": plugin_version(
            "paperweight-userdev",
            PAPERWEIGHT_USERDEV_PLUGIN_VERSION,
        ),
        "bukkit_plugin_yml_version": BUKKIT_PLUGIN_YML_VERSION,
    }


def settings_plugin_context(
    ctx: GradleSetupContext,
    projects: Sequence[GradleProject],
    *,
    root_path: Path | None = None,
) -> dict[str, object]:
    extra_gradle_plugins, extra_gradle_plugin_repositories = _extra_gradle_plugins_for_projects(ctx, projects)
    context: dict[str, object] = dict(settings_plugin_versions(ctx))
    context["extra_gradle_plugins"] = extra_gradle_plugins
    context["extra_gradle_plugin_repositories"] = extra_gradle_plugin_repositories
    repo_definition: RepoDefinition | None = None
    if root_path is not None:
        repo_ids = {project.repo_id for project in projects if project.repo_id is not None}
        if len(repo_ids) == 1:
            repo_definition = ctx.config.defined_repos.get(next(iter(repo_ids)))
            if repo_definition is not None and repo_definition.path.resolve() != root_path.resolve():
                repo_definition = None
    context["use_gradle_property_kotlin_version"] = (
        repo_definition is not None and repo_definition.default_kotlin_version is not None
    )
    context["repo_default_kotlin_version"] = (
        repo_definition.default_kotlin_version if repo_definition is not None else None
    )
    return context


def _local_plugin_included_build_name(relative_path: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", relative_path).strip("-")
    return f"local-plugin-{normalized or 'build'}"


def local_plugin_included_builds(
    ctx: GradleSetupContext,
    *,
    root_path: Path,
    projects: Sequence[GradleProject],
) -> list[dict[str, str]]:
    build_paths: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for project in projects:
        for application in get_gradle_plugin_applications(project):
            definition = ctx.config.plugins[application.name]
            plugin_id = resolve_kotlin_plugin_id(ctx.config, definition)
            plugin_project = next(
                (
                    candidate
                    for candidate in ctx.config.defined_projects.values()
                    if isinstance(candidate, GradleProject) and candidate.gradle_plugin_id == plugin_id
                ),
                None,
            )
            if plugin_project is None:
                continue

            build_root = plugin_project.effective_gradle_root.resolve()
            if build_root == root_path.resolve():
                continue

            relative_path = os.path.relpath(build_root, root_path)
            if relative_path in seen_paths:
                continue

            seen_paths.add(relative_path)
            build_paths.append(
                {
                    "build_path": relative_path,
                    "build_name": _local_plugin_included_build_name(relative_path),
                }
            )

    return build_paths


def _effective_targets(project: GradleProject) -> list[GradleTargetSpec]:
    if project.targets:
        return project.targets

    targets: list[GradleTargetSpec] = []
    android_library_feature = project.resolved_features.get("kmp-android-library")
    for platform in project.platforms:
        if platform == "android":
            if isinstance(android_library_feature, KmpAndroidLibrary):
                targets.append(
                    GradleTargetSpec(
                        kind="android-kmp-library",
                        namespace=android_library_feature.namespace,
                        compile_sdk=android_library_feature.compileSdk,
                        min_sdk=android_library_feature.minSdk,
                        manifest_path=android_library_feature.manifestPath,
                    )
                )
            else:
                targets.append(GradleTargetSpec(kind="android-application"))
        elif platform == "macosArm64":
            targets.append(GradleTargetSpec(kind="macosArm64", name="clientNative"))
        elif platform == "macosX64":
            targets.append(GradleTargetSpec(kind="macosX64"))
        else:
            targets.append(GradleTargetSpec(kind=platform))
    return targets


def _is_nested_gradle_project(project: GradleProject) -> bool:
    return project.effective_gradle_root != project.path


def _needs_google_repository(project: GradleProject) -> bool:
    return any(target.kind.startswith("android-") for target in _effective_targets(project))


def _has_apple_targets(project: GradleProject) -> bool:
    return any(
        target.kind in ("iosArm64", "iosSimulatorArm64", "macosX64", "macosArm64")
        for target in _effective_targets(project)
    )


def _has_wasm_targets(project: GradleProject) -> bool:
    return any(target.kind == "wasmJs" for target in _effective_targets(project))


def _apple_framework_target_names(project: GradleProject) -> list[str]:
    names: list[str] = []
    for target in _effective_targets(project):
        if target.kind == "iosArm64":
            names.append("iosArm64")
        elif target.kind == "iosSimulatorArm64":
            names.append("iosSimulatorArm64")
        elif target.kind == "macosArm64":
            names.append(target.name or "macosArm64")
        elif target.kind == "macosX64":
            names.append(target.name or "macosX64")
    return names


def _dokka_source_link_remote_url(project: GradleProject, source_root: str) -> str | None:
    github_repo = project.github_repo
    if github_repo is None:
        return None

    repo_relative_path = Path(".")
    repo_root = project.effective_repo_root
    if project.path.is_relative_to(repo_root):
        repo_relative_path = project.path.relative_to(repo_root)

    path_segments: list[str] = []
    repo_relative_posix = repo_relative_path.as_posix().strip("/")
    if repo_relative_posix not in {"", "."}:
        path_segments.append(repo_relative_posix)

    source_root_posix = source_root.strip("/")
    if source_root_posix:
        path_segments.append(source_root_posix)

    remote_path = "/".join(path_segments)
    return f"{GITHUB_SOURCE_ROOT}/{github_repo}/tree/{GITHUB_DEFAULT_BRANCH}/{remote_path}"


def _company_legal_name(ctx: GradleSetupContext) -> str:
    company_name = ctx.config.default_company_legal_name
    if company_name is None or not company_name.strip():
        raise ValueError("default-company-legal-name is required to render Kotlin project templates")
    return company_name.strip()


def _company_short_name(ctx: GradleSetupContext) -> str:
    company_name = ctx.config.default_company_short_name
    if company_name is None or not company_name.strip():
        raise ValueError("default-company-short-name is required to render Kotlin project templates")
    return company_name.strip()


def _default_source_set_names(project: GradleProject) -> set[str]:
    result = {"commonMain", "commonTest"}
    has_native_targets = False
    has_apple_targets = False
    has_ios_targets = False
    for target in _effective_targets(project):
        if target.kind == "jvm":
            result.update({"jvmMain", "jvmTest"})
        elif target.kind in ("android-application", "android-kmp-library"):
            result.update({"androidMain", "androidUnitTest"})
        elif target.kind == "js":
            result.update({"jsMain", "jsTest"})
        elif target.kind == "wasmJs":
            result.update({"wasmJsMain", "wasmJsTest"})
        elif target.kind == "iosArm64":
            has_native_targets = True
            has_apple_targets = True
            has_ios_targets = True
            result.update({"iosArm64Main", "iosArm64Test"})
        elif target.kind == "iosSimulatorArm64":
            has_native_targets = True
            has_apple_targets = True
            has_ios_targets = True
            result.update({"iosSimulatorArm64Main", "iosSimulatorArm64Test"})
        elif target.kind == "macosArm64":
            has_native_targets = True
            has_apple_targets = True
            target_name = target.name or "macosArm64"
            result.update({f"{target_name}Main", f"{target_name}Test"})
        elif target.kind == "macosX64":
            has_native_targets = True
            has_apple_targets = True
            target_name = target.name or "macosX64"
            result.update({f"{target_name}Main", f"{target_name}Test"})
        elif target.kind in ("linuxX64", "mingwX64"):
            has_native_targets = True
            target_name = target.name or target.kind
            result.update({f"{target_name}Main", f"{target_name}Test"})
    if has_native_targets:
        result.update({"nativeMain", "nativeTest"})
    if has_apple_targets:
        result.update({"appleMain", "appleTest"})
    if has_ios_targets:
        result.update({"iosMain", "iosTest"})
    return result


def _source_set_entries(
    project: GradleProject,
    source_set_dependencies: dict[str, list[str]],
) -> list[dict[str, str | list[str]]]:
    default_source_sets = _default_source_set_names(project)
    entries: list[dict[str, str | list[str]]] = []
    if not project.source_sets:
        for source_set_name, dependencies in source_set_dependencies.items():
            entries.append(
                {
                    "name": source_set_name,
                    "accessor": "getting" if source_set_name in default_source_sets else "creating",
                    "depends_on": [],
                    "dependencies": list(dependencies),
                    "kotlin_src_dirs": [],
                }
            )
        return entries

    declared_source_sets = set(project.source_sets)
    native_source_set_parents = {
        f"{(target.name or ('macosArm64' if target.kind == 'macosArm64' else 'macosX64' if target.kind == 'macosX64' else target.kind))}{suffix}": (
            "appleMain"
            if suffix == "Main" and target.kind in ("macosArm64", "macosX64")
            else "appleTest"
            if suffix == "Test" and target.kind in ("macosArm64", "macosX64")
            else "nativeMain"
            if suffix == "Main"
            else "nativeTest"
        )
        for target in _effective_targets(project)
        if target.kind in ("macosArm64", "macosX64", "linuxX64", "mingwX64")
        for suffix in ("Main", "Test")
    }

    def implicit_parent(source_set_name: str) -> str | None:
        if source_set_name == "nativeMain":
            return "commonMain"
        if source_set_name == "nativeTest":
            return "commonTest"
        if source_set_name == "appleMain":
            return "nativeMain" if "nativeMain" in declared_source_sets else "commonMain"
        if source_set_name == "appleTest":
            return "nativeTest" if "nativeTest" in declared_source_sets else "commonTest"
        if source_set_name == "iosMain":
            if "appleMain" in declared_source_sets:
                return "appleMain"
            if "nativeMain" in declared_source_sets:
                return "nativeMain"
            return "commonMain"
        if source_set_name == "iosTest":
            if "appleTest" in declared_source_sets:
                return "appleTest"
            if "nativeTest" in declared_source_sets:
                return "nativeTest"
            return "commonTest"
        if source_set_name in ("jvmMain", "androidMain"):
            return "commonMain"
        if source_set_name in ("jvmTest", "androidUnitTest"):
            return "commonTest"
        if source_set_name in ("jsMain", "wasmJsMain"):
            return "commonMain"
        if source_set_name in ("jsTest", "wasmJsTest"):
            return "commonTest"
        if source_set_name in ("iosArm64Main", "iosSimulatorArm64Main"):
            if "iosMain" in declared_source_sets:
                return "iosMain"
            if "appleMain" in declared_source_sets:
                return "appleMain"
            if "nativeMain" in declared_source_sets:
                return "nativeMain"
            return "commonMain"
        if source_set_name in ("iosArm64Test", "iosSimulatorArm64Test"):
            if "iosTest" in declared_source_sets:
                return "iosTest"
            if "appleTest" in declared_source_sets:
                return "appleTest"
            if "nativeTest" in declared_source_sets:
                return "nativeTest"
            return "commonTest"
        if source_set_name in native_source_set_parents:
            parent_name = native_source_set_parents[source_set_name]
            if parent_name == "appleMain":
                if "appleMain" in declared_source_sets:
                    return "appleMain"
                if "nativeMain" in declared_source_sets:
                    return "nativeMain"
                return "commonMain"
            if parent_name == "appleTest":
                if "appleTest" in declared_source_sets:
                    return "appleTest"
                if "nativeTest" in declared_source_sets:
                    return "nativeTest"
                return "commonTest"
            if parent_name == "nativeMain":
                if "nativeMain" in declared_source_sets:
                    return "nativeMain"
                return "commonMain"
            if "nativeTest" in declared_source_sets:
                return "nativeTest"
            return "commonTest"
        return None

    implicit_default_source_sets: list[str] = []
    seen_implicit_defaults: set[str] = set()

    def add_implicit_default_source_set(source_set_name: str) -> None:
        if source_set_name not in default_source_sets:
            return
        if source_set_name in project.source_sets:
            return
        if source_set_name in seen_implicit_defaults:
            return
        seen_implicit_defaults.add(source_set_name)
        implicit_default_source_sets.append(source_set_name)

    for source_set_name in source_set_dependencies:
        add_implicit_default_source_set(source_set_name)

    for source_set in project.source_sets.values():
        for parent in source_set.depends_on:
            add_implicit_default_source_set(parent)

    for source_set_name in implicit_default_source_sets:
        entries.append(
            {
                "name": source_set_name,
                "accessor": "getting",
                "depends_on": [],
                "dependencies": list(source_set_dependencies.get(source_set_name, [])),
                "kotlin_src_dirs": [],
            }
        )

    ordered_project_source_set_names: list[str] = []
    visited_source_sets: set[str] = set()
    active_source_sets: set[str] = set()

    def visit_source_set(source_set_name: str) -> None:
        if source_set_name in visited_source_sets:
            return
        if source_set_name in active_source_sets:
            raise ValueError(f"Cyclic KMP source set dependsOn chain detected at {project.name}.{source_set_name}")
        active_source_sets.add(source_set_name)
        source_set = project.source_sets[source_set_name]
        for parent_source_set in source_set.depends_on:
            if parent_source_set in project.source_sets:
                visit_source_set(parent_source_set)
        active_source_sets.remove(source_set_name)
        visited_source_sets.add(source_set_name)
        ordered_project_source_set_names.append(source_set_name)

    for source_set_name in project.source_sets:
        visit_source_set(source_set_name)

    for source_set_name in ordered_project_source_set_names:
        source_set = project.source_sets[source_set_name]
        depends_on = [parent for parent in source_set.depends_on if parent != implicit_parent(source_set_name)]
        entries.append(
            {
                "name": source_set_name,
                "accessor": "getting" if source_set_name in default_source_sets else "creating",
                "depends_on": depends_on,
                "dependencies": list(source_set_dependencies.get(source_set_name, [])),
                "kotlin_src_dirs": list(source_set.kotlin_src_dirs),
            }
        )
    accessor_by_name = {str(entry["name"]): str(entry["accessor"]) for entry in entries}
    for entry in entries:
        depends_on = entry["depends_on"]
        assert isinstance(depends_on, list)
        entry["depends_on_refs"] = [
            f"{parent}.get()" if accessor_by_name.get(parent) == "getting" else parent for parent in depends_on
        ]
    return entries


def _native_framework_base_name(project: GradleProject) -> str:
    parts = [part for part in project.effective_gradle_project_name.split("-") if part]
    if parts[:1] == ["kotlin"] and len(parts) > 1:
        parts = parts[1:]
    return "".join(part[0].upper() + part[1:] for part in parts)


def _android_application_target(project: GradleProject) -> GradleTargetSpec | None:
    for target in _effective_targets(project):
        if target.kind == "android-application":
            return target
    return None


def _android_kmp_library_target(project: GradleProject) -> GradleTargetSpec | None:
    for target in _effective_targets(project):
        if target.kind == "android-kmp-library":
            return target
    return None


def _github_repo_url(repo_full_name: str) -> str:
    return f"{GITHUB_SOURCE_ROOT}/{repo_full_name}"


def _github_clone_url(repo_full_name: str) -> str:
    return f"scm:git:git://github.com/{repo_full_name}.git"


def _github_ssh_connection_url(repo_full_name: str) -> str:
    return f"scm:git:ssh://git@github.com/{repo_full_name}.git"


def _github_pages_url(repo_full_name: str) -> str:
    owner, _, repo_name = repo_full_name.partition("/")
    if not owner or not repo_name:
        raise ValueError(f"Invalid GitHub repository name: {repo_full_name}")
    return f"https://{owner}.github.io/{repo_name}/"


def _supports_gradle_maven_central(project: GradleProject) -> bool:
    return (
        _is_maven_central_publishable_project(project)
        and not _is_nested_gradle_project(project)
    )


def _supports_gradle_dokka_docs(project: GradleProject) -> bool:
    return (
        _is_dokka_docs_project(project)
        and not _is_nested_gradle_project(project)
    )


def _is_maven_central_publishable_project(project: GradleProject) -> bool:
    return (
        project.publish
        and not project.quarantine
        and project.publish_target == "maven-central"
        and project.github_repo is not None
    )


def _is_dokka_docs_project(project: GradleProject) -> bool:
    return (
        project.docs_enabled
        and not project.quarantine
        and project.docs_system == "dokka"
        and project.github_repo is not None
    )


def _needs_android_setup(project: GradleProject) -> bool:
    return any(target.kind.startswith("android-") for target in _effective_targets(project))


def _pom_project_description(project: GradleProject) -> str:
    description = project.description
    if description is None or not description.strip():
        return project.name
    return description.strip()


def _maven_central_context(ctx: GradleSetupContext, project: GradleProject) -> dict[str, str | bool]:
    github_repo = project.github_repo
    if github_repo is None:
        raise ValueError(f"{project.name} requires github_repo for Maven Central publishing")

    company_name = _company_legal_name(ctx)
    repo_owner, _, _repo_name = github_repo.partition("/")
    if not repo_owner:
        raise ValueError(f"Invalid GitHub repository name for {project.name}: {github_repo}")

    license_name = license_display_name(project.license) or "Open Source"
    license_url = license_spdx_url(project.license) or _github_repo_url(github_repo)
    developer_email = ctx.config.default_company_email or ""

    return {
        "pom_name": project.name,
        "pom_artifact_id": project.effective_artifact_id,
        "pom_description": _pom_project_description(project),
        "pom_url": _github_repo_url(github_repo),
        "pom_license_name": license_name,
        "pom_license_url": license_url,
        "pom_scm_url": _github_repo_url(github_repo),
        "pom_scm_connection": _github_clone_url(github_repo),
        "pom_scm_developer_connection": _github_ssh_connection_url(github_repo),
        "pom_developer_id": repo_owner,
        "pom_developer_name": company_name,
        "pom_developer_email": developer_email,
        "pom_organization_name": company_name,
        "pom_organization_url": _github_repo_url(github_repo),
    }


def _workflow_task_name(project: GradleProject, task_name: str) -> str:
    if _is_nested_gradle_project(project):
        return f":{project.effective_gradle_project_name}:{task_name}"
    return task_name


def _workflow_command(tasks: Sequence[str], *, quiet: bool = False, extra_args: Sequence[str] = ()) -> str:
    command = ["./gradlew"]
    if quiet:
        command.append("--quiet")
    command.extend(["--no-daemon", *extra_args, *tasks])
    return shlex.join(command)


def _relative_output_path(root_path: Path, output_path: Path) -> str:
    return Path(os.path.relpath(output_path.resolve(), start=root_path.resolve())).as_posix()


def _workflow_context(
    *,
    project_name: str,
    github_repo: str,
    java_version: int,
    needs_android: bool,
    version_print_command: str,
    snapshot_version_print_command: str,
    release_validation_command: str,
    release_build_command: str,
    release_publish_command: str,
    snapshot_publish_command: str,
    docs_build_command: str,
    docs_output_dir: str,
) -> dict[str, str | bool]:
    return {
        "project_name": project_name,
        "github_repo": github_repo,
        "java_version": str(java_version),
        "needs_android": needs_android,
        "pages_url": _github_pages_url(github_repo),
        "version_print_command": version_print_command,
        "snapshot_version_print_command": snapshot_version_print_command,
        "release_validation_command": release_validation_command,
        "release_build_command": release_build_command,
        "release_publish_command": release_publish_command,
        "snapshot_publish_command": snapshot_publish_command,
        "docs_build_command": docs_build_command,
        "docs_output_dir": docs_output_dir,
    }


def _projects_need_android_setup(projects: Sequence[GradleProject]) -> bool:
    return any(_needs_android_setup(project) for project in projects)


def _gradle_workflow_context_for_projects(
    *,
    root_path: Path,
    projects: Sequence[GradleProject],
    docs_project: GradleProject | None,
    java_version: int,
) -> dict[str, str | bool]:
    if not projects:
        raise ValueError("At least one Gradle project is required for workflow generation")

    github_repo = projects[0].github_repo
    if github_repo is None:
        raise ValueError(f"{projects[0].name} requires github_repo for workflow generation")

    publish_projects = [project for project in projects if _is_maven_central_publishable_project(project)]
    snapshot_projects = [project for project in publish_projects if project.publish_snapshots]
    context_projects = [*publish_projects]
    if docs_project is not None:
        context_projects.append(docs_project)

    version_print_tasks = [_workflow_task_name(project, "printVersion") for project in publish_projects]
    snapshot_version_print_tasks = [_workflow_task_name(project, "printVersion") for project in snapshot_projects]
    release_validation_tasks = [_workflow_task_name(project, "assertReleaseVersion") for project in publish_projects]
    release_publish_tasks = [
        _workflow_task_name(project, "publishAndReleaseToMavenCentral") for project in publish_projects
    ]
    snapshot_publish_tasks = [_workflow_task_name(project, "assertSnapshotVersion") for project in snapshot_projects]
    snapshot_publish_tasks.extend(_workflow_task_name(project, "publishToMavenCentral") for project in snapshot_projects)

    docs_tasks: list[str] = []
    docs_output_dir = "build/dokka/html"
    if docs_project is not None:
        docs_tasks = [_workflow_task_name(docs_project, "dokkaGeneratePublicationHtml")]
        docs_output_dir = _relative_output_path(root_path, docs_project.path / "build" / "dokka" / "html")

    return _workflow_context(
        project_name=docs_project.name if docs_project is not None else projects[0].name,
        github_repo=github_repo,
        java_version=java_version,
        needs_android=_projects_need_android_setup(context_projects),
        version_print_command=_workflow_command(version_print_tasks or ["printVersion"], quiet=True),
        snapshot_version_print_command=_workflow_command(
            snapshot_version_print_tasks or version_print_tasks or ["printVersion"], quiet=True
        ),
        release_validation_command=_workflow_command(release_validation_tasks or ["assertReleaseVersion"]),
        release_build_command=_workflow_command(["build"]),
        release_publish_command=_workflow_command(["build", *release_publish_tasks]),
        snapshot_publish_command=_workflow_command(["build", *snapshot_publish_tasks]),
        docs_build_command=_workflow_command(["build", *docs_tasks]),
        docs_output_dir=docs_output_dir,
    )


def _compiler_plugin_repo_workflow_context(
    *,
    root_path: Path,
    repo_definition: RepoDefinition,
    projects: Sequence[GradleProject],
    java_version: int,
) -> dict[str, str | bool]:
    publish_projects = [project for project in projects if _is_maven_central_publishable_project(project)]
    compiler_plugin_projects = [
        project for project in publish_projects if isinstance(project.resolved_features.get("kotlin-compiler-plugin"), KotlinCompilerPlugin)
    ]
    if not compiler_plugin_projects:
        raise ValueError("Compiler-plugin workflow context requires at least one compiler plugin project")

    base_version_projects = [project for project in publish_projects if _project_uses_repo_base_version(project)]
    core_publish_projects = [project for project in publish_projects if project not in compiler_plugin_projects]
    if not base_version_projects:
        raise ValueError("Compiler-plugin workflow context requires at least one base-version project")

    github_repo = repo_definition.github_repo
    if github_repo is None:
        raise ValueError(f"{repo_definition.repo_id} requires github_repo for workflow generation")

    core_release_validation_tasks = [_workflow_task_name(project, "assertReleaseVersion") for project in core_publish_projects]
    core_release_publish_tasks = [
        _workflow_task_name(project, "publishAndReleaseToMavenCentral") for project in core_publish_projects
    ]
    core_snapshot_tasks = [_workflow_task_name(project, "assertSnapshotVersion") for project in core_publish_projects]
    core_snapshot_tasks.extend(_workflow_task_name(project, "publishToMavenCentral") for project in core_publish_projects)

    compiler_release_validation_tasks = [
        _workflow_task_name(project, "assertReleaseVersion") for project in compiler_plugin_projects
    ]
    compiler_release_build_tasks = [_workflow_task_name(project, "build") for project in compiler_plugin_projects]
    compiler_release_publish_tasks = [
        _workflow_task_name(project, "publishAndReleaseToMavenCentral") for project in compiler_plugin_projects
    ]
    compiler_snapshot_tasks = [_workflow_task_name(project, "assertSnapshotVersion") for project in compiler_plugin_projects]
    compiler_snapshot_tasks.extend(
        _workflow_task_name(project, "publishToMavenCentral") for project in compiler_plugin_projects
    )

    matrix_property_arg = "-PkotlinVersion=${{ matrix.kotlin-version }}"

    return {
        "project_name": projects[0].name,
        "github_repo": github_repo,
        "java_version": str(java_version),
        "needs_android": _projects_need_android_setup(publish_projects),
        "pages_url": _github_pages_url(github_repo),
        "repo_base_version_print_command": _workflow_command(
            [_workflow_task_name(project, "printBaseVersion") for project in base_version_projects],
            quiet=True,
        ),
        "core_release_validation_command": _workflow_command(
            core_release_validation_tasks or ["assertReleaseVersion"]
        ),
        "core_release_build_command": _workflow_command(["build"]),
        "core_release_publish_command": _workflow_command(["build", *core_release_publish_tasks]),
        "core_snapshot_publish_command": _workflow_command(["build", *core_snapshot_tasks]),
        "compiler_release_validation_command": _workflow_command(
            compiler_release_validation_tasks or ["assertReleaseVersion"],
            extra_args=[matrix_property_arg],
        ),
        "compiler_release_build_command": _workflow_command(
            compiler_release_build_tasks or ["build"],
            extra_args=[matrix_property_arg],
        ),
        "compiler_release_publish_command": _workflow_command(
            compiler_release_publish_tasks or ["publishAndReleaseToMavenCentral"],
            extra_args=[matrix_property_arg],
        ),
        "compiler_base_version_print_command": _workflow_command(
            [_workflow_task_name(project, "printBaseVersion") for project in compiler_plugin_projects],
            quiet=True,
            extra_args=[matrix_property_arg],
        ),
        "compiler_snapshot_publish_command": _workflow_command(
            compiler_snapshot_tasks or ["assertSnapshotVersion", "publishToMavenCentral"],
            extra_args=[matrix_property_arg],
        ),
    }


def _write_gradle_workflows(ctx: GradleSetupContext, project: GradleProject, *, java_version: int) -> None:
    workflows_dir = project.path / ".github" / "workflows"
    release_publish_path = workflows_dir / "release-publish.yml"
    snapshot_publish_path = workflows_dir / "snapshot-publish.yml"
    docs_quality_path = workflows_dir / "docs-quality.yml"
    docs_deploy_path = workflows_dir / "docs-deploy.yml"

    if _supports_gradle_maven_central(project):
        workflow_context = _gradle_workflow_context_for_projects(
            root_path=project.path,
            projects=[project],
            docs_project=project if _supports_gradle_dokka_docs(project) else None,
            java_version=java_version,
        )
        dev.io.write_text_file(
            release_publish_path,
            clean_text(render_template(ctx.gradle_release_publish_workflow_template, **workflow_context)),
        )
        if project.publish_snapshots:
            dev.io.write_text_file(
                snapshot_publish_path,
                clean_text(render_template(ctx.gradle_snapshot_publish_workflow_template, **workflow_context)),
            )
        else:
            dev.io.delete_if_exists(snapshot_publish_path)
    else:
        dev.io.delete_if_exists(release_publish_path)
        dev.io.delete_if_exists(snapshot_publish_path)

    if _supports_gradle_dokka_docs(project):
        workflow_context = _gradle_workflow_context_for_projects(
            root_path=project.path,
            projects=[project],
            docs_project=project,
            java_version=java_version,
        )
        dev.io.write_text_file(
            docs_quality_path,
            clean_text(render_template(ctx.gradle_docs_quality_workflow_template, **workflow_context)),
        )
        dev.io.write_text_file(
            docs_deploy_path,
            clean_text(render_template(ctx.gradle_docs_deploy_workflow_template, **workflow_context)),
        )
    else:
        dev.io.delete_if_exists(docs_quality_path)
        dev.io.delete_if_exists(docs_deploy_path)


def _write_gradle_repo_root_workflows(
    ctx: GradleSetupContext,
    *,
    root_path: Path,
    repo_github_repo: str | None,
    projects: Sequence[GradleProject],
    docs_project: GradleProject | None,
    java_version: int,
) -> None:
    workflows_dir = root_path / ".github" / "workflows"
    release_publish_path = workflows_dir / "release-publish.yml"
    snapshot_publish_path = workflows_dir / "snapshot-publish.yml"
    docs_quality_path = workflows_dir / "docs-quality.yml"
    docs_deploy_path = workflows_dir / "docs-deploy.yml"
    repo_definition = next(
        (
            definition
            for definition in ctx.config.defined_repos.values()
            if definition.path.resolve() == root_path.resolve()
        ),
        None,
    )

    publish_projects = [project for project in projects if _is_maven_central_publishable_project(project)]
    release_workflow_projects: list[GradleProject] = []
    if publish_projects:
        publish_versions = {str(project.version) for project in publish_projects if project.version is not None}
        if len(publish_versions) == 1:
            release_workflow_projects = publish_projects
        else:
            warning(
                f"Skipping repo-root Maven Central workflows for {root_path}: "
                f"publishable modules have differing versions {sorted(publish_versions)}"
            )

    compiler_plugin_projects = [
        project for project in publish_projects if isinstance(project.resolved_features.get("kotlin-compiler-plugin"), KotlinCompilerPlugin)
    ]
    use_compiler_plugin_workflows = (
        repo_github_repo is not None
        and bool(compiler_plugin_projects)
        and repo_definition is not None
        and bool(repo_definition.supported_kotlin_versions)
    )

    if use_compiler_plugin_workflows:
        workflow_context = _compiler_plugin_repo_workflow_context(
            root_path=root_path,
            repo_definition=repo_definition,
            projects=projects,
            java_version=java_version,
        )
        dev.io.write_text_file(
            release_publish_path,
            clean_text(render_template(ctx.gradle_compiler_plugin_release_publish_workflow_template, **workflow_context)),
        )
        if any(project.publish_snapshots for project in publish_projects):
            dev.io.write_text_file(
                snapshot_publish_path,
                clean_text(render_template(ctx.gradle_compiler_plugin_snapshot_publish_workflow_template, **workflow_context)),
            )
        else:
            dev.io.delete_if_exists(snapshot_publish_path)
    elif compiler_plugin_projects and repo_github_repo is not None and repo_definition is not None:
        warning(
            f"Skipping compiler-plugin matrix workflows for {root_path}: "
            "repo definition is missing supportedKotlinVersions"
        )
        if release_workflow_projects:
            workflow_context = _gradle_workflow_context_for_projects(
                root_path=root_path,
                projects=release_workflow_projects,
                docs_project=docs_project,
                java_version=java_version,
            )
            dev.io.write_text_file(
                release_publish_path,
                clean_text(render_template(ctx.gradle_release_publish_workflow_template, **workflow_context)),
            )
            if any(project.publish_snapshots for project in release_workflow_projects):
                dev.io.write_text_file(
                    snapshot_publish_path,
                    clean_text(render_template(ctx.gradle_snapshot_publish_workflow_template, **workflow_context)),
                )
            else:
                dev.io.delete_if_exists(snapshot_publish_path)
        else:
            dev.io.delete_if_exists(release_publish_path)
            dev.io.delete_if_exists(snapshot_publish_path)
    elif repo_github_repo is not None and release_workflow_projects:
        workflow_context = _gradle_workflow_context_for_projects(
            root_path=root_path,
            projects=release_workflow_projects,
            docs_project=docs_project,
            java_version=java_version,
        )
        dev.io.write_text_file(
            release_publish_path,
            clean_text(render_template(ctx.gradle_release_publish_workflow_template, **workflow_context)),
        )
        if any(project.publish_snapshots for project in release_workflow_projects):
            dev.io.write_text_file(
                snapshot_publish_path,
                clean_text(render_template(ctx.gradle_snapshot_publish_workflow_template, **workflow_context)),
            )
        else:
            dev.io.delete_if_exists(snapshot_publish_path)
    else:
        dev.io.delete_if_exists(release_publish_path)
        dev.io.delete_if_exists(snapshot_publish_path)

    if repo_github_repo is not None and docs_project is not None and _is_dokka_docs_project(docs_project):
        workflow_context = _gradle_workflow_context_for_projects(
            root_path=root_path,
            projects=release_workflow_projects or [docs_project],
            docs_project=docs_project,
            java_version=java_version,
        )
        dev.io.write_text_file(
            docs_quality_path,
            clean_text(render_template(ctx.gradle_docs_quality_workflow_template, **workflow_context)),
        )
        dev.io.write_text_file(
            docs_deploy_path,
            clean_text(render_template(ctx.gradle_docs_deploy_workflow_template, **workflow_context)),
        )
    else:
        dev.io.delete_if_exists(docs_quality_path)
        dev.io.delete_if_exists(docs_deploy_path)


def _cleanup_nested_gradle_project_files(project: GradleProject) -> None:
    dev.io.delete_if_exists(project.path / "settings.gradle.kts")
    dev.io.delete_if_exists(project.path / "settings.local.gradle.kts")
    dev.io.delete_if_exists(project.path / "gradlew")
    dev.io.delete_if_exists(project.path / "gradlew.bat")
    dev.io.delete_if_exists(project.path / "gradle.properties")
    dev.io.delete_if_exists(project.path / ".banner.png")
    dev.io.delete_if_exists(project.path / "CLA.md")
    dev.io.delete_if_exists(project.path / "CLA_EXPLANATIONS.md")
    dev.io.delete_if_exists(project.path / "CONTRIBUTOR_PRIVACY.md")
    dev.io.delete_if_exists(project.path / "CODE_OF_CONDUCT.md")
    dev.io.delete_if_exists(project.path / ".is-local-mode")
    dev.io.delete_if_exists(project.path / ".is-ij-mode")
    dev.io.delete_if_exists(project.path / ".is-dev-mode")
    dev.io.delete_if_exists(project.path / "gradle")


def _nested_gradle_project_keeps_license(ctx: GradleSetupContext, project: GradleProject) -> bool:
    repo_id = project.repo_id
    if repo_id is None:
        return True
    repo_definition = ctx.config.defined_repos.get(repo_id)
    if repo_definition is None:
        return True

    normalized_licenses: set[str | None] = set()
    for project_id in repo_definition.project_ids:
        candidate = ctx.config.defined_projects.get(project_id)
        if candidate is None:
            continue
        normalized_licenses.add(canonicalize_license_key(candidate.license))
    return len(normalized_licenses) != 1


def _mark_executable(path: Path) -> None:
    if not path.exists():
        return
    current_mode = path.stat().st_mode
    path.chmod(current_mode | 0o111)


def clean_gradle_build_text(text: str) -> str:
    while True:
        old_text = text
        if text.startswith("\n"):
            text = text[1:]
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"\{\n\n", "{\n", text)
        text = re.sub(r"\n\n\}", "\n}", text)
        text = clean_text(text)
        if text == old_text:
            break
    return text


@dataclass(frozen=True)
class InlineGradleBuildScript:
    imports: list[str]
    body: str


def read_optional_inline_gradle_build_script(root_path: Path) -> InlineGradleBuildScript:
    inline_script_path = root_path / "build.inline.gradle.kts"
    if not inline_script_path.exists():
        return InlineGradleBuildScript(imports=[], body="")

    lines = dev.io.read_text_file(inline_script_path).splitlines()
    imports: list[str] = []
    body_start_index = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            body_start_index = index + 1
            continue
        if line.startswith("import "):
            imports.append(line[len("import ") :].strip())
            body_start_index = index + 1
            continue
        body_start_index = index
        break
    else:
        body_start_index = len(lines)

    body = "\n".join(lines[body_start_index:]).rstrip()
    return InlineGradleBuildScript(imports=imports, body=body)


def java_version_for_features(default_java_version: int, features: Mapping[str, object]) -> int:
    # IntelliJ 2023.2 platform runtime is Java 17; targeting higher bytecode is invalid.
    if "intellij-plugin" in features:
        return 17
    return default_java_version


def kotlin_jvm_target_for_version(java_version: int) -> str:
    if java_version == 8:
        return "JVM_1_8"
    return f"JVM_{java_version}"


def _normalize_xml_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _find_child(root: ET.Element, tag: str) -> ET.Element | None:
    for child in root:
        if child.tag == tag:
            return child
    return None


def _upsert_child(root: ET.Element, tag: str, text: str) -> ET.Element:
    child = _find_child(root, tag)
    if child is None:
        child = ET.SubElement(root, tag)
    child.text = text
    return child


def _existing_depends(root: ET.Element) -> list[str]:
    result: list[str] = []
    for child in root:
        if child.tag != "depends":
            continue
        value = _normalize_xml_text(child.text)
        if value is not None:
            result.append(value)
    return result


def _sync_intellij_plugin_xml(project: GradleProject, feature: IntellijPlugin, default_vendor_name: str) -> None:
    plugin_xml_path = project.path / "src" / "main" / "resources" / "META-INF" / "plugin.xml"

    if plugin_xml_path.exists():
        existing_xml = dev.io.read_text_file(plugin_xml_path)
        try:
            root = ET.fromstring(existing_xml)
        except ET.ParseError as ex:
            error(f"Could not parse {plugin_xml_path}: {ex}")
            return
        if root.tag != "idea-plugin":
            error(f"Unexpected root tag in {plugin_xml_path}: {root.tag!r}")
            return
    else:
        root = ET.Element("idea-plugin")

    id_element = _find_child(root, "id")
    existing_id = _normalize_xml_text(id_element.text if id_element is not None else None)
    plugin_id = _normalize_xml_text(feature.pluginId) or existing_id or f"{project.group_name}.{project.name}"
    _upsert_child(root, "id", plugin_id)

    plugin_name = _normalize_xml_text(feature.pluginName) or project.name
    _upsert_child(root, "name", plugin_name)

    version_element = _find_child(root, "version")
    existing_version = _normalize_xml_text(version_element.text if version_element is not None else None)
    plugin_version = str(project.version) if project.version is not None else (existing_version or "0.0.1")
    _upsert_child(root, "version", plugin_version)

    vendor_element = _find_child(root, "vendor")
    if vendor_element is None:
        vendor_element = ET.SubElement(root, "vendor")
    vendor_name = (
        _normalize_xml_text(feature.vendorName) or _normalize_xml_text(vendor_element.text) or default_vendor_name
    )
    vendor_element.text = vendor_name
    vendor_email = _normalize_xml_text(feature.vendorEmail) or _normalize_xml_text(vendor_element.get("email"))
    vendor_url = _normalize_xml_text(feature.vendorUrl) or _normalize_xml_text(vendor_element.get("url"))
    if vendor_email is None:
        vendor_element.attrib.pop("email", None)
    else:
        vendor_element.set("email", vendor_email)
    if vendor_url is None:
        vendor_element.attrib.pop("url", None)
    else:
        vendor_element.set("url", vendor_url)

    description_element = _find_child(root, "description")
    existing_description = _normalize_xml_text(description_element.text if description_element is not None else None)
    plugin_description = (
        _normalize_xml_text(feature.pluginDescription)
        or existing_description
        or _normalize_xml_text(project.description)
        or f"Plugin {plugin_name}"
    )
    _upsert_child(root, "description", plugin_description)

    change_notes_element = _find_child(root, "change-notes")
    existing_change_notes = _normalize_xml_text(change_notes_element.text if change_notes_element is not None else None)
    plugin_change_notes = _normalize_xml_text(feature.pluginChangeNotes) or existing_change_notes or ""
    _upsert_child(root, "change-notes", plugin_change_notes)

    depends_values = feature.depends or _existing_depends(root)
    if not depends_values:
        depends_values = ["com.intellij.modules.platform"]
    depends_values = [value for value in (_normalize_xml_text(item) for item in depends_values) if value is not None]
    if not depends_values:
        depends_values = ["com.intellij.modules.platform"]
    for child in list(root):
        if child.tag == "depends":
            root.remove(child)
    for depends_value in depends_values:
        depends_element = ET.SubElement(root, "depends")
        depends_element.text = depends_value

    idea_version_element = _find_child(root, "idea-version")
    if idea_version_element is None:
        idea_version_element = ET.SubElement(root, "idea-version")
    since_build = _normalize_xml_text(feature.sinceBuild) or "232"
    idea_version_element.set("since-build", since_build)
    until_build = _normalize_xml_text(feature.untilBuild)
    if until_build is None:
        idea_version_element.attrib.pop("until-build", None)
    else:
        idea_version_element.set("until-build", until_build)

    ET.indent(root, space="    ")
    dev.io.write_text_file(plugin_xml_path, clean_text(ET.tostring(root, encoding="unicode")))


def setup_gradle_project(ctx: GradleSetupContext, project: GradleProject, interactive: bool = True) -> None:
    del interactive
    mode_value = ctx.mode.value
    java_version = java_version_for_features(ctx.config.java_version, project.resolved_features)
    kotlin_jvm_target = kotlin_jvm_target_for_version(java_version)
    compose_plugin_version = _compose_plugin_version(ctx)
    nested_gradle_project = _is_nested_gradle_project(project)
    kotlin_free_compiler_args = [CONTEXT_PARAMETERS_COMPILER_FLAG]
    kotlin_free_compiler_args.extend(
        arg for arg in project.kotlin_free_compiler_args if arg != CONTEXT_PARAMETERS_COMPILER_FLAG
    )
    extra_gradle_plugins, _extra_gradle_plugin_repositories = _extra_gradle_plugins_for_projects(ctx, [project])
    kotlin_compiler_plugin_options = _kotlin_compiler_plugin_options_for_project(ctx, project)
    publish_to_maven_central = _is_maven_central_publishable_project(project)
    maven_central_context = _maven_central_context(ctx, project) if publish_to_maven_central else {}
    template_features = _renderable_gradle_features(project.resolved_features)
    version_property_context = _version_property_context(ctx, project)
    kotlin_compiler_plugin_context = _kotlin_compiler_plugin_context(project)
    kotlin_compiler_gradle_plugin_context = _kotlin_compiler_gradle_plugin_context(project)
    intellij_feature = template_features.get("intellij-plugin")
    use_intellij_platform_gradle_plugin_v2 = (
        isinstance(intellij_feature, IntellijPlugin)
        and _uses_intellij_platform_gradle_plugin_v2(intellij_feature)
    )
    _materialize_gradle_plugin_version_resources(project)

    if project.is_kmp:
        dokka_source_link_remote_url = _dokka_source_link_remote_url(project, "src")
        company_legal_name = _company_legal_name(ctx)
        targets = _effective_targets(project)
        source_set_dependencies = _make_source_set_dependency_strings(ctx, project)
        source_set_entries = _source_set_entries(project, source_set_dependencies)
        kmp_jvm_runs_feature = project.resolved_features.get("kmp-jvm-runs")
        kmp_jvm_runs = None
        if isinstance(kmp_jvm_runs_feature, KmpJvmRuns):
            kmp_jvm_runs = kmp_jvm_runs_feature.entries

        android_application_target = _android_application_target(project)
        android_kmp_library_target = _android_kmp_library_target(project)

        inline_extra_build = read_optional_inline_gradle_build_script(project.path)
        result = render_template(
            ctx.subproject_build_kmp_template,
            project_name=project.name,
            project_group=project.group_name,
            project_version=project.version,
            published_artifact_id=project.effective_artifact_id,
            repositories=project.resolved_maven_repositories,
            kotlin_mp_version=ctx.config.plugins["kotlin-mp"].version,
            kotlin_serialization_version=ctx.config.plugins["kotlin-serialization"].version,
            android_gradle_version=ANDROID_GRADLE_PLUGIN_VERSION,
            compose_plugin_version=compose_plugin_version,
            dokka_version=DOKKA_PLUGIN_VERSION,
            kover_version=KOVER_PLUGIN_VERSION,
            java_version=java_version,
            kotlin_jvm_target=kotlin_jvm_target,
            features=template_features,
            use_root_plugin_management=nested_gradle_project,
            platforms=project.platforms,
            targets=targets,
            has_wasm_targets=_has_wasm_targets(project),
            has_apple_targets=_has_apple_targets(project),
            apple_framework_target_names=_apple_framework_target_names(project),
            needs_google_repository=_needs_google_repository(project),
            android_application_target=android_application_target,
            android_kmp_library_target=android_kmp_library_target,
            source_set_dependencies=source_set_dependencies,
            source_set_entries=source_set_entries,
            mode=mode_value,
            kmp_jvm_runs=kmp_jvm_runs,
            native_framework_base_name=_native_framework_base_name(project),
            kotlin_free_compiler_args=kotlin_free_compiler_args,
            kotlin_compiler_plugin_options=kotlin_compiler_plugin_options,
            extra_gradle_plugins=extra_gradle_plugins,
            paper_dev_bundle_version=_paper_dev_bundle_version(ctx),
            dokka_suppress_source_sets=project.dokka_suppress_source_sets,
            dokka_source_link_remote_url=dokka_source_link_remote_url or "",
            has_dokka_source_link=dokka_source_link_remote_url is not None,
            company_legal_name=company_legal_name,
            publish_to_maven_central=publish_to_maven_central,
            inline_extra_build_imports=inline_extra_build.imports,
            inline_extra_build_script=inline_extra_build.body,
            use_intellij_platform_gradle_plugin_v2=use_intellij_platform_gradle_plugin_v2,
            **version_property_context,
            **kotlin_compiler_plugin_context,
            **maven_central_context,
        )
    else:
        dokka_source_link_remote_url = _dokka_source_link_remote_url(project, "src/main/kotlin")
        company_legal_name = _company_legal_name(ctx)
        project_dependencies, other_dependencies = _make_dependency_strings(ctx, project)
        gradle_plugin_project_context = _gradle_plugin_project_context(project) or {}
        inline_extra_build = read_optional_inline_gradle_build_script(project.path)
        result = render_template(
            ctx.subproject_build_template,
            project_name=project.name,
            project_group=project.group_name,
            project_version=project.version,
            repositories=project.resolved_maven_repositories,
            kotlin_version=ctx.config.plugins["kotlin-jvm"].version,
            dokka_version=DOKKA_PLUGIN_VERSION,
            kover_version=KOVER_PLUGIN_VERSION,
            java_version=java_version,
            kotlin_jvm_target=kotlin_jvm_target,
            shadow_version=ctx.config.plugins["shadow"].version,
            features=template_features,
            use_root_plugin_management=nested_gradle_project,
            project_dependencies=project_dependencies,
            other_dependencies=other_dependencies,
            mode=mode_value,
            serialization_library=ctx.config.libraries["kotlinx-serialization-core"].maven_urn.__str__(),
            kotlin_free_compiler_args=kotlin_free_compiler_args,
            kotlin_compiler_plugin_options=kotlin_compiler_plugin_options,
            extra_gradle_plugins=extra_gradle_plugins,
            paper_dev_bundle_version=_paper_dev_bundle_version(ctx),
            dokka_source_link_remote_url=dokka_source_link_remote_url or "",
            has_dokka_source_link=dokka_source_link_remote_url is not None,
            company_legal_name=company_legal_name,
            publish_to_maven_central=publish_to_maven_central,
            is_gradle_plugin_project=project.gradle_plugin_id is not None,
            inline_extra_build_imports=inline_extra_build.imports,
            inline_extra_build_script=inline_extra_build.body,
            use_intellij_platform_gradle_plugin_v2=use_intellij_platform_gradle_plugin_v2,
            **version_property_context,
            **kotlin_compiler_plugin_context,
            **kotlin_compiler_gradle_plugin_context,
            **maven_central_context,
            **gradle_plugin_project_context,
        )
    result = clean_gradle_build_text(result)
    dev.io.write_text_file(project.path / "build.gradle.kts", result)

    if nested_gradle_project:
        _cleanup_nested_gradle_project_files(project)
        if not _nested_gradle_project_keeps_license(ctx, project):
            dev.io.delete_if_exists(project.path / "LICENSE.md")
            dev.io.delete_if_exists(project.path / "LICENSES")
    else:
        dev.io.write_text_file(
            project.path / "settings.gradle.kts",
            clean_gradle_build_text(
                render_template(
                    ctx.subproject_settings_template,
                    **settings_plugin_context(ctx, [project], root_path=project.path),
                    local_plugin_included_builds=local_plugin_included_builds(
                        ctx,
                        root_path=project.path,
                        projects=[project],
                    ),
                    project_name=project.effective_gradle_project_name,
                    features=project.resolved_features,
                )
            ),
        )
        dev.io.delete_if_exists(project.path / ".is-local-mode")
        dev.io.delete_if_exists(project.path / ".is-ij-mode")
        dev.io.delete_if_exists(project.path / ".is-dev-mode")

        dev.io.write_text_file(
            project.path / ".gitignore",
            clean_text(render_template(ctx.gitignore_template) + "\n" + render_template(ctx.gradle_gitignore_template)),
        )
        dev.io.write_text_file(
            project.path / "gradle.properties",
            clean_text(
                render_template(
                    ctx.gradle_properties_template,
                    repo_project_version=None,
                    repo_default_kotlin_version=None,
                    repo_supported_kotlin_versions=[],
                )
            ),
        )

    intellij_feature = project.resolved_features.get("intellij-plugin")
    if isinstance(intellij_feature, IntellijPlugin):
        _sync_intellij_plugin_xml(project, intellij_feature, _company_short_name(ctx))

    if not nested_gradle_project:
        write_wabbit_legal_files(ctx, project)

        dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew", project.path / "gradlew")
        dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew.bat", project.path / "gradlew.bat")
        _mark_executable(project.path / "gradlew")
        dev.io.copy(
            ctx.repo_template / "gradle-files" / "gradle" / "wrapper" / "gradle-wrapper.jar",
            project.path / "gradle" / "wrapper" / "gradle-wrapper.jar",
        )
        dev.io.copy(
            ctx.repo_template / "gradle-files" / "gradle" / "wrapper" / "gradle-wrapper.properties",
            project.path / "gradle" / "wrapper" / "gradle-wrapper.properties",
        )

        write_banner(ctx, project)
        _write_gradle_workflows(ctx, project, java_version=java_version)


__all__ = [
    "_make_dependency_strings",
    "java_version_for_features",
    "kotlin_jvm_target_for_version",
    "setup_gradle_project",
]
