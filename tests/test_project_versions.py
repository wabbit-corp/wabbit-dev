from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from mu.parser import parse


def _clean_git_state_result(args: list[str], merged_tags: list[str]) -> subprocess.CompletedProcess[str] | None:
    match args:
        case ["status", "--porcelain=1", "--untracked-files=all"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        case ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args, 0, "master\n", "")
        case ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return subprocess.CompletedProcess(args, 0, "origin/master\n", "")
        case ["fetch", "--quiet", "--no-tags", "origin", "master"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        case ["rev-parse", "FETCH_HEAD"]:
            return subprocess.CompletedProcess(args, 0, "abc123\n", "")
        case ["rev-list", "--count", "FETCH_HEAD..HEAD"]:
            return subprocess.CompletedProcess(args, 0, "0\n", "")
        case ["rev-list", "--count", "HEAD..FETCH_HEAD"]:
            return subprocess.CompletedProcess(args, 0, "0\n", "")
        case ["tag", "--merged", "HEAD", "--list"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(merged_tags) + "\n", "")
        case ["rev-list", "--count", tag_range] if tag_range.endswith("..HEAD"):
            return subprocess.CompletedProcess(args, 0, "0\n", "")
        case _:
            return None


def _make_python_project(path: Path):
    from dev.config import OwnershipType, PythonProject, Version

    return PythonProject(
        path=path,
        name="alpha",
        version=Version.parse("0.2.0"),
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        github_repo="wabbit-corp/alpha",
        requires_python=">=3.12",
        dependencies=[],
        dev_dependencies=[],
        scripts=[],
        application=None,
        homepage=None,
        repository=None,
        keywords=[],
        classifiers=[],
        quarantine=False,
        publish=True,
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        project_id="alpha",
        publish_target="pypi",
    )


def _make_gradle_project(path: Path):
    from dev.config import GradleProject, OwnershipType, Version

    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name="alpha",
        version=Version.parse("0.2.0"),
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/alpha",
        ownership=OwnershipType.WABBIT,
        raw_dependencies=[],
        raw_features=[],
        resolved_dependencies=[],
        resolved_maven_repositories=[],
        resolved_features={},
        project_id="alpha",
        publish_target="maven-central",
    )


def _make_dotnet_project(path: Path):
    from dev.config import DotnetProject, OwnershipType, Version

    return DotnetProject(
        path=path,
        name="alpha",
        version=Version.parse("0.2.0"),
        description="Alpha project",
        authors=["Dev"],
        license="AGPL",
        quarantine=False,
        publish=True,
        github_repo="wabbit-corp/alpha",
        ownership=OwnershipType.WABBIT,
        resolved_dependencies=[],
        language="fsharp",
        project_kind="library",
        sdk="Microsoft.NET.Sdk",
        target_framework="net10.0",
        project_id="alpha",
        publish_target="nuget",
        packable=True,
    )


def test_project_versions_json_merges_current_tags_and_pypi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.project_versions as project_versions_task
    from dev.config import Config
    from dev.pypi import PyPiProjectMetadata

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_python_project(project_path)
    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    config.github_ssh_key = "~/.ssh/id_example"

    def fake_run_git(repo_root: Path, args: list[str], loaded_config: Config) -> subprocess.CompletedProcess[str]:
        assert repo_root == project_path
        assert loaded_config.github_ssh_key == "~/.ssh/id_example"
        match args:
            case ["tag", "--list"]:
                return subprocess.CompletedProcess(args, 0, "0.1.0\nv0.2.0\nnot-a-release\n", "")
            case ["remote"]:
                return subprocess.CompletedProcess(args, 0, "origin\n", "")
            case ["ls-remote", "--tags", "origin"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "abc\trefs/tags/v0.1.0\n"
                    "def\trefs/tags/v0.2.0\n"
                    "ghi\trefs/tags/not-a-release\n",
                    "",
                )
            case _:
                git_state_result = _clean_git_state_result(args, ["0.1.0", "v0.2.0"])
                if git_state_result is not None:
                    return git_state_result
                raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(project_versions_task, "_run_git", fake_run_git)
    monkeypatch.setattr(
        project_versions_task,
        "_fetch_pypi_project_metadata",
        lambda project_name: PyPiProjectMetadata(latest_version="0.3.0", releases=["0.1.0", "0.3.0"]),
    )

    result = project_versions_task.show_project_versions(["alpha"], config=config, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["projectId"] == "alpha"
    assert payload["currentVersion"] == "0.2.0"
    assert payload["publishTarget"] == "pypi"
    assert payload["registry"]["name"] == "pypi"
    assert payload["registry"]["latest"] == "0.3.0"

    rows = {row["version"]: row for row in payload["versions"]}
    assert rows["0.1.0"]["localTags"] == ["0.1.0"]
    assert rows["0.1.0"]["remoteTags"] == ["v0.1.0"]
    assert rows["0.1.0"]["registries"] == ["pypi"]
    assert rows["0.2.0"]["current"] is True
    assert rows["0.2.0"]["localTags"] == ["v0.2.0"]
    assert rows["0.2.0"]["remoteTags"] == ["v0.2.0"]
    assert rows["0.3.0"]["registries"] == ["pypi"]
    assert payload["gitState"]["workingTree"]["clean"] is True
    assert payload["gitState"]["unpushedCommits"] == 0
    assert payload["gitState"]["latestTag"]["tag"] == "v0.2.0"
    assert payload["gitState"]["latestTag"]["commitsAfter"] == 0


def test_project_versions_json_adds_jitpack_for_gradle_libraries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.project_versions as project_versions_task
    from dev.config import Config
    from dev.maven import MavenMetadata

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_gradle_project(project_path)
    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    def fake_run_git(repo_root: Path, args: list[str], loaded_config: Config) -> subprocess.CompletedProcess[str]:
        del loaded_config
        assert repo_root == project_path
        match args:
            case ["tag", "--list"]:
                return subprocess.CompletedProcess(args, 0, "0.1.0\n0.2.0\n", "")
            case ["remote"]:
                return subprocess.CompletedProcess(args, 0, "origin\n", "")
            case ["ls-remote", "--tags", "origin"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "abc\trefs/tags/0.1.0\n"
                    "def\trefs/tags/0.2.0\n",
                    "",
                )
            case _:
                git_state_result = _clean_git_state_result(args, ["0.1.0", "0.2.0"])
                if git_state_result is not None:
                    return git_state_result
                raise AssertionError(f"unexpected git args: {args}")

    def fake_fetch_jitpack_versions(
        loaded_config: Config,
        group_id: str,
        artifact_id: str,
    ) -> tuple[str, ...]:
        assert loaded_config is config
        assert group_id == "com.github.wabbit-corp"
        assert artifact_id == "alpha"
        return ("0.1.0", "0.2.0")

    monkeypatch.setattr(project_versions_task, "_run_git", fake_run_git)
    monkeypatch.setattr(
        project_versions_task,
        "_fetch_maven_central_metadata",
        lambda group_id, artifact_id: MavenMetadata(
            latest="0.1.0",
            release="0.1.0",
            versions=["0.1.0"],
            last_updated="",
        ),
    )
    monkeypatch.setattr(project_versions_task, "_fetch_jitpack_versions", fake_fetch_jitpack_versions)

    result = project_versions_task.show_project_versions(["alpha"], config=config, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry"]["name"] == "maven-central"
    assert [registry["name"] for registry in payload["registries"]] == ["maven-central", "jitpack"]
    assert payload["registries"][1]["package"] == "com.github.wabbit-corp:alpha"
    assert payload["registries"][1]["latest"] == "0.2.0"

    rows = {row["version"]: row for row in payload["versions"]}
    assert rows["0.1.0"]["registries"] == ["maven-central", "jitpack"]
    assert rows["0.2.0"]["current"] is True
    assert rows["0.2.0"]["registries"] == ["jitpack"]


def test_project_versions_json_reports_unpublished_git_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.project_versions as project_versions_task
    from dev.config import Config
    from dev.pypi import PyPiProjectMetadata

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_python_project(project_path)
    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    def fake_run_git(repo_root: Path, args: list[str], loaded_config: Config) -> subprocess.CompletedProcess[str]:
        del loaded_config
        assert repo_root == project_path
        match args:
            case ["tag", "--list"]:
                return subprocess.CompletedProcess(args, 0, "0.1.0\n0.2.0\n", "")
            case ["remote"]:
                return subprocess.CompletedProcess(args, 0, "origin\n", "")
            case ["ls-remote", "--tags", "origin"]:
                return subprocess.CompletedProcess(args, 0, "abc\trefs/tags/0.2.0\n", "")
            case ["status", "--porcelain=1", "--untracked-files=all"]:
                return subprocess.CompletedProcess(args, 0, " M README.md\nA  src/new.py\n?? scratch.txt\n", "")
            case ["branch", "--show-current"]:
                return subprocess.CompletedProcess(args, 0, "master\n", "")
            case ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return subprocess.CompletedProcess(args, 0, "origin/master\n", "")
            case ["fetch", "--quiet", "--no-tags", "origin", "master"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            case ["rev-parse", "FETCH_HEAD"]:
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            case ["rev-list", "--count", "FETCH_HEAD..HEAD"]:
                return subprocess.CompletedProcess(args, 0, "3\n", "")
            case ["rev-list", "--count", "HEAD..FETCH_HEAD"]:
                return subprocess.CompletedProcess(args, 0, "1\n", "")
            case ["tag", "--merged", "HEAD", "--list"]:
                return subprocess.CompletedProcess(args, 0, "0.1.0\n0.2.0\n", "")
            case ["rev-list", "--count", "0.2.0..HEAD"]:
                return subprocess.CompletedProcess(args, 0, "5\n", "")
            case _:
                raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(project_versions_task, "_run_git", fake_run_git)
    monkeypatch.setattr(
        project_versions_task,
        "_fetch_pypi_project_metadata",
        lambda project_name: PyPiProjectMetadata(latest_version="0.2.0", releases=["0.2.0"]),
    )

    result = project_versions_task.show_project_versions(["alpha"], config=config, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    git_state = payload["gitState"]
    assert git_state["branch"] == "master"
    assert git_state["remote"] == "origin"
    assert git_state["remoteBranch"] == "master"
    assert git_state["unpushedCommits"] == 3
    assert git_state["remoteOnlyCommits"] == 1
    assert git_state["latestTag"]["tag"] == "0.2.0"
    assert git_state["latestTag"]["commitsAfter"] == 5
    assert git_state["workingTree"]["clean"] is False
    assert git_state["workingTree"]["fileCount"] == 3
    assert git_state["workingTree"]["stagedCount"] == 1
    assert git_state["workingTree"]["unstagedCount"] == 1
    assert git_state["workingTree"]["untrackedCount"] == 1


def test_project_versions_requires_single_project_target(tmp_path: Path) -> None:
    import dev.tasks.project_versions as project_versions_task
    from dev.config import Config

    project_a_path = tmp_path / "alpha"
    project_b_path = tmp_path / "beta"
    project_a_path.mkdir()
    project_b_path.mkdir()
    project_a = _make_python_project(project_a_path)
    project_b = _make_python_project(project_b_path)
    project_b.name = "beta"
    project_b.project_id = "beta"

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project_a
    config.defined_projects["beta"] = project_b

    with pytest.raises(ValueError, match="expects exactly one project"):
        project_versions_task.show_project_versions(["alpha", "beta"], config=config, json_output=True)


def test_project_versions_json_adds_nuget_for_dotnet_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.project_versions as project_versions_task
    from dev.config import Config
    from dev.nuget import NuGetPackageMetadata

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_dotnet_project(project_path)
    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    def fake_run_git(repo_root: Path, args: list[str], loaded_config: Config) -> subprocess.CompletedProcess[str]:
        del loaded_config
        assert repo_root == project_path
        match args:
            case ["tag", "--list"]:
                return subprocess.CompletedProcess(args, 0, "0.1.0\nv0.2.0\n", "")
            case ["remote"]:
                return subprocess.CompletedProcess(args, 0, "origin\n", "")
            case ["ls-remote", "--tags", "origin"]:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "abc\trefs/tags/v0.1.0\n"
                    "def\trefs/tags/v0.2.0\n",
                    "",
                )
            case _:
                git_state_result = _clean_git_state_result(args, ["0.1.0", "v0.2.0"])
                if git_state_result is not None:
                    return git_state_result
                raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(project_versions_task, "_run_git", fake_run_git)
    monkeypatch.setattr(
        project_versions_task,
        "fetch_package_metadata",
        lambda package_id: NuGetPackageMetadata(latest_version="0.3.0", versions=("0.1.0", "0.3.0")),
    )

    result = project_versions_task.show_project_versions(["alpha"], config=config, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["publishTarget"] == "nuget"
    assert payload["registry"]["name"] == "nuget"
    assert payload["registry"]["latest"] == "0.3.0"

    rows = {row["version"]: row for row in payload["versions"]}
    assert rows["0.1.0"]["registries"] == ["nuget"]
    assert rows["0.2.0"]["current"] is True
    assert rows["0.2.0"]["localTags"] == ["v0.2.0"]
    assert rows["0.3.0"]["registries"] == ["nuget"]
