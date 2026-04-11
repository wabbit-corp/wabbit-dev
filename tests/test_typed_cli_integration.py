from __future__ import annotations

import argparse

import pytest


def _fail_argparse(
    self: argparse.ArgumentParser,
    args: list[str] | None = None,
    namespace: argparse.Namespace | None = None,
) -> argparse.Namespace:
    del self, args, namespace
    raise AssertionError("argparse should not handle typed-cli commands")


@pytest.mark.asyncio
async def test_docs_commands_bypass_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev import cli
    from dev.tasks import docs_check as docs_check_task
    from dev.tasks import doctor as doctor_task

    called: list[tuple[list[str], bool, bool]] = []

    def fake_docs_check(
        targets: list[str] | None = None,
        *,
        semantic: bool = False,
        json_output: bool = False,
    ) -> int:
        called.append((targets or [], semantic, json_output))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(docs_check_task, "docs_check", fake_docs_check)
    monkeypatch.setattr("sys.argv", ["dev.py", "docs", "check", "--semantic", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True, True)]


@pytest.mark.asyncio
async def test_root_help_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr("sys.argv", ["dev.py", "--help"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Wabbit development toolkit." in output
    assert "Usage: dev <subcommand>" in output


@pytest.mark.asyncio
async def test_bare_invocation_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr("sys.argv", ["dev.py"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Wabbit development toolkit." in output
    assert "Usage: dev <subcommand>" in output


@pytest.mark.asyncio
async def test_help_alias_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr("sys.argv", ["dev.py", "help"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Wabbit development toolkit." in output


@pytest.mark.asyncio
async def test_parent_help_alias_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr("sys.argv", ["dev.py", "project", "help"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Explore the projects defined in root.clj" in output


@pytest.mark.asyncio
async def test_release_parent_help_bypasses_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dev import cli

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr("sys.argv", ["dev.py", "release"])

    result = await cli.async_main()

    assert result == 0
    output = capsys.readouterr().out
    assert "Verify or package release assets for publishable projects." in output
    assert "verify" in output
    assert "bundle" in output


@pytest.mark.asyncio
async def test_slash_alias_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check_config as check_config_task
    from dev.tasks import doctor as doctor_task

    called: list[str] = []

    def fake_check_config() -> None:
        called.append("check")

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(check_config_task, "check_config", fake_check_config)
    monkeypatch.setattr("sys.argv", ["dev.py", "config/check"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["check"]


@pytest.mark.asyncio
async def test_where_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import where as where_task

    called: list[bool] = []

    def fake_show_where(*, json_output: bool = False) -> int:
        called.append(json_output)
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(where_task, "show_where", fake_show_where)
    monkeypatch.setattr("sys.argv", ["dev.py", "where", "--json"])

    result = await cli.async_main()

    assert result == 0
    assert called == [True]


@pytest.mark.asyncio
async def test_check_config_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check_config as check_config_task
    from dev.tasks import doctor as doctor_task

    called: list[str] = []

    def fake_check_config() -> None:
        called.append("check")

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(check_config_task, "check_config", fake_check_config)
    monkeypatch.setattr("sys.argv", ["dev.py", "check", "config"])

    result = await cli.async_main()

    assert result == 0
    assert called == ["check"]


@pytest.mark.asyncio
async def test_install_commands_bypass_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from dev import cli
    from dev.tasks import install as install_task

    app_called: list[str | None] = []
    completions_called: list[tuple[str, bool, bool, bool, bool, bool]] = []
    tools_called: list[tuple[list[str], bool, bool]] = []

    def fake_install_app(*, bin_dir: str | None = None) -> install_task.AppInstallResult:
        app_called.append(bin_dir)
        return install_task.AppInstallResult(
            install_dir=Path("/tmp/bin"),
            wabbit_dev_path=Path("/tmp/bin/wabbit-dev"),
            dev_path=Path("/tmp/bin/dev"),
            python_bin=Path("/tmp/python"),
            dev_py=Path("/tmp/dev.py"),
            install_dir_on_path=True,
        )

    def fake_install_completions(
        *,
        shell: str,
        update_rc: bool,
        dev_bash: str,
        wabbit_dev_bash: str,
        dev_zsh: str,
        wabbit_dev_zsh: str,
    ) -> install_task.CompletionInstallResult:
        completions_called.append(
            (
                shell,
                update_rc,
                "__complete" in dev_bash,
                "__complete" in wabbit_dev_bash,
                "__complete" in dev_zsh,
                "__complete" in wabbit_dev_zsh,
            )
        )
        return install_task.CompletionInstallResult(
            bash_paths=(),
            zsh_paths=(),
            bashrc_path=None,
            zshrc_path=None,
            updated_bashrc=False,
            updated_zshrc=False,
        )

    def fake_install_tools(
        tools: list[str] | None = None,
        *,
        force: bool = False,
        json_output: bool = False,
    ) -> install_task.ToolsInstallResult:
        tools_called.append((tools or [], force, json_output))
        return install_task.ToolsInstallResult(
            root=Path("/tmp/.tools"),
            bin_dir=Path("/tmp/.tools/bin"),
            results=(
                install_task.ToolInstallResult(
                    name="gitleaks",
                    status="installed",
                    executable=Path("/tmp/.tools/bin/gitleaks"),
                    install_path=Path("/tmp/.tools/gitleaks"),
                    version="v1",
                    verification="sha256",
                    details="ok",
                ),
            ),
        )

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(install_task, "install_app", fake_install_app)
    monkeypatch.setattr(install_task, "install_completions", fake_install_completions)
    monkeypatch.setattr(install_task, "install_tools", fake_install_tools)

    monkeypatch.setattr("sys.argv", ["dev.py", "install", "app", "--bin-dir", "/tmp/custom-bin"])
    app_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "install", "completions", "--shell", "zsh", "--no-rc"])
    completions_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "install", "tools", "--tool", "gitleaks", "--force", "--json"])
    tools_result = await cli.async_main()

    assert app_result == 0
    assert completions_result == 0
    assert tools_result == 0
    assert app_called == ["/tmp/custom-bin"]
    assert completions_called == [("zsh", False, True, True, True, True)]
    assert tools_called == [(["gitleaks"], True, True)]


@pytest.mark.asyncio
async def test_project_show_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import project_list as project_list_task

    called: list[tuple[list[str], bool]] = []

    def fake_show_projects(project_targets: list[str], *, json_output: bool = False) -> None:
        called.append((project_targets, json_output))

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(project_list_task, "show_projects", fake_show_projects)
    monkeypatch.setattr("sys.argv", ["dev.py", "project", "show", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True)]


@pytest.mark.asyncio
async def test_project_versions_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import project_versions as project_versions_task

    called: list[tuple[list[str], bool]] = []

    def fake_show_project_versions(project_targets: list[str], *, json_output: bool = False) -> int:
        called.append((project_targets, json_output))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(project_versions_task, "show_project_versions", fake_show_project_versions)
    monkeypatch.setattr("sys.argv", ["dev.py", "project", "versions", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["app-wabbit-dev"], True)]


@pytest.mark.asyncio
async def test_doctor_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from dev import cli
    from dev.tasks import doctor as doctor_task

    called: list[tuple[bool, Sequence[str] | None, Sequence[str] | None]] = []

    def fake_doctor(
        *,
        json_output: bool = False,
        only: Sequence[str] | None = None,
        targets: Sequence[str] | None = None,
    ) -> int:
        called.append((json_output, only, targets))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "doctor", fake_doctor)
    monkeypatch.setattr(
        "sys.argv",
        ["dev.py", "doctor", "--only", "publish", "--only", "config", "--json", "app-wabbit-dev"],
    )

    result = await cli.async_main()

    assert result == 0
    assert called == [(True, ["publish", "config"], ["app-wabbit-dev"])]


@pytest.mark.asyncio
async def test_setup_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import setup as setup_task
    from dev.tasks.setup_common import RepoSetupMode

    called: list[tuple[RepoSetupMode, list[str] | None, bool]] = []

    def fake_setup(
        mode: RepoSetupMode,
        *,
        interactive: bool = True,
        project: str | None = None,
        projects: list[str] | None = None,
        json_output: bool = False,
    ) -> int:
        del interactive, project
        called.append((mode, projects, json_output))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(setup_task, "setup", fake_setup)
    monkeypatch.setattr("sys.argv", ["dev.py", "setup", "--local", "--json", "app-wabbit-dev"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(RepoSetupMode.LOCAL, ["app-wabbit-dev"], True)]


@pytest.mark.asyncio
async def test_dep_graph_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from dev import cli
    from dev.tasks import dep_graph as dep_graph_task
    from dev.tasks import doctor as doctor_task

    called: list[tuple[Sequence[str] | None, bool]] = []

    def fake_get_project_dependencies(
        *,
        focus_project_names: Sequence[str] | None = None,
        include_artifacts: bool = False,
        output_filename: str = "dependency_graph",
        graph_title: str | None = None,
    ) -> None:
        del output_filename, graph_title
        called.append((focus_project_names, include_artifacts))

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(dep_graph_task, "get_project_dependencies", fake_get_project_dependencies)
    monkeypatch.setattr("sys.argv", ["dev.py", "dep", "graph", "--artifacts", "jeeves"])

    result = await cli.async_main()

    assert result == 0
    assert called == [(["jeeves"], True)]


@pytest.mark.asyncio
async def test_security_scan_bypasses_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import security_scan as security_task

    called: list[tuple[Sequence[str] | None, Sequence[str] | None, bool]] = []

    def fake_security_scan(
        targets: Sequence[str] | None = None,
        *,
        tools: Sequence[str] | None = None,
        json_output: bool = False,
    ) -> int:
        called.append((targets, tools, json_output))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(security_task, "security_scan", fake_security_scan)
    monkeypatch.setattr(
        "sys.argv",
        ["dev.py", "security", "scan", "--tool", "gitleaks", "--tool", "shellcheck", "--json", "jeeves"],
    )

    result = await cli.async_main()

    assert result == 0
    assert called == [(["jeeves"], ["gitleaks", "shellcheck"], True)]


@pytest.mark.asyncio
async def test_build_status_and_push_bypass_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import build as build_task
    from dev.tasks import doctor as doctor_task
    from dev.tasks import push as push_task
    from dev.tasks import status as status_task

    build_called: list[tuple[list[str] | None, bool]] = []
    status_called: list[tuple[list[str] | None, bool]] = []
    push_called: list[tuple[list[str] | None, bool]] = []

    def fake_build(projects: str | list[str] | None = None, *, json_output: bool = False) -> int:
        match projects:
            case str():
                raise AssertionError("typed CLI should pass repeated targets as a list")
            case _:
                pass
        build_called.append((projects, json_output))
        return 0

    def fake_status(targets: str | list[str] | None, *, json_output: bool = False) -> int:
        match targets:
            case str():
                raise AssertionError("typed CLI should pass repeated targets as a list")
            case _:
                pass
        status_called.append((targets, json_output))
        return 0

    def fake_push(targets: str | list[str] | None = None, *, dry_run: bool = False) -> int:
        match targets:
            case str():
                raise AssertionError("typed CLI should pass repeated targets as a list")
            case _:
                pass
        push_called.append((targets, dry_run))
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(build_task, "build", fake_build)
    monkeypatch.setattr(status_task, "status", fake_status)
    monkeypatch.setattr(push_task, "push", fake_push)

    monkeypatch.setattr("sys.argv", ["dev.py", "build", "--json", "app-wabbit-dev"])
    build_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "status", "--json", "app-wabbit-dev"])
    status_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "push", "--dry-run", "app-wabbit-dev"])
    push_result = await cli.async_main()

    assert build_result == 0
    assert status_result == 0
    assert push_result == 0
    assert build_called == [(["app-wabbit-dev"], True)]
    assert status_called == [(["app-wabbit-dev"], True)]
    assert push_called == [(["app-wabbit-dev"], True)]


@pytest.mark.asyncio
async def test_llmcopy_duplicates_and_contributors_bypass_argparse_with_typed_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev import cli
    from dev.tasks import contributors_audit as contributors_task
    from dev.tasks import doctor as doctor_task
    from dev.tasks import duplicates as duplicates_task
    from dev.tasks import llmcopy as llmcopy_task

    llmcopy_called: list[list[str]] = []
    duplicates_called: list[tuple[list[str], list[str], list[str], int, bool, bool, bool]] = []
    contributors_called: list[str] = []

    def fake_llmcopy(paths: list[str]) -> None:
        llmcopy_called.append(paths)

    def fake_check_for_duplicates(
        paths: list[str],
        exclude_filters: list[str],
        include_filters: list[str],
        min_size: int,
        no_default_excludes: bool,
        include_zip_contents: bool = False,
        include_weak_encrypted_zip: bool = False,
    ) -> None:
        duplicates_called.append(
            (
                paths,
                exclude_filters,
                include_filters,
                min_size,
                no_default_excludes,
                include_zip_contents,
                include_weak_encrypted_zip,
            )
        )

    def fake_audit_contributors() -> int:
        contributors_called.append("audit")
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(llmcopy_task, "llmcopy", fake_llmcopy)
    monkeypatch.setattr(duplicates_task, "check_for_duplicates", fake_check_for_duplicates)
    monkeypatch.setattr(contributors_task, "audit_contributors", fake_audit_contributors)

    monkeypatch.setattr("sys.argv", ["dev.py", "llmcopy", "README.md", "docs"])
    llmcopy_result = await cli.async_main()

    monkeypatch.setattr(
        "sys.argv",
        [
            "dev.py",
            "duplicates",
            ".",
            "--exclude",
            "*.png",
            "*.jpg",
            "--filter",
            "*.kt",
            "--size",
            "4096",
            "--no-default-excludes",
            "--zip-contents",
            "--weak-encrypted-zip",
        ],
    )
    duplicates_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "contributors", "audit"])
    contributors_result = await cli.async_main()

    assert llmcopy_result == 0
    assert duplicates_result == 0
    assert contributors_result == 0
    assert llmcopy_called == [["README.md", "docs"]]
    assert duplicates_called == [(["."], ["*.png", "*.jpg"], ["*.kt"], 4096, True, True, True)]
    assert contributors_called == ["audit"]


@pytest.mark.asyncio
async def test_publish_and_jitpack_bypass_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from dev import cli
    from dev.tasks import doctor as doctor_task
    from dev.tasks import jitpack as jitpack_task
    from dev.tasks import publish as publish_task

    publish_called: list[tuple[Sequence[str] | None, bool]] = []
    jitpack_called: list[tuple[str, str, str | None]] = []

    async def fake_publish_main(projects: str | list[str] | None = None, *, dry_run: bool = False) -> int:
        match projects:
            case str():
                raise AssertionError("typed CLI should pass repeated targets as a list")
            case _:
                pass
        publish_called.append((projects, dry_run))
        return 0

    async def fake_get_jitpack_info(group: str, artifact: str, target_version: str | None) -> None:
        jitpack_called.append((group, artifact, target_version))

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(publish_task, "publish_main", fake_publish_main)
    monkeypatch.setattr(jitpack_task, "get_jitpack_info", fake_get_jitpack_info)

    monkeypatch.setattr("sys.argv", ["dev.py", "publish", "--dry-run", "app-wabbit-dev"])
    publish_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "jitpack", "info", "wabbit-corp", "kotlin-base58", "0.1.0"])
    jitpack_result = await cli.async_main()

    assert publish_result == 0
    assert jitpack_result == 0
    assert publish_called == [(["app-wabbit-dev"], True)]
    assert jitpack_called == [("wabbit-corp", "kotlin-base58", "0.1.0")]


@pytest.mark.asyncio
async def test_check_shortcuts_bypass_argparse_with_typed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from dev import cli
    from dev.tasks import check as check_task
    from dev.tasks import doctor as doctor_task
    from dev.tasks import spdx_headers as spdx_task

    check_called: list[tuple[str | None, list[str] | None, bool, list[str]]] = []
    list_called: list[bool] = []
    show_called: list[tuple[str, bool]] = []
    spdx_called: list[tuple[str | None, bool]] = []
    secrets_called: list[str | None] = []

    def fake_check_main(
        project_or_dir_or_file: str | None,
        enabled_checks: list[str] | None = None,
        fix: bool = False,
        *,
        bundles: list[str] | None = None,
    ) -> int:
        check_called.append((project_or_dir_or_file, enabled_checks, fix, bundles or []))
        return 0

    def fake_list_checks(*, json_output: bool = False) -> int:
        list_called.append(json_output)
        return 0

    def fake_show_check(check_name: str, *, json_output: bool = False) -> int:
        show_called.append((check_name, json_output))
        return 0

    def fake_spdx_headers(project_or_dir_or_file: str | None = None, fix: bool = False) -> int:
        spdx_called.append((project_or_dir_or_file, fix))
        return 0

    def fake_secrets_scan(project_or_dir_or_file: str | None = None, fix: bool = False) -> int:
        del fix
        secrets_called.append(project_or_dir_or_file)
        return 0

    monkeypatch.setattr(cli.SuggestingArgumentParser, "parse_args", _fail_argparse)
    monkeypatch.setattr(doctor_task, "preflight_for_command", lambda *args, **kwargs: True)
    monkeypatch.setattr(check_task, "check_main", fake_check_main)
    monkeypatch.setattr(check_task, "list_checks", fake_list_checks)
    monkeypatch.setattr(check_task, "show_check", fake_show_check)
    monkeypatch.setattr(check_task, "secrets_scan", fake_secrets_scan)
    monkeypatch.setattr(spdx_task, "spdx_headers", fake_spdx_headers)

    monkeypatch.setattr("sys.argv", ["dev.py", "check", ".", "spdx-header", "--fix"])
    check_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "check", "list", "--json"])
    list_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "check", "show", "spdx-header", "--json"])
    show_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "spdx", "headers", "--fix", "."])
    spdx_result = await cli.async_main()

    monkeypatch.setattr("sys.argv", ["dev.py", "secrets", "scan", "."])
    secrets_result = await cli.async_main()

    assert check_result == 0
    assert list_result == 0
    assert show_result == 0
    assert spdx_result == 0
    assert secrets_result == 0
    assert check_called == [(".", ["spdx-header"], True, [])]
    assert list_called == [True]
    assert show_called == [("spdx-header", True)]
    assert spdx_called == [(".", True)]
    assert secrets_called == ["."]
