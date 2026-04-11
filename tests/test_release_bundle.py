from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from mu.parser import parse


def _make_python_project(path: Path):
    from dev.config import OwnershipType, PythonProject, Version

    return PythonProject(
        path=path,
        name="alpha",
        version=Version.parse("0.1.0"),
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


def test_release_bundle_python_json_output_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_bundle as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    project = _make_python_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])
    monkeypatch.setattr(release_task.importlib, "import_module", lambda _name: 1)

    def fake_run_python_module(module: str, args: list[str], *, cwd: Path, redirect_output: bool) -> None:
        del cwd, redirect_output
        if module != "build":
            return
        out_dir = Path(args[args.index("--outdir") + 1])
        wheel_path = out_dir / "alpha-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as archive:
            archive.writestr("alpha/__init__.py", "__version__ = '0.1.0'\n")
        sdist_path = out_dir / "alpha-0.1.0.tar.gz"
        with tarfile.open(sdist_path, "w:gz") as archive:
            source = out_dir / "alpha-0.1.0" / "README.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# alpha\n", encoding="utf-8")
            archive.add(source, arcname="alpha-0.1.0/README.md")

    monkeypatch.setattr(release_task, "_run_python_module", fake_run_python_module)

    result = release_task.release_bundle(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {
        "total": 1,
        "success": 1,
        "failed": 0,
        "skipped": 0,
        "unsupported": 0,
    }
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["bundle"]["bundleKind"] == "python-dist"
    assert payload["repos"][0]["aggregateBundle"]["fileName"] == "alpha-0.1.0-all.zip"
    assert (project_path / "build" / "releases" / "alpha-0.1.0-alpha.zip").is_file()
    assert (project_path / "build" / "releases" / "alpha-0.1.0-all.zip").is_file()
    assert (project_path / "build" / "releases" / "release-manifest.json").is_file()
    assert (project_path / "build" / "releases" / "SHA256SUMS").is_file()


def test_release_bundle_gradle_uses_publications_and_restores_local_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.release_bundle as release_task
    from dev.config import Config

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "settings.local.gradle.kts").write_text("// local overlay\n", encoding="utf-8")
    (project_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    project = _make_gradle_project(project_path)

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    monkeypatch.setattr(release_task, "load_config", lambda: config)
    monkeypatch.setattr(release_task, "resolve_project_ids", lambda _config, targets: list(targets))
    monkeypatch.setattr(release_task, "toposort_projects", lambda _projects, target_project=None: ["alpha"])

    def fake_run(command: list[str], cwd: Path, check: bool, stdout=None, stderr=None) -> None:
        del command, check, stdout, stderr
        publications_dir = cwd / "build" / "publications" / "maven"
        publications_dir.mkdir(parents=True, exist_ok=True)
        (publications_dir / "pom-default.xml").write_text("<project />\n", encoding="utf-8")

    monkeypatch.setattr(release_task.subprocess, "run", fake_run)

    result = release_task.release_bundle(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["bundle"]["bundleKind"] == "gradle-publications"
    assert (project_path / "settings.local.gradle.kts").is_file()
    assert not (project_path / ".settings.local.gradle.kts.release-bundle.backup").exists()
    assert (project_path / "build" / "releases" / "alpha-0.1.0-alpha.zip").is_file()
