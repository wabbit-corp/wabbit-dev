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

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            self.untracked_files = ["notes.txt"]
            self.git = SimpleNamespace(
                status=lambda *_args: "M  src/main.py\n M README.md\n?? notes.txt\n"
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(status_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(status_task, "Repo", FakeRepo)

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

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            self.untracked_files = []
            self.git = SimpleNamespace(status=lambda *_args: " M src/main.py\n")

        def close(self) -> None:
            return None

    monkeypatch.setattr(status_task, "find_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(status_task, "load_config", lambda: object())
    monkeypatch.setattr(status_task, "inferred_repo_targets", lambda config, targets=None: ["alpha"])
    monkeypatch.setattr(status_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(status_task, "Repo", FakeRepo)

    result = status_task.status(None, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == []
    assert payload["inferredTargets"] == ["alpha"]
    assert payload["repos"][0]["name"] == "alpha"
    assert payload["repos"][0]["unstagedChanges"] == ["src/main.py"]
