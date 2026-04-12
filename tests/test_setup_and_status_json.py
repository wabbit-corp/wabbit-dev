from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from mu.parser import parse


def test_setup_json_output_reports_selected_projects(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.setup as setup_module
    from dev.config import Config

    project = SimpleNamespace(
        name="demo",
        project_id="demo",
        repo_id=None,
        path=tmp_path / "demo",
        github_repo=None,
    )
    project.path.mkdir()

    config = Config(raw=parse("()"))
    config.defined_projects["demo"] = project

    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, _mode: SimpleNamespace(config=config, mode=_mode),
    )
    monkeypatch.setattr(setup_module, "toposort_projects", lambda _projects, target_project=None: ["demo"])
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "_write_repo_metadata_files", lambda *_args, **_kwargs: [str(tmp_path.resolve())])
    monkeypatch.setattr(
        setup_module,
        "_write_repo_agents_files",
        lambda *_args, **_kwargs: [str((tmp_path / "demo" / "AGENTS.md").resolve())],
    )

    result = setup_module.setup(
        setup_module.RepoSetupMode.PROD,
        interactive=False,
        project="demo",
        json_output=True,
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "prod"
    assert payload["requestedTargets"] == ["demo"]
    assert payload["selectedProjectIds"] == ["demo"]
    assert payload["repoMetadataRootsWritten"] == [str(tmp_path.resolve())]
    assert payload["repoAgentsWritten"] == [str((tmp_path / "demo" / "AGENTS.md").resolve())]
    assert payload["summary"]["selectedProjectCount"] == 1


def test_status_json_output_reports_repo_status(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.status as status_task
    from dev.repo_status import RepoStatusRecord

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    monkeypatch.setattr(status_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(
        status_task,
        "collect_repo_status_record",
        lambda _target: RepoStatusRecord(
            name="alpha",
            path=tmp_path,
            staged_changes=("src/main.py",),
            unstaged_changes=("README.md",),
            untracked_files=("notes.txt",),
        ),
    )

    result = status_task.status(["alpha"], json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == ["alpha"]
    assert payload["repos"][0]["name"] == "alpha"
    assert payload["repos"][0]["stagedChanges"] == ["src/main.py"]
    assert payload["repos"][0]["unstagedChanges"] == ["README.md"]
    assert payload["repos"][0]["untrackedFiles"] == ["notes.txt"]


def test_status_json_output_uses_inferred_repo_target(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.status as status_task
    from dev.repo_status import RepoStatusRecord

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    monkeypatch.setattr(status_task, "find_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(status_task, "load_config", lambda: object())
    monkeypatch.setattr(status_task, "inferred_repo_targets", lambda config, targets=None: ["alpha"])
    monkeypatch.setattr(status_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(
        status_task,
        "collect_repo_status_record",
        lambda _target: RepoStatusRecord(
            name="alpha",
            path=tmp_path,
            staged_changes=(),
            unstaged_changes=("src/main.py",),
            untracked_files=(),
        ),
    )

    result = status_task.status(None, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == []
    assert payload["inferredTargets"] == ["alpha"]
    assert payload["repos"][0]["name"] == "alpha"
    assert payload["repos"][0]["unstagedChanges"] == ["src/main.py"]


def test_setup_json_output_ignores_configured_repo_roots_in_unexpected_directories(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import dev.tasks.setup as setup_module
    from dev.config import Config

    repo_root = tmp_path / "app-jove"
    nested_project_path = repo_root / "src" / "server"
    nested_project_path.mkdir(parents=True)
    standalone_path = tmp_path / "standalone-tool"
    standalone_path.mkdir()
    unexpected_path = tmp_path / "mystery-dir"
    unexpected_path.mkdir()

    repo_project = SimpleNamespace(
        name="server",
        project_id="app-jove/src/server",
        repo_id="app-jove",
        path=nested_project_path,
        repo_root=repo_root,
        github_repo=None,
    )
    standalone_project = SimpleNamespace(
        name="standalone-tool",
        project_id="standalone-tool",
        repo_id=None,
        path=standalone_path,
        repo_root=standalone_path,
        github_repo=None,
    )

    config = Config(raw=parse("()"))
    config.workspace_root = tmp_path
    config.defined_projects[repo_project.project_id] = repo_project
    config.defined_projects[standalone_project.project_id] = standalone_project

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_module, "load_config", lambda: config)
    monkeypatch.setattr(setup_module, "inferred_project_targets", lambda _config, _targets: None)
    monkeypatch.setattr(
        setup_module,
        "create_repo_setup_context",
        lambda _config, _mode, require_github_api=False: SimpleNamespace(config=config, mode=_mode),
    )
    monkeypatch.setattr(
        setup_module,
        "toposort_projects",
        lambda _projects, target_project=None: [repo_project.project_id, standalone_project.project_id],
    )
    monkeypatch.setattr(setup_module, "setup_project", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(setup_module, "_write_repo_metadata_files", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(setup_module, "_write_repo_agents_files", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(setup_module, "_write_repo_docs_root", lambda *_args, **_kwargs: None)

    result = setup_module.setup(
        setup_module.RepoSetupMode.LOCAL,
        interactive=False,
        json_output=True,
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == []
    assert payload["unexpectedDirectories"] == [str(unexpected_path.resolve())]
