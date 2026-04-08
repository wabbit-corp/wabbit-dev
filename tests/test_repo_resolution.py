from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import pytest
from mu.parser import parse

from dev.config import Config, OwnershipType, PythonProject, RepoDefinition, Version
from dev.repo_resolution import (
    inferred_project_targets,
    inferred_repo_targets,
    resolve_project_ids,
    resolve_workspace_context,
)


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


def test_resolve_workspace_context_prefers_current_project(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "root.clj").write_text("()", encoding="utf-8")

    repo_root = workspace / "jeeves"
    project_path = repo_root / "client"
    nested_path = project_path / "src" / "commonMain" / "kotlin"
    nested_path.mkdir(parents=True)

    config = Config(raw=parse("()"), workspace_root=workspace)
    config.defined_repos["jeeves"] = RepoDefinition(
        repo_id="jeeves",
        path=repo_root,
        github_repo=None,
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["jeeves/client"],
    )
    config.defined_projects = OrderedDict(
        [("jeeves/client", _python_project(project_path, project_id="jeeves/client", repo_id="jeeves", repo_root=repo_root))]
    )

    context = resolve_workspace_context(nested_path, config=config)

    assert context.workspace_root == workspace.resolve()
    assert context.current_project_id == "jeeves/client"
    assert context.current_repo_target == "jeeves"
    assert inferred_project_targets(config, start=nested_path) == ["jeeves/client"]
    assert inferred_repo_targets(config, start=nested_path) == ["jeeves"]


def test_inferred_targets_use_repo_when_outside_project_but_inside_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "root.clj").write_text("()", encoding="utf-8")

    repo_root = workspace / "jeeves"
    repo_root.mkdir()
    project_path = repo_root / "client"
    project_path.mkdir()
    docs_path = repo_root / "docs"
    docs_path.mkdir()

    config = Config(raw=parse("()"), workspace_root=workspace)
    config.defined_repos["jeeves"] = RepoDefinition(
        repo_id="jeeves",
        path=repo_root,
        github_repo=None,
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["jeeves/client"],
    )
    config.defined_projects = OrderedDict(
        [("jeeves/client", _python_project(project_path, project_id="jeeves/client", repo_id="jeeves", repo_root=repo_root))]
    )

    context = resolve_workspace_context(docs_path, config=config)

    assert context.current_project_id is None
    assert context.current_repo_target == "jeeves"
    assert inferred_project_targets(config, start=docs_path) == ["jeeves"]
    assert inferred_repo_targets(config, start=docs_path) == ["jeeves"]


def test_resolve_project_ids_errors_include_resolved_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "root.clj").write_text("()", encoding="utf-8")

    repo_root = workspace / "jeeves"
    project_path = repo_root / "client"
    project_path.mkdir(parents=True)

    config = Config(raw=parse("()"), workspace_root=workspace)
    config.defined_repos["jeeves"] = RepoDefinition(
        repo_id="jeeves",
        path=repo_root,
        github_repo=None,
        gradle_root_project_name=None,
        jvm_policy=None,
        project_ids=["jeeves/client"],
    )
    config.defined_projects = OrderedDict(
        [("jeeves/client", _python_project(project_path, project_id="jeeves/client", repo_id="jeeves", repo_root=repo_root))]
    )

    monkeypatch.chdir(project_path)

    with pytest.raises(ValueError) as excinfo:
        resolve_project_ids(config, ["jeeves/clinet"])

    message = str(excinfo.value)
    assert "Unknown project or repo: 'jeeves/clinet'" in message
    assert "Resolved context:" in message
    assert "current project: jeeves/client" in message
    assert "current repo: jeeves" in message
