from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import jinja2

import dev.io
from dev.config import (
    Config,
    Dependency,
    DependencyTarget,
    GradleProject,
    JarFileDependencyTarget,
    MavenDependencyTarget,
    Project,
    ProjectDependencyTarget,
)
from dev.messages import error
from dev.tasks.setup_common import RepoSetupMode, clean_text, render_template, write_banner, write_wabbit_legal_files


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
    def settings_template(self) -> jinja2.Template: ...

    @property
    def subproject_settings_template(self) -> jinja2.Template: ...

    @property
    def gitignore_template(self) -> jinja2.Template: ...

    @property
    def gradle_gitignore_template(self) -> jinja2.Template: ...

    @property
    def gradle_properties_template(self) -> jinja2.Template: ...


def _make_dependency_strings(ctx: GradleSetupContext, project: Project) -> tuple[list[str], list[str]]:
    other_dependencies: list[str] = []
    project_dependencies: list[str] = []
    for dep in project.resolved_dependencies:
        target = dep.target
        if isinstance(target, MavenDependencyTarget) or isinstance(target, JarFileDependencyTarget):
            other_dependencies.append(dep.as_string())
            continue

        if isinstance(target, ProjectDependencyTarget):
            name = target.project
            subproject = ctx.config.defined_projects.get(name)
            if subproject is None:
                error(f"Unknown subproject dependency: {name}")
                continue

            has_github_repo = subproject.github_repo is not None
            if isinstance(subproject, GradleProject):
                artifact_name = subproject.artifact_name
                project_version = subproject.version
            else:
                artifact_name = subproject.name
                project_version = getattr(subproject, "version", None)
            artifact_dep = Dependency(
                scope=dep.scope,
                target=DependencyTarget.Maven(artifact=artifact_name, maven_repo=None),
            )

            mode_value = ctx.mode.value
            if has_github_repo and mode_value != "local":
                project_dependencies.append(artifact_dep.as_string())
            else:
                project_dependencies.append(f"{dep.as_string()} // {project_version}")
            continue

        error(f"Unsupported dependency target type: {type(target).__name__}")

    return project_dependencies, other_dependencies


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


def setup_gradle_project(ctx: GradleSetupContext, project: GradleProject, interactive: bool = True) -> None:
    del interactive
    project_dependencies, other_dependencies = _make_dependency_strings(ctx, project)
    mode_value = ctx.mode.value
    java_version = java_version_for_features(ctx.config.java_version, project.resolved_features)
    kotlin_jvm_target = kotlin_jvm_target_for_version(java_version)

    result = render_template(
        ctx.subproject_build_template,
        project_name=project.name,
        project_group=project.group_name,
        project_version=project.version,
        repositories=project.resolved_maven_repositories,
        kotlin_version=ctx.config.plugins["kotlin-jvm"].version,
        java_version=java_version,
        kotlin_jvm_target=kotlin_jvm_target,
        shadow_version=ctx.config.plugins["shadow"].version,
        features=project.resolved_features,
        project_dependencies=project_dependencies,
        other_dependencies=other_dependencies,
        mode=mode_value,
        serialization_library=ctx.config.libraries["kotlinx-serialization-core"].maven_urn.__str__(),
    )
    result = clean_gradle_build_text(result)
    dev.io.write_text_file(project.path / "build.gradle.kts", result)

    if mode_value == "local":
        dev.io.delete_if_exists(project.path / "settings.gradle.kts")
        dev.io.touch(project.path / ".is-local-mode")
        dev.io.delete_if_exists(project.path / ".is-ij-mode")
        dev.io.delete_if_exists(project.path / ".is-dev-mode")
    elif mode_value == "dev":
        dev.io.write_text_file(
            project.path / "settings.gradle.kts",
            clean_gradle_build_text(render_template(ctx.settings_template, project_name=project.name)),
        )
        dev.io.delete_if_exists(project.path / ".is-local-mode")
        dev.io.delete_if_exists(project.path / ".is-ij-mode")
        dev.io.touch(project.path / ".is-dev-mode")
    else:
        dev.io.write_text_file(
            project.path / "settings.gradle.kts",
            clean_gradle_build_text(render_template(ctx.subproject_settings_template, project_name=project.name)),
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

    write_wabbit_legal_files(ctx, project)

    dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew", project.path / "gradlew")
    dev.io.copy(ctx.repo_template / "gradle-files" / "gradlew.bat", project.path / "gradlew.bat")
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
