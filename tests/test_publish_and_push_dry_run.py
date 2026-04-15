from __future__ import annotations

from contextlib import contextmanager
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
    monkeypatch.setattr(
        publish_task, "determine_publish_target", lambda project: "pypi" if project.name == "alpha" else "skip"
    )
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

    monkeypatch.setattr(push_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(push_task, "load_config", lambda: object())
    monkeypatch.setattr(
        push_task,
        "push_resolved_repo_target",
        lambda _config, _target, *, dry_run=False: (True, "would push master -> origin/master (ahead 2, behind 0)"),
    )

    result = push_task.push(["alpha"], dry_run=True)

    assert result == 0
    output = capsys.readouterr().out
    assert "Dry run: would push 1 repository/repositories" in output
    assert "alpha: would push master -> origin/master (ahead 2, behind 0)" in output


def test_push_resolved_repo_target_pushes_current_tracking_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    repo_root.mkdir()
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeGit:
        def fetch(self, *args: str) -> None:
            calls.append(("fetch", args))

        def push(self, *args: str) -> None:
            calls.append(("push", args))

    class FakeRepo:
        def __init__(self, *_args, **_kwargs) -> None:
            self.git = FakeGit()

        def close(self) -> None:
            calls.append(("close", ()))

    tracking_states = iter(
        [
            push_task.PushTargetState(
                branch_name="feature",
                upstream_name="origin/feature",
                remote_name="origin",
                remote_branch_name="feature",
                ahead_count=1,
                behind_count=0,
            ),
        ]
    )

    @contextmanager
    def fake_configured_git_ssh(_git: object, _config: object):
        yield

    def fake_tracking_state_for_push(_repo: object, _target_name: str, *, config: object):
        del config
        return next(tracking_states), None

    monkeypatch.setattr(push_task, "Repo", FakeRepo)
    monkeypatch.setattr(push_task, "configured_git_ssh", fake_configured_git_ssh)
    monkeypatch.setattr(push_task, "_tracking_state_for_push", fake_tracking_state_for_push)

    ok, message = push_task.push_resolved_repo_target(
        SimpleNamespace(),
        SimpleNamespace(name="alpha", path=repo_root),
    )

    assert ok is True
    assert message == "alpha: pushed feature -> origin/feature (ahead 1, behind 0)"
    assert calls == [("push", ("origin", "feature:feature")), ("close", ())]


def test_push_continues_after_blocked_repo(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import dev.tasks.push as push_task

    repo_targets = [
        SimpleNamespace(name="alpha", path=Path("/tmp/alpha")),
        SimpleNamespace(name="beta", path=Path("/tmp/beta")),
    ]

    def fake_push_resolved_repo_target(_config: object, target: object, *, dry_run: bool = False) -> tuple[bool, str]:
        del dry_run
        name = target.name
        if name == "alpha":
            return False, "alpha: cannot push branch behind upstream master -> origin/master (ahead 0, behind 1)"
        return True, "beta: pushed master -> origin/master (ahead 3, behind 0)"

    monkeypatch.setattr(push_task, "load_config", lambda: object())
    monkeypatch.setattr(push_task, "resolve_repo_targets", lambda targets, config=None: repo_targets)
    monkeypatch.setattr(push_task, "push_resolved_repo_target", fake_push_resolved_repo_target)

    result = push_task.push(["alpha", "beta"])

    assert result == 1
    output = capsys.readouterr().out
    assert "alpha: cannot push branch behind upstream master -> origin/master (ahead 0, behind 1)" in output
    assert "beta: pushed master -> origin/master (ahead 3, behind 0)" in output
