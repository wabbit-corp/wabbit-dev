from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dev.config import GradleProject, IntellijPlugin
from dev.messages import error, info, success
from dev.tasks.publish_common import PublishError
from dev.tasks.setup import RepoSetupContext, setup_project


def _intellij_feature(project: GradleProject) -> IntellijPlugin:
    feature = project.resolved_features.get("intellij-plugin")
    if not isinstance(feature, IntellijPlugin):
        raise PublishError(f"Project {project.name} is missing required intellij-plugin feature metadata.")
    return feature


def _run_gradle_tasks(project_path: Path, tasks: list[str], extra_env: dict[str, str]) -> None:
    command = ["bash", "gradlew", *tasks]
    env = os.environ.copy()
    env.update(extra_env)
    subprocess.run(command, cwd=project_path, env=env, check=True)


async def publish_gradle_project_to_intellij_marketplace(
    project: GradleProject,
    repo_setup_context: RepoSetupContext,
    marketplace_token: str | None,
) -> bool:
    if project.quarantine:
        raise PublishError(f"Project {project.name} is in quarantine. Cannot publish.")

    if not project.publish:
        info(f"Skipping IntelliJ Marketplace publish for {project.name} (publish=false).")
        return True

    feature = _intellij_feature(project)
    token_env_name = feature.marketplaceTokenEnv or "JETBRAINS_MARKETPLACE_TOKEN"

    token_value = marketplace_token
    if not token_value:
        token_value = os.environ.get(token_env_name)
    if not token_value:
        raise PublishError(
            f"Missing IntelliJ Marketplace token for {project.name}. "
            f"Set it in root.private.clj (jetbrains-marketplace-token) or export {token_env_name}."
        )

    setup_project(repo_setup_context, project, interactive=False)
    gradle_tasks = ["verifyPlugin", "buildPlugin", "publishPlugin"]
    gradle_cwd = project.effective_gradle_root
    if project.is_repo_managed:
        gradle_tasks = [f":{project.effective_gradle_project_name}:{task}" for task in gradle_tasks]

    info(f"Publishing IntelliJ plugin {project.name} to JetBrains Marketplace...")
    try:
        _run_gradle_tasks(gradle_cwd, gradle_tasks, {token_env_name: token_value})
    except subprocess.CalledProcessError as ex:
        error(f"IntelliJ Marketplace publish failed for {project.name}: {ex}")
        return False

    success(f"Published IntelliJ plugin {project.name} to JetBrains Marketplace.")
    return True


__all__ = [
    "publish_gradle_project_to_intellij_marketplace",
]
