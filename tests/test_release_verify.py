from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from mu.parser import parse


def _make_python_project(path: Path) -> object:
    from dev.config import OwnershipType, PythonProject

    return PythonProject(
        path=path,
        name="alpha",
        version=None,
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


def _make_gradle_project(path: Path) -> object:
    from dev.config import GradleProject, OwnershipType, Version

    return GradleProject(
        path=path,
        group_name="one.wabbit",
        name="alpha",
        version=Version.parse("0.1.0"),
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


def test_release_verify_python_json_output_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text("# alpha\n", encoding="utf-8")
    (project_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    (project_path / "LICENSE.md").write_text("license\n", encoding="utf-8")
    (project_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'alpha'\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(release_task.importlib, "import_module", lambda _name: object())

    def fake_run_python_module(module: str, args: list[str], *, cwd: Path, redirect_output: bool) -> None:
        del redirect_output
        if module != "build":
            return
        out_dir = Path(args[args.index("--outdir") + 1])
        wheel_path = out_dir / "alpha-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as archive:
            archive.writestr("alpha/__init__.py", "__version__ = '0.1.0'\n")
            archive.writestr(
                "alpha-0.1.0.dist-info/METADATA",
                "\n".join(
                    [
                        "Metadata-Version: 2.3",
                        "Name: alpha",
                        "Version: 0.1.0",
                        "License: AGPL-3.0-or-later",
                        "Home-page: https://github.com/wabbit-corp/alpha",
                        "Description-Content-Type: text/markdown",
                        "",
                        "# alpha",
                    ]
                ),
            )
        sdist_path = out_dir / "alpha-0.1.0.tar.gz"
        with tarfile.open(sdist_path, "w:gz") as archive:
            for relative_name, content in (
                ("alpha-0.1.0/pyproject.toml", "[tool.poetry]\nname = 'alpha'\n"),
                ("alpha-0.1.0/README.md", "# alpha\n"),
                ("alpha-0.1.0/CHANGELOG.md", "# changelog\n"),
                ("alpha-0.1.0/LICENSE.md", "license\n"),
            ):
                data = content.encode("utf-8")
                info = tarfile.TarInfo(relative_name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    monkeypatch.setattr(release_task, "_run_python_module", fake_run_python_module)

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == ["alpha"]
    assert payload["resolvedTargets"] == ["alpha"]
    assert payload["topologicalOrder"] == ["alpha"]
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["publishTarget"] == "pypi"
    assert payload["results"][0]["artifacts"]["metadata"]["licensePresent"] is True


def test_release_verify_python_passes_standard_check_manifest_ignore_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text("# alpha\n", encoding="utf-8")
    (project_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    (project_path / "LICENSE.md").write_text("license\n", encoding="utf-8")
    (project_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'alpha'\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    check_manifest_args: list[str] = []

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(release_task.importlib, "import_module", lambda _name: object())

    def fake_run_python_module(module: str, args: list[str], *, cwd: Path, redirect_output: bool) -> None:
        del cwd, redirect_output
        if module == "check_manifest":
            check_manifest_args[:] = args
            return
        if module != "build":
            return
        out_dir = Path(args[args.index("--outdir") + 1])
        wheel_path = out_dir / "alpha-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as archive:
            archive.writestr("alpha/__init__.py", "__version__ = '0.1.0'\n")
            archive.writestr(
                "alpha-0.1.0.dist-info/METADATA",
                "\n".join(
                    [
                        "Metadata-Version: 2.3",
                        "Name: alpha",
                        "Version: 0.1.0",
                        "License: AGPL-3.0-or-later",
                        "Home-page: https://github.com/wabbit-corp/alpha",
                        "Description-Content-Type: text/markdown",
                        "",
                        "# alpha",
                    ]
                ),
            )
        sdist_path = out_dir / "alpha-0.1.0.tar.gz"
        with tarfile.open(sdist_path, "w:gz") as archive:
            for relative_name, content in (
                ("alpha-0.1.0/pyproject.toml", "[tool.poetry]\nname = 'alpha'\n"),
                ("alpha-0.1.0/README.md", "# alpha\n"),
                ("alpha-0.1.0/CHANGELOG.md", "# changelog\n"),
                ("alpha-0.1.0/LICENSE.md", "license\n"),
            ):
                data = content.encode("utf-8")
                info = tarfile.TarInfo(relative_name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    monkeypatch.setattr(release_task, "_run_python_module", fake_run_python_module)

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    json.loads(capsys.readouterr().out)
    assert check_manifest_args[0] == "--ignore"
    assert ".llm/**" in check_manifest_args[1]
    assert "docs-research/**" in check_manifest_args[1]
    assert ".github/**" in check_manifest_args[1]
    assert ".editorconfig" in check_manifest_args[1]
    assert "AGENTS.md" in check_manifest_args[1]


def test_release_verify_python_reports_missing_check_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "README.md").write_text("# alpha\n", encoding="utf-8")
    (project_path / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
    (project_path / "LICENSE.md").write_text("license\n", encoding="utf-8")
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])

    def fake_import_module(name: str) -> object:
        if name == "check_manifest":
            raise ModuleNotFoundError(name)
        return object()

    monkeypatch.setattr(release_task.importlib, "import_module", fake_import_module)

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 1
    assert payload["results"][0]["status"] == "failed"
    assert "check-manifest" in payload["results"][0]["error"]


def test_release_verify_gradle_runs_maven_local_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_gradle_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    commands: list[list[str]] = []

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(
        release_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["preflight"]["mavenCentral"]["status"] == "pass"
    assert commands == [["gradle", "--no-daemon", "build", "publishToMavenLocal"]]


def test_release_verify_kmp_gradle_uses_multiplatform_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_gradle_project(project_path)
    project.build_model = "kmp"
    project.platforms = ["jvm", "linuxX64", "mingwX64"]

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    commands: list[list[str]] = []

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(
        release_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] == 1
    assert payload["results"][0]["status"] == "success"
    assert commands == [["gradle", "--no-daemon", "publishKotlinMultiplatformPublicationToMavenLocal"]]


def test_release_verify_gradle_skips_when_cross_repo_dependency_missing_from_maven_central(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config, Dependency, DependencyTarget

    alpha_path = tmp_path / "alpha"
    beta_path = tmp_path / "beta"
    alpha_path.mkdir()
    beta_path.mkdir()

    alpha = _make_gradle_project(alpha_path)
    beta = _make_gradle_project(beta_path)
    alpha.name = "alpha"
    alpha.project_id = "alpha"
    alpha.resolved_dependencies = [Dependency(scope="implementation", target=DependencyTarget.Project(project="beta"))]
    beta.name = "beta"
    beta.project_id = "beta"
    beta.artifact_id = "beta-artifact"

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = alpha
    config.defined_projects["beta"] = beta

    commands: list[list[str]] = []

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])

    import requests

    class NotFoundError(requests.HTTPError):
        def __init__(self) -> None:
            super().__init__("404")
            self.response = SimpleNamespace(status_code=404)

    monkeypatch.setattr(
        release_task,
        "_fetch_maven_central_metadata",
        lambda *_args: (_ for _ in ()).throw(NotFoundError()),
    )
    monkeypatch.setattr(
        release_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["skipped"] == 1
    assert payload["results"][0]["status"] == "skipped"
    assert payload["results"][0]["reason"] == "external-project-dependencies-missing-from-maven-central"
    missing = payload["results"][0]["missingDependencies"]
    assert missing[0]["projectId"] == "beta"
    assert missing[0]["coordinate"] == "one.wabbit:beta-artifact:0.1.0"
    assert commands == []


def test_release_verify_gradle_restores_local_overlay_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_verify as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "settings.local.gradle.kts").write_text("// local\n", encoding="utf-8")
    project = _make_gradle_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(
        release_task.subprocess,
        "run",
        lambda command, cwd, check, **kwargs: SimpleNamespace(returncode=0),
    )

    result = release_task.release_verify(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["localOverlayPresentBeforeVerify"] is True
    assert (project_path / "settings.local.gradle.kts").is_file()
    assert not (project_path / ".settings.local.gradle.kts.release-verify.backup").exists()
