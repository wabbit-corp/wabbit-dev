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
    assert "docs" in output
    assert "Validate project documentation quality." in output
    assert "where" in output
    assert "Show the workspace, repo, and project context inferred" in output
    assert "config" in output
    assert "Validate workspace configuration files." in output
    assert "release" in output
    assert "Verify release readiness for publishable projects." in output
    assert "project" in output
    assert "Inspect the configured project inventory." in output
    assert "check" in output
    assert "Run repository and source checks, or inspect the loaded" in output
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
    assert "updates" in output
    assert "pinned Python deps" in output


@pytest.mark.asyncio
async def test_release_parent_help_lists_verify(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "release"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "verify" in output
    assert "Verify publishable Python and Gradle projects" in output


@pytest.mark.asyncio
async def test_docs_parent_help_lists_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "docs"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "check" in output
    assert "snippets" in output
    assert "Check project documentation links, sections, snippets" in output
    assert "Check fenced documentation snippets" in output


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
    assert "source <(dev completion bash)" in output


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
async def test_cli_config_check_slash_alias_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check_config as check_config_task

    called: list[str] = []

    def fake_check_config() -> None:
        called.append("called")

    monkeypatch.setattr(check_config_task, "check_config", fake_check_config)
    monkeypatch.setattr("sys.argv", ["dev.py", "config/check"])

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
async def test_cli_release_verify_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import release_verify as release_verify_task

    called: list[tuple[list[str], bool]] = []

    def fake_release_verify(targets=None, *, json_output: bool = False) -> int:
        called.append((targets, json_output))
        return 0

    monkeypatch.setattr(release_verify_task, "release_verify", fake_release_verify)
    monkeypatch.setattr("sys.argv", ["dev.py", "release", "verify", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True)]


@pytest.mark.asyncio
async def test_cli_docs_check_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import docs_check as docs_check_task

    called: list[tuple[list[str], bool, bool]] = []

    def fake_docs_check(targets=None, *, semantic: bool = False, json_output: bool = False) -> int:
        called.append((targets, semantic, json_output))
        return 0

    monkeypatch.setattr(docs_check_task, "docs_check", fake_docs_check)
    monkeypatch.setattr("sys.argv", ["dev.py", "docs", "check", "--semantic", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True, True)]


@pytest.mark.asyncio
async def test_cli_docs_snippets_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import docs_check as docs_check_task

    called: list[tuple[list[str], bool, bool]] = []

    def fake_docs_snippets(
        targets=None,
        *,
        verify: bool = False,
        json_output: bool = False,
    ) -> int:
        called.append((targets, verify, json_output))
        return 0

    monkeypatch.setattr(docs_check_task, "docs_snippets", fake_docs_snippets)
    monkeypatch.setattr(
        "sys.argv",
        ["dev.py", "docs", "snippets", "--verify", "--json", "app-wabbit-dev"],
    )

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True, True)]


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
async def test_cli_check_describe_does_not_infer_target(monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.repo_resolution as repo_resolution
    from dev import cli
    from dev.tasks import check as check_task

    called: list[str] = []

    monkeypatch.setattr(cli, "_load_workspace_config", lambda: object())

    def fail_infer(*_args, **_kwargs):
        raise AssertionError("check describe should not infer a target")

    monkeypatch.setattr(repo_resolution, "inferred_project_targets", fail_infer)
    monkeypatch.setattr(check_task, "describe_check", lambda name, json_output=False: called.append(name) or 0)
    monkeypatch.setattr("sys.argv", ["dev.py", "check", "describe", "SpdxHeaderCheck"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["SpdxHeaderCheck"]


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
    assert "dev config check" in output


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
async def test_help_alias_prints_root_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "help"])

    with pytest.raises(SystemExit) as excinfo:
        await cli.async_main()

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "Wabbit development toolkit." in output


@pytest.mark.asyncio
async def test_parent_help_alias_prints_parent_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr("sys.argv", ["dev.py", "project", "help"])

    with pytest.raises(SystemExit) as excinfo:
        await cli.async_main()

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "Explore the projects defined in root.clj" in output


def test_print_failure_context_includes_rerun_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from argparse import Namespace

    from dev import cli

    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "apps" / "demo"
    nested.mkdir(parents=True, exist_ok=True)
    (workspace_root / "root.clj").write_text("()", encoding="utf-8")
    (workspace_root / "dev").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    cli._print_failure_context(
        "build",
        args=Namespace(
            targets=["demo"],
            json=False,
        ),
    )

    err = capsys.readouterr().err
    assert "Resolved context:" in err
    assert "workspace root:" in err
    assert "Retry from workspace root:" in err
    assert "dev build demo" in err


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
