from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mu.parser import parse


def test_checkout_clones_missing_repo_using_https_when_no_ssh_key(tmp_path: Path, monkeypatch) -> None:
    import dev.tasks.checkout as checkout_task
    from dev.config import Config, RepoDefinition

    workspace_root = tmp_path / "ws"
    workspace_root.mkdir()
    config = Config(raw=parse("()"))
    config.defined_repos["alpha"] = RepoDefinition(
        repo_id="alpha",
        path=workspace_root / "alpha",
        github_repo="wabbit-corp/alpha",
        gradle_root_project_name=None,
        jvm_policy=None,
    )

    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text, env
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(checkout_task.subprocess, "run", fake_run)

    result = checkout_task.checkout_resolved_target(config, "alpha")

    assert result.status == "cloned"
    assert commands == [("git", "clone", "https://github.com/wabbit-corp/alpha.git", str(workspace_root / "alpha"))]


def test_checkout_clones_missing_repo_using_ssh_when_configured(tmp_path: Path, monkeypatch) -> None:
    import dev.tasks.checkout as checkout_task
    from dev.config import Config, RepoDefinition

    workspace_root = tmp_path / "ws"
    workspace_root.mkdir()
    config = Config(raw=parse("()"))
    config.github_ssh_key = "~/.ssh/id_example"
    config.defined_repos["alpha"] = RepoDefinition(
        repo_id="alpha",
        path=workspace_root / "alpha",
        github_repo="wabbit-corp/alpha",
        gradle_root_project_name=None,
        jvm_policy=None,
    )

    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text, env
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(checkout_task.subprocess, "run", fake_run)

    result = checkout_task.checkout_resolved_target(config, "alpha")

    assert result.status == "cloned"
    assert commands == [("git", "clone", "git@github.com:wabbit-corp/alpha.git", str(workspace_root / "alpha"))]


def test_checkout_skips_existing_git_repo(tmp_path: Path) -> None:
    import dev.tasks.checkout as checkout_task
    from dev.config import Config, RepoDefinition

    workspace_root = tmp_path / "ws"
    repo_root = workspace_root / "alpha"
    (repo_root / ".git").mkdir(parents=True)
    config = Config(raw=parse("()"))
    config.defined_repos["alpha"] = RepoDefinition(
        repo_id="alpha",
        path=repo_root,
        github_repo="wabbit-corp/alpha",
        gradle_root_project_name=None,
        jvm_policy=None,
    )

    result = checkout_task.checkout_resolved_target(config, "alpha")

    assert result.status == "skipped"
    assert result.details == "repository already exists locally"


def test_checkout_json_output_reports_results(tmp_path: Path, monkeypatch, capsys) -> None:
    import dev.tasks.checkout as checkout_task

    repo_target = type("Target", (), {"name": "alpha", "path": tmp_path / "alpha"})
    monkeypatch.setattr(checkout_task, "find_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(checkout_task, "load_config", lambda: object())
    monkeypatch.setattr(checkout_task, "inferred_repo_targets", lambda config, targets=None: ["alpha"])
    monkeypatch.setattr(checkout_task, "resolve_repo_targets", lambda targets, config=None: [repo_target])
    monkeypatch.setattr(
        checkout_task,
        "checkout_resolved_target",
        lambda _config, _target_name, dry_run=False: checkout_task.CheckoutResult(
            name="alpha",
            path=tmp_path / "alpha",
            github_repo="wabbit-corp/alpha",
            clone_url="https://github.com/wabbit-corp/alpha.git",
            status="would-clone" if dry_run else "cloned",
            details="would clone into /tmp/alpha" if dry_run else "cloned wabbit-corp/alpha",
        ),
    )

    result = checkout_task.checkout(None, dry_run=True, json_output=True)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == []
    assert payload["inferredTargets"] == ["alpha"]
    assert payload["repos"][0]["name"] == "alpha"
    assert payload["repos"][0]["status"] == "would-clone"
