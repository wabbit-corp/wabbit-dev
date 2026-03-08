from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dev.config import PythonProject
from dev.messages import error, info, success
from dev.tasks.publish_common import PublishError
from dev.tasks.setup import RepoSetupContext, setup_project


def _run_python_module(module: str, args: list[str], cwd: Path, extra_env: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, env=env, check=True)


async def publish_python_project_to_pypi(
    project: PythonProject,
    repo_setup_context: RepoSetupContext,
    pypi_token: str | None,
) -> bool:
    if project.quarantine:
        raise PublishError(f"Project {project.name} is in quarantine. Cannot publish.")

    if not project.publish:
        info(f"Skipping PyPI publish for {project.name} (publish=false).")
        return True

    twine_username = os.environ.get("TWINE_USERNAME")
    twine_password = os.environ.get("TWINE_PASSWORD")
    token = pypi_token
    if token is None and twine_password is None:
        raise PublishError(
            f"Missing PyPI token for {project.name}. "
            "Set root.private.clj (pypi-token) or export TWINE_USERNAME/TWINE_PASSWORD."
        )

    setup_project(repo_setup_context, project, interactive=False)

    info(f"Building Python package for {project.name}...")
    try:
        _run_python_module("build", [], project.path, {})
    except subprocess.CalledProcessError as ex:
        error(f"PyPI build failed for {project.name}: {ex}")
        return False

    dist_dir = project.path / "dist"
    dist_files = sorted(dist_dir.glob("*"))
    if not dist_files:
        raise PublishError(f"No distribution artifacts found for {project.name} in {dist_dir}.")

    upload_env: dict[str, str] = {}
    if token is not None:
        upload_env["TWINE_USERNAME"] = "__token__"
        upload_env["TWINE_PASSWORD"] = token
    else:
        if twine_username is not None:
            upload_env["TWINE_USERNAME"] = twine_username
        assert twine_password is not None
        upload_env["TWINE_PASSWORD"] = twine_password

    info(f"Uploading Python package for {project.name} to PyPI...")
    try:
        _run_python_module(
            "twine",
            ["upload", "--non-interactive", "--skip-existing", *[str(path) for path in dist_files]],
            project.path,
            upload_env,
        )
    except subprocess.CalledProcessError as ex:
        error(f"PyPI upload failed for {project.name}: {ex}")
        return False

    success(f"Published Python package {project.name} to PyPI.")
    return True


__all__ = [
    "publish_python_project_to_pypi",
]
