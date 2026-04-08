from __future__ import annotations

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

    monkeypatch.setattr(build_module, "load_config", lambda: config)
    monkeypatch.setattr(build_module, "toposort_projects", lambda _projects, target_project=None: ["consumer"])

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
