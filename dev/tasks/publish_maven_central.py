from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dev.config import GradleProject
from dev.messages import error, info, success
from dev.tasks.publish_common import PublishError
from dev.tasks.setup import RepoSetupContext, setup_gradle_repo_root, setup_project


def _maven_central_env(
    *,
    maven_username: str | None,
    maven_password: str | None,
    gpg_private_key: str | None,
    gpg_passphrase: str | None,
    gpg_key_id: str | None,
) -> dict[str, str]:
    env = os.environ.copy()

    def set_if_present(env_name: str, value: str | None) -> None:
        if value is not None and value.strip():
            env[env_name] = value

    set_if_present("MAVEN_USERNAME", env.get("MAVEN_USERNAME") or maven_username)
    set_if_present("MAVEN_PASSWORD", env.get("MAVEN_PASSWORD") or maven_password)
    set_if_present("MAVEN_GPG_PRIVATE_KEY", env.get("MAVEN_GPG_PRIVATE_KEY") or gpg_private_key)
    set_if_present("MAVEN_GPG_PASSPHRASE", env.get("MAVEN_GPG_PASSPHRASE") or gpg_passphrase)
    set_if_present("MAVEN_GPG_KEY_ID", env.get("MAVEN_GPG_KEY_ID") or gpg_key_id)
    set_if_present(
        "ORG_GRADLE_PROJECT_mavenCentralUsername",
        env.get("ORG_GRADLE_PROJECT_mavenCentralUsername") or maven_username,
    )
    set_if_present(
        "ORG_GRADLE_PROJECT_mavenCentralPassword",
        env.get("ORG_GRADLE_PROJECT_mavenCentralPassword") or maven_password,
    )
    set_if_present(
        "ORG_GRADLE_PROJECT_signingInMemoryKey",
        env.get("ORG_GRADLE_PROJECT_signingInMemoryKey") or gpg_private_key,
    )
    set_if_present(
        "ORG_GRADLE_PROJECT_signingInMemoryKeyPassword",
        env.get("ORG_GRADLE_PROJECT_signingInMemoryKeyPassword") or gpg_passphrase,
    )
    set_if_present(
        "ORG_GRADLE_PROJECT_signingInMemoryKeyId",
        env.get("ORG_GRADLE_PROJECT_signingInMemoryKeyId") or gpg_key_id,
    )
    return env


def _gradle_command(gradle_root: Path) -> list[str]:
    wrapper_path = gradle_root / "gradlew"
    if wrapper_path.is_file():
        return [str(wrapper_path)]
    return ["gradle"]


def _gradle_task_name(project: GradleProject, task_name: str) -> str:
    if project.effective_gradle_root != project.path:
        return f":{project.effective_gradle_project_name}:{task_name}"
    return task_name


async def publish_gradle_project_to_maven_central(
    project: GradleProject,
    repo_setup_context: RepoSetupContext,
    *,
    maven_username: str | None,
    maven_password: str | None,
    gpg_private_key: str | None,
    gpg_passphrase: str | None,
    gpg_key_id: str | None,
) -> bool:
    if project.quarantine:
        raise PublishError(f"Project {project.name} is in quarantine. Cannot publish.")
    if not project.publish:
        info(f"Skipping Maven Central publish for {project.name} (publish=false).")
        return True
    if project.publish_target != "maven-central":
        info(f"Skipping Maven Central publish for {project.name} (publishTarget={project.publish_target!r}).")
        return True
    if project.github_repo is None:
        raise PublishError(f"Project {project.name} has no GitHub repository set.")

    if maven_username is None or maven_password is None:
        raise PublishError(
            f"Missing Maven Central credentials for {project.name}. "
            "Set maven-username/maven-password in root.private.clj or export MAVEN_USERNAME/MAVEN_PASSWORD."
        )
    if gpg_private_key is None or gpg_passphrase is None:
        raise PublishError(
            f"Missing GPG signing material for {project.name}. "
            "Set maven-gpg-private-key/maven-gpg-passphrase in root.private.clj or export the matching env vars."
        )

    if project.is_repo_managed:
        setup_gradle_repo_root(repo_setup_context, project)
    setup_project(repo_setup_context, project, interactive=False)

    env = _maven_central_env(
        maven_username=maven_username,
        maven_password=maven_password,
        gpg_private_key=gpg_private_key,
        gpg_passphrase=gpg_passphrase,
        gpg_key_id=gpg_key_id,
    )

    version_object = project.version
    version_string = str(version_object) if version_object is not None else ""
    if not version_string:
        raise PublishError(f"Project {project.name} has no version set.")

    gradle_root = project.effective_gradle_root
    gradle_tasks = [_gradle_task_name(project, "build")]
    if version_object is not None and version_object.is_dev:
        gradle_tasks.extend(
            [
                _gradle_task_name(project, "assertSnapshotVersion"),
                _gradle_task_name(project, "publishToMavenCentral"),
            ]
        )
    else:
        gradle_tasks.extend(
            [
                _gradle_task_name(project, "assertReleaseVersion"),
                _gradle_task_name(project, "publishAndReleaseToMavenCentral"),
            ]
        )

    command = [*_gradle_command(gradle_root), "--no-daemon", *gradle_tasks]
    info(f"Publishing {project.name} to Maven Central...")
    try:
        subprocess.run(command, cwd=gradle_root, env=env, check=True)
    except subprocess.CalledProcessError as ex:
        error(f"Maven Central publish failed for {project.name}: {ex}")
        return False

    success(f"Published Gradle project {project.name} to Maven Central.")
    return True


__all__ = ["publish_gradle_project_to_maven_central"]
