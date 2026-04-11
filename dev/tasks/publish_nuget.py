from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from dev.config import DotnetProject
from dev.dotnet import dotnet_project_file
from dev.messages import info, success
from dev.tasks.publish_common import PublishError


def _publish_dotnet_project_to_nuget_sync(
    project: DotnetProject,
    *,
    nuget_api_key: str | None,
) -> bool:
    if not nuget_api_key:
        raise PublishError("NuGet API key is not configured.")

    project_file = dotnet_project_file(project)
    with tempfile.TemporaryDirectory(prefix="publish-nuget-") as temp_dir_name:
        output_dir = Path(temp_dir_name)
        pack_command = [
            "dotnet",
            "pack",
            str(project_file),
            "-c",
            "Release",
            "--nologo",
            "--output",
            str(output_dir),
        ]
        info(f"Packing NuGet package for {project.name}: {' '.join(pack_command)}")
        try:
            subprocess.run(pack_command, cwd=project.effective_repo_root, check=True)
        except subprocess.CalledProcessError as ex:
            raise PublishError(f"dotnet pack failed with exit code {ex.returncode}") from ex
        except FileNotFoundError as ex:
            raise PublishError("dotnet CLI not found.") from ex

        package_paths = sorted(
            [
                *output_dir.glob("*.nupkg"),
                *output_dir.glob("*.snupkg"),
            ]
        )
        package_paths = [path for path in package_paths if not path.name.endswith(".symbols.nupkg")]
        if not package_paths:
            raise PublishError("dotnet pack did not produce any publishable NuGet packages.")

        for package_path in package_paths:
            push_command = [
                "dotnet",
                "nuget",
                "push",
                str(package_path),
                "--api-key",
                nuget_api_key,
                "--source",
                "https://api.nuget.org/v3/index.json",
                "--skip-duplicate",
            ]
            info(f"Pushing {package_path.name} for {project.name}: {' '.join(push_command[:-1])} --skip-duplicate")
            try:
                subprocess.run(push_command, cwd=project.effective_repo_root, check=True)
            except subprocess.CalledProcessError as ex:
                raise PublishError(f"dotnet nuget push failed with exit code {ex.returncode}") from ex
            except FileNotFoundError as ex:
                raise PublishError("dotnet CLI not found.") from ex

    success(f"Published {project.name} to NuGet.")
    return True


async def publish_dotnet_project_to_nuget(
    project: DotnetProject,
    *,
    nuget_api_key: str | None,
) -> bool:
    return await asyncio.to_thread(
        _publish_dotnet_project_to_nuget_sync,
        project,
        nuget_api_key=nuget_api_key,
    )


__all__ = ["publish_dotnet_project_to_nuget"]
