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
        lambda _config, _target, *, dry_run=False: (True, "would push | master -> origin/master | ahead 2, behind 0 | worktree clean"),
    )

    result = push_task.push(["alpha"], dry_run=True)

    assert result == 0
    output = capsys.readouterr().out
    assert "Dry run: would push 1 repository/repositories" in output
    assert "alpha: would push | master -> origin/master | ahead 2, behind 0 | worktree clean" in output


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

        def is_dirty(self, **_kwargs) -> bool:
            return False

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

    def fake_tracking_state_for_push(_repo: object, _target: object, *, config: object, dry_run: bool = False):
        del config
        del dry_run
        return next(tracking_states), None

    monkeypatch.setattr(push_task, "Repo", FakeRepo)
    monkeypatch.setattr(push_task, "configured_git_ssh", fake_configured_git_ssh)
    monkeypatch.setattr(push_task, "_tracking_state_for_push", fake_tracking_state_for_push)

    ok, message = push_task.push_resolved_repo_target(
        SimpleNamespace(),
        SimpleNamespace(name="alpha", path=repo_root, repo_id=None, project_ids=()),
    )

    assert ok is True
    assert message == "alpha: pushed | feature -> origin/feature | ahead 1, behind 0 | worktree clean"
    assert calls == [("push", ("origin", "feature:feature")), ("close", ())]


def test_push_resolved_repo_target_reports_clean_up_to_date_worktree(tmp_path: Path) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")

    ok, message = push_task.push_resolved_repo_target(
        SimpleNamespace(github_ssh_key=None),
        SimpleNamespace(name="alpha", path=repo_root, repo_id=None, project_ids=()),
    )

    assert ok is True
    assert message == "alpha: up to date | master -> origin/master | ahead 0, behind 0 | worktree clean"


def test_push_resolved_repo_target_reports_dirty_up_to_date_worktree(tmp_path: Path) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")
    (repo_root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    ok, message = push_task.push_resolved_repo_target(
        SimpleNamespace(github_ssh_key=None),
        SimpleNamespace(name="alpha", path=repo_root, repo_id=None, project_ids=()),
    )

    assert ok is True
    assert message == "alpha: up to date | master -> origin/master | ahead 0, behind 0 | worktree dirty"


def test_push_sets_missing_upstream_when_origin_matches_root_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")
    repo.git.branch("--unset-upstream", "master")
    repo.git.commit("--allow-empty", "-m", "local change")

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is True
    assert message == "alpha: pushed | master -> origin/master | ahead 1, behind 0 | worktree clean"
    assert repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}") == "origin/master"


def test_push_dry_run_reports_missing_upstream_repair_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")
    repo.git.branch("--unset-upstream", "master")

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target, dry_run=True)

    assert ok is False
    assert "alpha: would set upstream for master to origin/master" in message
    with pytest.raises(push_task.GitCommandError):
        repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}")


def test_push_creates_missing_upstream_branch_when_remote_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is True
    assert message == "alpha: pushed and set upstream | master -> origin/master | ahead 0, behind 0 | worktree clean"
    assert repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}") == "origin/master"
    assert repo.git.ls_remote("--heads", "origin", "master")


def test_push_dry_run_reports_empty_remote_branch_creation_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target, dry_run=True)

    assert ok is False
    assert "alpha: would create upstream branch origin/master from local master" in message
    assert repo.git.ls_remote("--heads", "origin") == ""
    with pytest.raises(push_task.GitCommandError):
        repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}")


def test_push_adds_missing_origin_then_creates_empty_remote_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is True
    assert message == "alpha: pushed and set upstream | master -> origin/master | ahead 0, behind 0 | worktree clean"
    assert repo.git.remote("get-url", "origin") == str(remote_root)
    assert repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}") == "origin/master"


def test_push_repairs_wrong_origin_then_creates_empty_remote_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    wrong_remote_root = tmp_path / "wrong.git"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(wrong_remote_root, bare=True).close()
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(wrong_remote_root))

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is True
    assert message == "alpha: pushed and set upstream | master -> origin/master | ahead 0, behind 0 | worktree clean"
    assert repo.git.remote("get-url", "origin") == str(remote_root)
    assert repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}") == "origin/master"


def test_push_repairs_wrong_origin_with_existing_upstream_before_push(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    wrong_remote_root = tmp_path / "wrong.git"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(wrong_remote_root, bare=True).close()
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")
    repo.git.remote("set-url", "origin", str(wrong_remote_root))
    repo.git.commit("--allow-empty", "-m", "local change")

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is True
    assert message == "alpha: pushed | master -> origin/master | ahead 1, behind 0 | worktree clean"
    assert repo.git.remote("get-url", "origin") == str(remote_root)
    assert repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}") == "origin/master"


def test_push_dry_run_reports_origin_repair_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    wrong_remote_root = tmp_path / "wrong.git"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(wrong_remote_root, bare=True).close()
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(wrong_remote_root))

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target, dry_run=True)

    assert ok is False
    assert f"would set origin from {wrong_remote_root} to {remote_root}" in message
    assert "and create upstream branch origin/master from local master" in message
    assert repo.git.remote("get-url", "origin") == str(wrong_remote_root)


def test_push_does_not_create_missing_branch_when_remote_has_other_heads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    seed_root = tmp_path / "seed"
    remote_root = tmp_path / "remote.git"
    push_task.Repo.init(remote_root, bare=True).close()

    seed = push_task.Repo.init(seed_root)
    seed.git.checkout("-b", "main")
    seed.git.commit("--allow-empty", "-m", "seed")
    seed.git.remote("add", "origin", str(remote_root))
    seed.git.push("-u", "origin", "main")

    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    repo.git.remote("add", "origin", str(remote_root))

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=str(remote_root),
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    monkeypatch.setattr(push_task, "_github_ssh_url", lambda value: value)

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is False
    assert "origin/master is missing; remote has other branches: main" in message
    assert repo.git.ls_remote("--heads", "origin", "master") == ""
    with pytest.raises(push_task.GitCommandError):
        repo.git.rev_parse("--abbrev-ref", "--symbolic-full-name", "@{u}")


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
        return True, "beta: pushed | master -> origin/master | ahead 3, behind 0 | worktree clean"

    monkeypatch.setattr(push_task, "load_config", lambda: object())
    monkeypatch.setattr(push_task, "resolve_repo_targets", lambda targets, config=None: repo_targets)
    monkeypatch.setattr(push_task, "push_resolved_repo_target", fake_push_resolved_repo_target)

    result = push_task.push(["alpha", "beta"])

    assert result == 1
    output = capsys.readouterr().out
    assert "alpha: cannot push branch behind upstream master -> origin/master (ahead 0, behind 1)" in output
    assert "beta: pushed | master -> origin/master | ahead 3, behind 0 | worktree clean" in output


def test_push_missing_upstream_reports_configuration_diagnostics(
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    repo_root.mkdir()
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    repo.git.remote("add", "origin", "git@github.com:wrong-org/alpha.git")

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=None,
                quarantine=True,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is False
    assert "alpha: branch master has no configured upstream" in message
    assert "root.clj repo=missing" in message
    assert "quarantine=true" in message
    assert "local origin=git@github.com:wrong-org/alpha.git" in message
    assert "configured remote=missing" in message
    assert "origin matches root.clj=not checked" in message
    assert "configured remote reachable=not checked (no configured GitHub repo)" in message
    assert "upstream=missing" in message


def test_push_fetch_failure_reports_diagnostics_without_configured_remote(
    tmp_path: Path,
) -> None:
    import dev.tasks.push as push_task

    repo_root = tmp_path / "alpha"
    remote_root = tmp_path / "remote.git"
    repo = push_task.Repo.init(repo_root)
    repo.git.commit("--allow-empty", "-m", "initial")
    push_task.Repo.init(remote_root, bare=True).close()
    repo.git.remote("add", "origin", str(remote_root))
    repo.git.push("-u", "origin", "master")
    repo.git.remote("set-url", "origin", "git@github.com:wrong-org/alpha.git")

    config = SimpleNamespace(
        defined_repos={},
        defined_projects={
            "alpha": SimpleNamespace(
                name="alpha",
                github_repo=None,
                quarantine=False,
            )
        },
        github_ssh_key=None,
    )
    target = SimpleNamespace(
        name="alpha",
        path=repo_root,
        repo_id=None,
        project_ids=("alpha",),
    )

    ok, message = push_task.push_resolved_repo_target(config, target)

    assert ok is False
    assert "alpha: failed to refresh origin" in message
    assert "root.clj repo=missing" in message
    assert "quarantine=false" in message
    assert "local origin=git@github.com:wrong-org/alpha.git" in message
    assert "configured remote=missing" in message
    assert "origin matches root.clj=not checked" in message
    assert "configured remote reachable=not checked (no configured GitHub repo)" in message
    assert "upstream=origin/master" in message
