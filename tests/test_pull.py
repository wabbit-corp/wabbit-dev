from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _commit_file(repo, path: Path, text: str, message: str) -> None:
    path.write_text(text, encoding="utf-8")
    repo.git.add(path.name)
    repo.git.commit("-m", message)


def _make_pull_repo(tmp_path: Path):
    import dev.tasks.pull as pull_task

    remote_root = tmp_path / "remote.git"
    seed_root = tmp_path / "seed"
    clone_root = tmp_path / "clone"

    pull_task.Repo.init(remote_root, bare=True).close()
    seed = pull_task.Repo.init(seed_root)
    _commit_file(seed, seed_root / "README.md", "one\n", "initial")
    seed.git.remote("add", "origin", str(remote_root))
    seed.git.push("-u", "origin", "master")

    clone = pull_task.Repo.clone_from(str(remote_root), clone_root)
    return remote_root, seed_root, seed, clone_root, clone


def _config() -> SimpleNamespace:
    return SimpleNamespace(github_ssh_key=None)


def _target(path: Path) -> SimpleNamespace:
    return SimpleNamespace(name="alpha", path=path)


def test_pull_dry_run_prints_targets_without_fast_forwarding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.pull as pull_task

    repo_target = SimpleNamespace(name="alpha", path=Path("/tmp/alpha"))

    monkeypatch.setattr(pull_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(pull_task, "load_config", lambda: object())
    monkeypatch.setattr(
        pull_task,
        "pull_resolved_repo_target",
        lambda _config, _target, *, dry_run=False: (
            True,
            "would fast-forward master -> origin/master (ahead 0, behind 2)",
        ),
    )

    result = pull_task.pull(["alpha"], dry_run=True)

    assert result == 0
    output = capsys.readouterr().out
    assert "Dry run: would pull 1 repository/repositories" in output
    assert "alpha: would fast-forward master -> origin/master (ahead 0, behind 2)" in output


def test_pull_resolved_repo_target_fast_forwards_branch(tmp_path: Path) -> None:
    import dev.tasks.pull as pull_task

    _remote_root, seed_root, seed, clone_root, clone = _make_pull_repo(tmp_path)
    _commit_file(seed, seed_root / "README.md", "two\n", "remote update")
    seed.git.push("origin", "master")

    ok, message = pull_task.pull_resolved_repo_target(_config(), _target(clone_root))

    assert ok is True
    assert message == "alpha: fast-forwarded master -> origin/master (ahead 0, behind 1)"
    assert (clone_root / "README.md").read_text(encoding="utf-8") == "two\n"
    assert clone.git.status("--short", "--branch").splitlines()[0] == "## master...origin/master"


def test_pull_resolved_repo_target_dry_run_does_not_move_branch(tmp_path: Path) -> None:
    import dev.tasks.pull as pull_task

    _remote_root, seed_root, seed, clone_root, clone = _make_pull_repo(tmp_path)
    before = clone.git.rev_parse("HEAD")
    _commit_file(seed, seed_root / "README.md", "two\n", "remote update")
    seed.git.push("origin", "master")

    ok, message = pull_task.pull_resolved_repo_target(_config(), _target(clone_root), dry_run=True)

    assert ok is True
    assert message == "would fast-forward master -> origin/master (ahead 0, behind 1)"
    assert clone.git.rev_parse("HEAD") == before
    assert (clone_root / "README.md").read_text(encoding="utf-8") == "one\n"


def test_pull_refuses_diverged_branch(tmp_path: Path) -> None:
    import dev.tasks.pull as pull_task

    _remote_root, seed_root, seed, clone_root, clone = _make_pull_repo(tmp_path)
    _commit_file(seed, seed_root / "README.md", "remote\n", "remote update")
    seed.git.push("origin", "master")
    _commit_file(clone, clone_root / "local.txt", "local\n", "local update")

    ok, message = pull_task.pull_resolved_repo_target(_config(), _target(clone_root))

    assert ok is False
    assert message == "alpha: cannot pull diverged branch master -> origin/master (ahead 1, behind 1)"


def test_pull_refuses_dirty_worktree_before_fast_forward(tmp_path: Path) -> None:
    import dev.tasks.pull as pull_task

    _remote_root, seed_root, seed, clone_root, _clone = _make_pull_repo(tmp_path)
    _commit_file(seed, seed_root / "README.md", "two\n", "remote update")
    seed.git.push("origin", "master")
    (clone_root / "local.txt").write_text("dirty\n", encoding="utf-8")

    ok, message = pull_task.pull_resolved_repo_target(_config(), _target(clone_root))

    assert ok is False
    assert message == "alpha: cannot pull with local changes master -> origin/master (ahead 0, behind 1)"


def test_pull_continues_after_blocked_repo(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import dev.tasks.pull as pull_task

    repo_targets = [
        SimpleNamespace(name="alpha", path=Path("/tmp/alpha")),
        SimpleNamespace(name="beta", path=Path("/tmp/beta")),
    ]

    def fake_pull_resolved_repo_target(_config: object, target: object, *, dry_run: bool = False) -> tuple[bool, str]:
        del dry_run
        name = target.name
        if name == "alpha":
            return False, "alpha: cannot pull diverged branch master -> origin/master (ahead 1, behind 1)"
        return True, "beta: fast-forwarded master -> origin/master (ahead 0, behind 3)"

    monkeypatch.setattr(pull_task, "load_config", lambda: object())
    monkeypatch.setattr(pull_task, "resolve_repo_targets", lambda targets, config=None: repo_targets)
    monkeypatch.setattr(pull_task, "pull_resolved_repo_target", fake_pull_resolved_repo_target)

    result = pull_task.pull(["alpha", "beta"])

    assert result == 1
    output = capsys.readouterr().out
    assert "alpha: cannot pull diverged branch master -> origin/master (ahead 1, behind 1)" in output
    assert "beta: fast-forwarded master -> origin/master (ahead 0, behind 3)" in output
