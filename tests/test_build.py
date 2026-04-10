from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_build_publishes_local_compiler_plugin_before_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mu.types import Document

    import dev.tasks.build as build_module
    from dev.config import (
        Config,
        Feature,
        GradlePluginApplication,
        GradlePlugins,
        GradleProject,
        KotlinPluginDefinition,
        OwnershipType,
        Version,
    )

    def make_gradle_project(
        path: Path,
        *,
        project_id: str,
        gradle_root_path: Path,
        gradle_project_name: str,
        resolved_features: dict[str, Feature] | None = None,
    ) -> GradleProject:
        return GradleProject(
            path=path,
            group_name="one.wabbit",
            name=gradle_project_name,
            version=Version.parse("0.0.1"),
            description=None,
            authors=[],
            license="AGPL",
            quarantine=False,
            publish=False,
            github_repo="org/repo",
            ownership=OwnershipType.IMPORTED,
            raw_dependencies=[],
            raw_features=[],
            resolved_dependencies=[],
            resolved_maven_repositories=[],
            resolved_features=resolved_features or {},
            platforms=["jvm"],
            source_set_dependencies={},
            project_id=project_id,
            repo_id=project_id.split("/", 1)[0] if "/" in project_id else None,
            repo_root=gradle_root_path,
            gradle_root=gradle_root_path,
            module_dir=Path(path.name),
            gradle_project_name=gradle_project_name,
        )

    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir(parents=True, exist_ok=True)
    (consumer_root / "settings.local.gradle.kts").write_text("// local\n", encoding="utf-8")
    consumer_project = make_gradle_project(
        consumer_root,
        project_id="consumer",
        gradle_root_path=consumer_root,
        gradle_project_name="consumer",
        resolved_features={
            "gradle-plugin": GradlePlugins(entries=[GradlePluginApplication(name="acyclic-gradle")]),
        },
    )

    compiler_root = tmp_path / "kotlin-acyclic"
    compiler_project = make_gradle_project(
        compiler_root / "compiler-plugin",
        project_id="kotlin-acyclic/compiler-plugin",
        gradle_root_path=compiler_root,
        gradle_project_name="compiler-plugin",
    )
    gradle_plugin_project = make_gradle_project(
        compiler_root / "gradle-plugin",
        project_id="kotlin-acyclic/gradle-plugin",
        gradle_root_path=compiler_root,
        gradle_project_name="gradle-plugin",
    )
    gradle_plugin_project.gradle_plugin_id = "one.wabbit.acyclic"

    config = Config(raw=Document([]))
    config.defined_projects.update(
        {
            "consumer": consumer_project,
            "kotlin-acyclic/compiler-plugin": compiler_project,
            "kotlin-acyclic/gradle-plugin": gradle_plugin_project,
        }
    )
    config.plugins["acyclic-gradle"] = KotlinPluginDefinition(
        project="kotlin-acyclic/gradle-plugin",
        compiler_plugin="kotlin-acyclic/compiler-plugin",
    )

    commands: list[tuple[Path, list[str]]] = []

    def fake_load_config() -> Config:
        return config

    def fake_toposort_projects(
        _projects: dict[str, GradleProject],
        target_project: str | list[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        del target_project
        return ["consumer"]

    monkeypatch.setattr(build_module, "load_config", fake_load_config)
    monkeypatch.setattr(build_module, "toposort_projects", fake_toposort_projects)

    def fake_run(command: list[str], cwd: Path, check: bool) -> SimpleNamespace:
        del check
        commands.append((cwd, command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(build_module.subprocess, "run", fake_run)

    build_module.build(["consumer"])

    assert commands == [
        (
            compiler_root,
            ["gradle", "--no-daemon", ":compiler-plugin:publishToMavenLocal"],
        ),
        (
            consumer_root,
            ["gradle", "--no-daemon", "build"],
        ),
    ]


def test_build_json_output_reports_python_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mu.parser import parse

    import dev.tasks.build as build_module
    from dev.config import Config, OwnershipType, Project, PythonProject

    project_path = tmp_path / "alpha"
    project_path.mkdir()
    (project_path / "main.py").write_text("print('ok')\n", encoding="utf-8")

    project = PythonProject(
        path=project_path,
        name="alpha",
        version=None,
        description=None,
        authors=[],
        license=None,
        github_repo=None,
        requires_python=None,
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
        project_id="alpha",
    )

    config = Config(raw=parse("()"))
    config.defined_projects["alpha"] = project

    def fake_load_config() -> Config:
        return config

    def fake_resolve_project_ids(_config: Config, targets: list[str]) -> list[str]:
        assert targets == ["alpha"]
        return ["alpha"]

    def fake_toposort_projects(
        _projects: dict[str, Project],
        target_project: str | list[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        del target_project
        return ["alpha"]

    monkeypatch.setattr(build_module, "load_config", fake_load_config)
    monkeypatch.setattr(build_module, "resolve_project_ids", fake_resolve_project_ids)
    monkeypatch.setattr(build_module, "toposort_projects", fake_toposort_projects)

    result = build_module.build(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == ["alpha"]
    assert payload["resolvedTargets"] == ["alpha"]
    assert payload["topologicalOrder"] == ["alpha"]
    assert payload["results"][0]["projectId"] == "alpha"
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["sourceCount"] == 1
