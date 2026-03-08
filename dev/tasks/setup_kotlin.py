from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
from dev.config import (
    Config,
    DataProject,
    Dependency,
    DependencyTarget,
    GradleTargetSpec,
    GradleProject,
    IntellijPlugin,
    KmpAndroidLibrary,
    JarFileDependencyTarget,
    KmpJvmRuns,
    MavenDependencyTarget,
    PremakeProject,
    Project,
    ProjectDependencyTarget,
    PurescriptProject,
    PythonProject,
)
from dev.messages import error
from dev.tasks.setup_common import RepoSetupMode, clean_text, render_template, write_banner, write_wabbit_legal_files

ANDROID_GRADLE_PLUGIN_VERSION = "8.13.2"
DEFAULT_COMPOSE_PLUGIN_VERSION = "1.9.1"
DOKKA_PLUGIN_VERSION = "2.0.0"
KOVER_PLUGIN_VERSION = "0.9.3"
INTELLIJ_GRADLE_PLUGIN_VERSION = "1.17.2"
PAPERWEIGHT_USERDEV_PLUGIN_VERSION = "1.7.2"
BUKKIT_PLUGIN_YML_VERSION = "0.6.0"
CONTEXT_PARAMETERS_COMPILER_FLAG = "-Xcontext-parameters"
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
    def coc(self) -> str: ...

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


def _render_dependency_for_mode(ctx: GradleSetupContext, project: Project, dependency: Dependency) -> str:
    target = dependency.target
    if isinstance(target, MavenDependencyTarget):
        if isinstance(project, GradleProject) and "kmp-compose" in project.resolved_features:
            for prefix, accessor in COMPOSE_ACCESSOR_PREFIXES:
                if target.artifact.startswith(prefix):
                    modifier = dependency.scope or "implementation"
                    return f"{modifier}({accessor})"
        return dependency.as_string()
    if isinstance(target, JarFileDependencyTarget):
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
        if has_github_repo and ctx.mode.value != "local":
            return artifact_dependency.as_string()
        return f"{dependency_string} // {project_version}"

    error(f"Unsupported dependency target type: {type(target).__name__}")
    return dependency.as_string()


def _make_dependency_strings(ctx: GradleSetupContext, project: Project) -> tuple[list[str], list[str]]:
    other_dependencies: list[str] = []
    project_dependencies: list[str] = []
    for dep in project.resolved_dependencies:
        target = dep.target
        if isinstance(target, MavenDependencyTarget) or isinstance(target, JarFileDependencyTarget):
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


def settings_plugin_versions(ctx: GradleSetupContext) -> dict[str, str]:
    def plugin_version(name: str, fallback: str) -> str:
        plugin = ctx.config.plugins.get(name)
        if plugin is None:
            return fallback
        return plugin.version

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
        "intellij_gradle_plugin_version": INTELLIJ_GRADLE_PLUGIN_VERSION,
        "paperweight_userdev_plugin_version": PAPERWEIGHT_USERDEV_PLUGIN_VERSION,
        "bukkit_plugin_yml_version": BUKKIT_PLUGIN_YML_VERSION,
    }
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
        else:
            targets.append(GradleTargetSpec(kind=platform))
    return targets


def _is_nested_gradle_project(project: GradleProject) -> bool:
    return project.effective_gradle_root != project.path


def _needs_google_repository(project: GradleProject) -> bool:
    return any(target.kind.startswith("android-") for target in _effective_targets(project))


def _has_apple_targets(project: GradleProject) -> bool:
    return any(target.kind in ("iosArm64", "iosSimulatorArm64", "macosArm64") for target in _effective_targets(project))


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
                }
            )
        return entries

    declared_source_sets = set(project.source_sets)
    macos_source_set_names = {
        f"{(target.name or 'macosArm64')}{suffix}"
        for target in _effective_targets(project)
        if target.kind == "macosArm64"
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
        if source_set_name in macos_source_set_names:
            if source_set_name.endswith("Main"):
                if "appleMain" in declared_source_sets:
                    return "appleMain"
                if "nativeMain" in declared_source_sets:
                    return "nativeMain"
                return "commonMain"
            if "appleTest" in declared_source_sets:
                return "appleTest"
            if "nativeTest" in declared_source_sets:
                return "nativeTest"
            return "commonTest"
        return None

    for source_set_name, source_set in project.source_sets.items():
        depends_on = [
            parent for parent in source_set.depends_on if parent != implicit_parent(source_set_name)
        ]
        entries.append(
            {
                "name": source_set_name,
                "accessor": "getting" if source_set_name in default_source_sets else "creating",
                "depends_on": depends_on,
                "dependencies": list(source_set_dependencies.get(source_set_name, [])),
            }
        )
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


def _cleanup_nested_gradle_project_files(project: GradleProject) -> None:
    dev.io.delete_if_exists(project.path / "settings.gradle.kts")
    dev.io.delete_if_exists(project.path / "gradlew")
    dev.io.delete_if_exists(project.path / "gradlew.bat")
    dev.io.delete_if_exists(project.path / "gradle.properties")
    dev.io.delete_if_exists(project.path / ".is-local-mode")
    dev.io.delete_if_exists(project.path / ".is-ij-mode")
    dev.io.delete_if_exists(project.path / ".is-dev-mode")
    dev.io.delete_if_exists(project.path / "gradle")


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


def _sync_intellij_plugin_xml(project: GradleProject, feature: IntellijPlugin) -> None:
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
        _normalize_xml_text(feature.vendorName) or _normalize_xml_text(vendor_element.text) or "Wabbit Corporation"
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

    if project.is_kmp:
        targets = _effective_targets(project)
        source_set_dependencies = _make_source_set_dependency_strings(ctx, project)
        source_set_entries = _source_set_entries(project, source_set_dependencies)
        kmp_jvm_runs_feature = project.resolved_features.get("kmp-jvm-runs")
        kmp_jvm_runs = None
        if isinstance(kmp_jvm_runs_feature, KmpJvmRuns):
            kmp_jvm_runs = kmp_jvm_runs_feature.entries

        android_application_target = _android_application_target(project)
        android_kmp_library_target = _android_kmp_library_target(project)

        result = render_template(
            ctx.subproject_build_kmp_template,
            project_name=project.name,
            project_group=project.group_name,
            project_version=project.version,
            repositories=project.resolved_maven_repositories,
            kotlin_mp_version=ctx.config.plugins["kotlin-mp"].version,
            kotlin_serialization_version=ctx.config.plugins["kotlin-serialization"].version,
            android_gradle_version=ANDROID_GRADLE_PLUGIN_VERSION,
            compose_plugin_version=compose_plugin_version,
            dokka_version=DOKKA_PLUGIN_VERSION,
            kover_version=KOVER_PLUGIN_VERSION,
            java_version=java_version,
            kotlin_jvm_target=kotlin_jvm_target,
            features=project.resolved_features,
            use_root_plugin_management=nested_gradle_project,
            platforms=project.platforms,
            targets=targets,
            has_apple_targets=_has_apple_targets(project),
            needs_google_repository=_needs_google_repository(project),
            android_application_target=android_application_target,
            android_kmp_library_target=android_kmp_library_target,
            source_set_dependencies=source_set_dependencies,
            source_set_entries=source_set_entries,
            mode=mode_value,
            kmp_jvm_runs=kmp_jvm_runs,
            native_framework_base_name=_native_framework_base_name(project),
            kotlin_free_compiler_args=kotlin_free_compiler_args,
        )
    else:
        project_dependencies, other_dependencies = _make_dependency_strings(ctx, project)
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
            features=project.resolved_features,
            use_root_plugin_management=nested_gradle_project,
            project_dependencies=project_dependencies,
            other_dependencies=other_dependencies,
            mode=mode_value,
            serialization_library=ctx.config.libraries["kotlinx-serialization-core"].maven_urn.__str__(),
            kotlin_free_compiler_args=kotlin_free_compiler_args,
        )
    result = clean_gradle_build_text(result)
    dev.io.write_text_file(project.path / "build.gradle.kts", result)

    if nested_gradle_project:
        _cleanup_nested_gradle_project_files(project)
    else:
        if mode_value == "local":
            dev.io.delete_if_exists(project.path / "settings.gradle.kts")
            dev.io.touch(project.path / ".is-local-mode")
            dev.io.delete_if_exists(project.path / ".is-ij-mode")
            dev.io.delete_if_exists(project.path / ".is-dev-mode")
        elif mode_value == "dev":
            dev.io.write_text_file(
                project.path / "settings.gradle.kts",
                clean_gradle_build_text(
                    render_template(
                        ctx.settings_template,
                        root_project_name=project.effective_gradle_project_name,
                    )
                ),
            )
            dev.io.delete_if_exists(project.path / ".is-local-mode")
            dev.io.delete_if_exists(project.path / ".is-ij-mode")
            dev.io.touch(project.path / ".is-dev-mode")
        else:
            dev.io.write_text_file(
                project.path / "settings.gradle.kts",
                clean_gradle_build_text(
                    render_template(
                        ctx.subproject_settings_template,
                        **settings_plugin_versions(ctx),
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
            clean_text(render_template(ctx.gradle_properties_template)),
        )

    intellij_feature = project.resolved_features.get("intellij-plugin")
    if isinstance(intellij_feature, IntellijPlugin):
        _sync_intellij_plugin_xml(project, intellij_feature)

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


__all__ = [
    "_make_dependency_strings",
    "java_version_for_features",
    "kotlin_jvm_target_for_version",
    "setup_gradle_project",
]
