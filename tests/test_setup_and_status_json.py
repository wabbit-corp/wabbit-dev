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
    assert payload["repoAgentsWritten"] == [str((tmp_path / "demo" / "AGENTS.md").resolve())]
    assert payload["summary"]["selectedProjectCount"] == 1


def test_status_json_output_reports_tracked_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.status as status_task

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            self.index = SimpleNamespace(
                diff=lambda _other: [
                    SimpleNamespace(a_path="src/main.py"),
                    SimpleNamespace(a_path="README.md"),
                ]
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
    assert payload["repos"][0]["trackedChanges"] == ["src/main.py", "README.md"]


def test_status_json_output_uses_inferred_repo_target(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.status as status_task

    repo_target = SimpleNamespace(name="alpha", path=tmp_path)

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            self.index = SimpleNamespace(diff=lambda _other: [SimpleNamespace(a_path="src/main.py")])

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
