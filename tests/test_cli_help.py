from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_root_help_includes_command_summaries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        await cli.async_main()

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "Wabbit development toolkit." in output
    assert "completion" in output
    assert "Generate shell completion scripts." in output
    assert "doctor" in output
    assert "Diagnose workspace, toolchain, and credential readiness." in output
    assert "where" in output
    assert "Show the workspace, repo, and project context inferred" in output
    assert "config" in output
    assert "Validate workspace configuration files." in output
    assert "project" in output
    assert "Inspect the configured project inventory." in output
    assert "check" in output
    assert "Run repository and source checks." in output
    assert "contributors" in output
    assert "secrets" in output
    assert "trufflehog" not in output
    assert "Audit git contributor identity mismatches across configured repos." not in output


@pytest.mark.asyncio
async def test_parent_command_without_subcommand_prints_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "dep"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Analyze the dependency metadata loaded from root.clj." in output
    assert "graph     Render an SVG graph of project dependencies." in output
    assert "updates   Check configured libraries for newer upstream versions." in output


@pytest.mark.asyncio
async def test_completion_parent_help_lists_shells(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "completion"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "bash" in output
    assert "zsh" in output
    assert "source <(dev.py completion bash)" in output


@pytest.mark.asyncio
async def test_project_parent_help_lists_new_subcommands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "project"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "list" in output
    assert "show" in output
    assert "deps" in output
    assert "repo" in output
    assert "targets" in output


@pytest.mark.asyncio
async def test_cli_config_check_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check_config as check_config_task

    called: list[str] = []

    def fake_check_config() -> None:
        called.append("called")

    monkeypatch.setattr(check_config_task, "check_config", fake_check_config)
    monkeypatch.setattr("sys.argv", ["dev.py", "config", "check"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["called"]


@pytest.mark.asyncio
async def test_cli_doctor_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task

    called: list[str] = []

    def fake_doctor(*, json_output: bool = False, only=None, targets=None) -> int:
        assert json_output is False
        assert only is None
        assert targets == []
        called.append("called")
        return 0

    monkeypatch.setattr(doctor_task, "doctor", fake_doctor)
    monkeypatch.setattr("sys.argv", ["dev.py", "doctor"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["called"]


@pytest.mark.asyncio
async def test_cli_where_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import where as where_task

    called: list[bool] = []

    def fake_show_where(*, json_output: bool = False) -> int:
        called.append(json_output)
        return 0

    monkeypatch.setattr(where_task, "show_where", fake_show_where)
    monkeypatch.setattr("sys.argv", ["dev.py", "where", "--json"])

    result = await cli.async_main()

    assert result == 0
    assert called == [True]


@pytest.mark.asyncio
async def test_cli_doctor_dispatches_only_and_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task

    called: list[tuple[list[str] | None, list[str] | None]] = []

    def fake_doctor(*, json_output: bool = False, only=None, targets=None) -> int:
        assert json_output is False
        called.append((only, targets))
        return 0

    monkeypatch.setattr(doctor_task, "doctor", fake_doctor)
    monkeypatch.setattr("sys.argv", ["dev.py", "doctor", "--only", "publish", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["publish"], ["app-wabbit-dev"])]


@pytest.mark.asyncio
async def test_cli_completion_bash_prints_script(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "completion", "bash"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "complete -o bashdefault" in output
    assert "completion query bash" in output


@pytest.mark.asyncio
async def test_cli_doctor_prints_next_steps(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task

    monkeypatch.setattr(doctor_task, "doctor", lambda *, json_output=False, only=None, targets=None: 0)
    monkeypatch.setattr("sys.argv", ["dev.py", "doctor"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Next useful commands:" in output
    assert "dev.py config check" in output


@pytest.mark.asyncio
async def test_cli_doctor_json_suppresses_next_steps(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task

    def fake_doctor(*, json_output: bool = False, only=None, targets=None) -> int:
        assert json_output is True
        print("{}")
        return 0

    monkeypatch.setattr(doctor_task, "doctor", fake_doctor)
    monkeypatch.setattr("sys.argv", ["dev.py", "doctor", "--json"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert output.strip() == "{}"


@pytest.mark.asyncio
async def test_cli_contributors_audit_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import contributors_audit as contributors_audit_task
    from dev.tasks import doctor as doctor_task

    called: list[str] = []

    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda command_path, prog, projects=None, dry_run=False: True)

    def fake_audit_contributors() -> int:
        called.append("called")
        return 0

    monkeypatch.setattr(contributors_audit_task, "audit_contributors", fake_audit_contributors)
    monkeypatch.setattr("sys.argv", ["dev.py", "contributors", "audit"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["called"]


@pytest.mark.asyncio
async def test_cli_secrets_scan_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check as check_task
    from dev.tasks import doctor as doctor_task

    called: list[str] = []

    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda command_path, prog, projects=None, dry_run=False: True)

    def fake_secrets_scan(target: str) -> int:
        called.append(target)
        return 0

    monkeypatch.setattr(check_task, "secrets_scan", fake_secrets_scan)
    monkeypatch.setattr("sys.argv", ["dev.py", "secrets", "scan", "."])

    result = await cli.async_main()

    assert result == 0
    assert called == ["."]


@pytest.mark.asyncio
async def test_unknown_command_suggests_similar_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "proje", "list"])

    with pytest.raises(SystemExit) as excinfo:
        await cli.async_main()

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice: 'proje'" in err
    assert "Did you mean 'project'?" in err


@pytest.mark.asyncio
async def test_removed_command_names_are_not_registered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "trufflehog"])

    with pytest.raises(SystemExit) as excinfo:
        await cli.async_main()

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice: 'trufflehog'" in err
