from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_publish_dry_run_prints_plan_without_calling_publishers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.publish as publish_task

    alpha = SimpleNamespace(name="alpha")
    beta = SimpleNamespace(name="beta")
    config = SimpleNamespace(defined_projects={"alpha": alpha, "beta": beta})

    calls: list[str] = []

    monkeypatch.setattr(publish_task, "load_config", lambda: config)
    monkeypatch.setattr(publish_task, "resolve_project_ids", lambda config, targets: list(targets))
    monkeypatch.setattr(publish_task, "toposort_projects", lambda _projects, target_project=None: ["alpha", "beta"])
    monkeypatch.setattr(publish_task, "determine_publish_target", lambda project: "pypi" if project.name == "alpha" else "skip")
    monkeypatch.setattr(publish_task, "create_repo_setup_context", lambda *_args, **_kwargs: calls.append("setup"))
    monkeypatch.setattr(publish_task, "publish_python_project_to_pypi", lambda *args, **kwargs: calls.append("pypi"))

    result = await publish_task.publish_main(["alpha"], dry_run=True)

    assert result == 0
    assert calls == []
    output = capsys.readouterr().out
    assert "Topological order of projects to publish:" in output
    assert "Dry run: planned publish actions:" in output
    assert "alpha: publish to pypi" in output
    assert "beta: skip" in output


def test_push_dry_run_prints_targets_without_pushing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.push as push_task

    repo_target = SimpleNamespace(name="alpha", path=Path("/tmp/alpha"))
    repo_calls: list[str] = []

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            repo_calls.append("repo-opened")
            self.git = SimpleNamespace(push=lambda *args, **kwargs: repo_calls.append("push"))

        def close(self) -> None:
            repo_calls.append("repo-closed")

    monkeypatch.setattr(push_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(push_task, "load_config", lambda: object())
    monkeypatch.setattr(push_task, "Repo", FakeRepo)

    result = push_task.push(["alpha"], dry_run=True)

    assert result == 0
    assert repo_calls == []
    output = capsys.readouterr().out
    assert "Dry run: would push 1 repository/repositories" in output
    assert "alpha: origin master + tags" in output
