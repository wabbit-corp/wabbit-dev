from __future__ import annotations

import subprocess
from pathlib import Path

from dev.service_actions import _configured_difftool_name, open_repo_in_difftool


def test_configured_difftool_name_prefers_meld_over_git_config(monkeypatch) -> None:
    monkeypatch.setattr("dev.service_actions.shutil.which", lambda name: "/usr/bin/meld" if name == "meld" else None)

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="opendiff\n", stderr="")

    monkeypatch.setattr("dev.service_actions.subprocess.run", fake_run)

    tool_name = _configured_difftool_name(Path("/tmp/repo"))

    assert tool_name == "meld"


def test_configured_difftool_name_falls_back_to_git_config_then_opendiff(monkeypatch) -> None:
    monkeypatch.setattr("dev.service_actions.shutil.which", lambda name: None)

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="opendiff\n", stderr="")

    monkeypatch.setattr("dev.service_actions.subprocess.run", fake_run)

    tool_name = _configured_difftool_name(Path("/tmp/repo"))

    assert tool_name == "opendiff"


def test_open_repo_in_difftool_launches_meld_directly(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    launched: list[list[str]] = []

    class _FakeConfig:
        pass

    def fake_popen(command: list[str], **kwargs) -> subprocess.Popen[str]:
        launched.append(command)
        raise OSError("stop after capture")

    monkeypatch.setattr("dev.service_actions.load_config", lambda workspace_root: _FakeConfig())
    monkeypatch.setattr("dev.service_actions._configured_difftool_name", lambda repo_root: "meld")
    monkeypatch.setattr("dev.service_actions._create_meld_snapshot_dir", lambda repo_root, config: snapshot_dir)
    monkeypatch.setattr("dev.service_actions.git_subprocess_env", lambda config: None)
    monkeypatch.setattr("dev.service_actions.subprocess.Popen", fake_popen)

    result = open_repo_in_difftool(tmp_path, repo_root)

    assert launched == [["meld", str(snapshot_dir), str(repo_root)]]
    assert result.ok is False
    assert "failed to open difftool" in result.message
