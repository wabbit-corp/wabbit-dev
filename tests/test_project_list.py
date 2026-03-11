from collections import OrderedDict
from pathlib import Path

import pytest
from mu.parser import parse

from dev.config import Config, GradleProject, Kotlin, OwnershipType, PythonProject, Version
from dev.tasks.project_list import render_project_list_lines


def _empty_config() -> Config:
    return Config(raw=parse("()"))


def _python_project(path: Path, *, project_id: str, repo_id: str | None = None, repo_root: Path | None = None) -> PythonProject:
    return PythonProject(
        path=path,
        name=path.name,
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=">=3.12,<4.0",
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=False,
        ownership=OwnershipType.WABBIT,
        project_id=project_id,
        repo_id=repo_id,
        repo_root=repo_root,
    )


def _gradle_project(
    path: Path,
    *,
    project_id: str,
    build_model: str,
    repo_id: str | None = None,
    repo_root: Path | None = None,
) -> GradleProject:
    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name=path.name,
        version=Version.parse("0.0.1"),
        description=None,
        authors=[],
        license=None,
        quarantine=False,
        publish=False,
        github_repo=None,
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={"kotlin": Kotlin()},
        project_id=project_id,
        repo_id=repo_id,
        repo_root=repo_root,
        build_model=build_model,
        platforms=["jvm"] if build_model == "jvm" else ["jvm", "iosArm64"],
    )


def test_render_project_list_lines_groups_repo_projects() -> None:
    config = _empty_config()
    repo_root = Path("./jeeves")
    config.defined_projects = OrderedDict(
        [
            (
                "app-wabbit-dev",
                _python_project(Path("./app-wabbit-dev"), project_id="app-wabbit-dev"),
            ),
            (
                "kotlin-base58",
                _gradle_project(Path("./kotlin-base58"), project_id="kotlin-base58", build_model="jvm"),
            ),
            (
                "jeeves/api",
                _gradle_project(
                    repo_root / "api",
                    project_id="jeeves/api",
                    build_model="kmp",
                    repo_id="jeeves",
                    repo_root=repo_root,
                ),
            ),
            (
                "jeeves/client",
                _gradle_project(
                    repo_root / "client",
                    project_id="jeeves/client",
                    build_model="kmp",
                    repo_id="jeeves",
                    repo_root=repo_root,
                ),
            ),
            (
                "jeeves/audio-backend",
                _python_project(
                    repo_root / "audio-backend",
                    project_id="jeeves/audio-backend",
                    repo_id="jeeves",
                    repo_root=repo_root,
                ),
            ),
        ]
    )

    lines = render_project_list_lines(config, colorize=False)

    assert lines[0].startswith("app-wabbit-dev")
    assert lines[0].endswith("python")
    assert lines[1].startswith("kotlin-base58")
    assert lines[1].endswith("kotlin/jvm")
    assert lines[2] == "jeeves/"
    assert lines[3].startswith("  api")
    assert lines[3].endswith("kotlin/kmp")
    assert lines[4].startswith("  client")
    assert lines[4].endswith("kotlin/kmp")
    assert lines[5].startswith("  audio-backend")
    assert lines[5].endswith("python")


@pytest.mark.asyncio
async def test_cli_project_list_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import project_list

    called: list[str] = []

    def fake_list_projects() -> None:
        called.append("called")

    monkeypatch.setattr(project_list, "list_projects", fake_list_projects)
    monkeypatch.setattr("sys.argv", ["dev.py", "project", "list"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["called"]
