from __future__ import annotations

import subprocess
from pathlib import Path

from dev.service_actions import _configured_difftool_name


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
