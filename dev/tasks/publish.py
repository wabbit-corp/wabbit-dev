#!/usr/bin/env python3

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Literal

from dev.build_order import toposort_projects
from dev.config import GradleProject, Project, PythonProject, load_config
from dev.jitpack import JitPackAPI
from dev.messages import error, success, warning
from dev.repo_resolution import resolve_project_ids
from dev.tasks.publish_common import PublishError
from dev.tasks.publish_intellij import publish_gradle_project_to_intellij_marketplace
from dev.tasks.publish_jetpack import publish_gradle_project_to_jetpack
from dev.tasks.publish_maven_central import publish_gradle_project_to_maven_central
from dev.tasks.publish_pypi import publish_python_project_to_pypi
from dev.tasks.setup import RepoSetupMode, create_repo_setup_context

PublishTarget = Literal["maven-central", "jitpack", "intellij-marketplace", "pypi", "skip"]


def determine_publish_target(project: Project) -> PublishTarget:
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


async def publish_main(projects: str | list[str] | None = None) -> None:
    config = load_config()
    repo_setup_context = create_repo_setup_context(config, RepoSetupMode.PROD)

    all_projects = {name: p for name, p in config.defined_projects.items()}
    requested_projects = [projects] if isinstance(projects, str) else projects
    selected_project_names: list[str] | None = None
    if requested_projects:
        try:
            selected_project_names = resolve_project_ids(config, requested_projects)
        except ValueError as ex:
            error(str(ex))
            return

    order = toposort_projects(all_projects, target_project=selected_project_names)
    if not order:
        error("No projects to publish or cycle in dependencies.")
        return

    success("Topological order of projects to publish:\n  " + ", ".join(order))
    has_jitpack_target = any(determine_publish_target(all_projects[name]) == "jitpack" for name in order)

    async with AsyncExitStack() as stack:
        jitpack_api: JitPackAPI | None = None
        if has_jitpack_target:
            jitpack_api = await stack.enter_async_context(JitPackAPI(session_cookie=config.jitpack_cookie))

        for name in order:
            project = all_projects[name]
            target = determine_publish_target(project)

            if target == "skip":
                warning(f"Skipping {project.name}: unsupported project type for publish.")
                continue

            try:
                if target == "maven-central":
                    if not isinstance(project, GradleProject):
                        raise PublishError(f"Expected GradleProject for {project.name}, got {type(project).__name__}.")
                    ok = await publish_gradle_project_to_maven_central(
                        project,
                        repo_setup_context,
                        maven_username=config.maven_username,
                        maven_password=config.maven_password,
                        gpg_private_key=config.maven_gpg_private_key,
                        gpg_passphrase=config.maven_gpg_passphrase,
                        gpg_key_id=config.maven_gpg_key_id,
                    )
                elif target == "jitpack":
                    if not isinstance(project, GradleProject):
                        raise PublishError(f"Expected GradleProject for {project.name}, got {type(project).__name__}.")
                    if jitpack_api is None:
                        raise PublishError("JetPack API client is not available.")
                    ok = await publish_gradle_project_to_jetpack(
                        project,
                        jitpack_api,
                        repo_setup_context,
                        openai_key=config.openai_key,
                    )
                elif target == "intellij-marketplace":
                    if not isinstance(project, GradleProject):
                        raise PublishError(f"Expected GradleProject for {project.name}, got {type(project).__name__}.")
                    ok = await publish_gradle_project_to_intellij_marketplace(
                        project,
                        repo_setup_context,
                        marketplace_token=config.jetbrains_marketplace_token,
                    )
                elif target == "pypi":
                    if not isinstance(project, PythonProject):
                        raise PublishError(f"Expected PythonProject for {project.name}, got {type(project).__name__}.")
                    ok = await publish_python_project_to_pypi(
                        project,
                        repo_setup_context,
                        pypi_token=config.pypi_token,
                    )
            except PublishError as ex:
                error(f"{project.name} publish failed: {ex}")
                break

            if not ok:
                warning(f"Stopped after {project.name} failed.")
                break
        else:
            success("All selected projects published successfully.")


__all__ = [
    "determine_publish_target",
    "publish_main",
]
