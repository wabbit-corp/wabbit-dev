from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest


def test_security_scan_skips_missing_and_non_applicable_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.tasks.security_scan as security_task

    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")

    monkeypatch.setattr(security_task, "_load_config_if_available", lambda: None)
    monkeypatch.setattr(security_task, "_tool_path", lambda _executable: None)

    report = security_task.build_security_scan_report(
        [str(tmp_path)],
        tools=["gitleaks", "semgrep", "shellcheck", "pip-audit"],
    )

    statuses = {result.tool: result.status for result in report.results}
    reasons = {result.tool: result.reason for result in report.results}

    assert statuses == {
        "gitleaks": "skipped",
        "semgrep": "skipped",
        "shellcheck": "skipped",
        "pip-audit": "skipped",
    }
    assert reasons["gitleaks"] == "gitleaks is not installed or not on PATH"
    assert reasons["semgrep"] == "no source files found"
    assert reasons["shellcheck"] == "no shell scripts found"
    assert reasons["pip-audit"] == "no requirements*.txt files found"
    assert report.exit_code() == 0


def test_security_scan_runs_applicable_tools_and_reports_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.tasks.security_scan as security_task

    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (tmp_path / "script.sh").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")

    commands: list[tuple[str, ...]] = []

    def fake_tool_path(executable: str) -> str | None:
        return f"/tools/{executable}"

    def fake_run_command(
        command: Sequence[str],
        *,
        cwd: Path,
    ) -> security_task.ExternalCommandResult:
        del cwd
        command_tuple = tuple(command)
        commands.append(command_tuple)
        if command_tuple[0] == "/tools/bandit":
            return security_task.ExternalCommandResult(return_code=1, output="bandit finding")
        return security_task.ExternalCommandResult(return_code=0, output="")

    monkeypatch.setattr(security_task, "_load_config_if_available", lambda: None)
    monkeypatch.setattr(security_task, "_tool_path", fake_tool_path)
    monkeypatch.setattr(security_task, "_run_command", fake_run_command)

    report = security_task.build_security_scan_report(
        [str(tmp_path)],
        tools=["bandit", "shellcheck", "pip-audit"],
    )

    statuses = {result.tool: result.status for result in report.results}

    assert statuses == {
        "bandit": "findings",
        "shellcheck": "clean",
        "pip-audit": "clean",
    }
    assert report.exit_code() == 1
    assert commands[0][:3] == ("/tools/bandit", "-q", "-r")
    assert commands[1][0] == "/tools/shellcheck"
    assert str(tmp_path / "script.sh") in commands[1]
    assert commands[2][:3] == ("/tools/pip-audit", "--progress-spinner", "off")
    assert "-r" in commands[2]


def test_security_scan_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dev.tasks.security_scan as security_task

    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setattr(security_task, "_load_config_if_available", lambda: None)
    monkeypatch.setattr(security_task, "_tool_path", lambda executable: f"/tools/{executable}")
    monkeypatch.setattr(
        security_task,
        "_run_command",
        lambda command, *, cwd: security_task.ExternalCommandResult(return_code=0, output=""),
    )

    exit_code = security_task.security_scan([str(tmp_path)], tools=["bandit"], json_output=True)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requestedTargets"] == [str(tmp_path)]
    assert payload["selectedTools"] == ["bandit"]
    assert payload["summary"]["clean"] == 1
    assert payload["results"][0]["tool"] == "bandit"
    assert payload["results"][0]["status"] == "clean"


def test_security_scan_validates_tool_names() -> None:
    import dev.tasks.security_scan as security_task

    with pytest.raises(ValueError, match="Unknown security scan tool"):
        security_task.build_security_scan_report(["."], tools=["not-a-tool"])
