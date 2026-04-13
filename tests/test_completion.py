from __future__ import annotations

import asyncio
from collections import OrderedDict
from types import SimpleNamespace


def _run_typed_completion(words: list[str], cword: int, capsys) -> tuple[str, ...]:
    from dev.typed_cli import maybe_run_typed_cli

    exit_code = asyncio.run(maybe_run_typed_cli(["__complete", str(cword), "--", *words], prog="dev"))
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    return tuple(line.split("\t", 1)[0] for line in captured.out.splitlines() if line)


def _run_typed_command(args: list[str], capsys) -> str:
    from dev.typed_cli import maybe_run_typed_cli

    exit_code = asyncio.run(maybe_run_typed_cli(args, prog="dev"))
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    return captured.out


def test_bash_completion_script_uses_typed_hidden_protocol(capsys) -> None:
    script = _run_typed_command(["completion", "bash"], capsys)

    assert "__complete \"$COMP_CWORD\"" in script
    assert "complete -o bashdefault -o default -F _dev_completion 'dev'" in script
    assert "completion query" not in script


def test_zsh_completion_script_uses_typed_hidden_protocol(capsys) -> None:
    script = _run_typed_command(["completion", "zsh"], capsys)

    assert "#compdef dev" in script
    assert "compdef _dev_completion 'dev'" in script
    assert "__complete $((CURRENT - 1))" in script
    assert "completion query" not in script


def test_completion_lists_top_level_commands(capsys) -> None:
    candidates = _run_typed_completion(["dev", ""], 1, capsys)

    assert "completion" in candidates
    assert "config" in candidates
    assert "install" in candidates
    assert "doctor" in candidates
    assert "verify" in candidates
    assert "backup" in candidates
    assert "docs" not in candidates
    assert "release" not in candidates
    assert "security" not in candidates


def test_completion_lists_backup_subcommands(capsys) -> None:
    candidates = _run_typed_completion(["dev", "backup", ""], 2, capsys)

    assert "push" in candidates
    assert "restore" in candidates


def test_completion_lists_project_subcommands(capsys) -> None:
    candidates = _run_typed_completion(["dev", "project", ""], 2, capsys)

    assert "list" in candidates
    assert "show" in candidates
    assert "deps" in candidates
    assert "repo" in candidates
    assert "targets" in candidates
    assert "versions" in candidates


def test_completion_lists_verify_subcommands(capsys) -> None:
    candidates = _run_typed_completion(["dev", "verify", ""], 2, capsys)

    assert "docs" in candidates
    assert "release" in candidates
    assert "security" in candidates
    assert "list" in candidates


def test_completion_lists_install_subcommands_and_tools(capsys) -> None:
    candidates = _run_typed_completion(["dev", "install", ""], 2, capsys)

    assert "app" in candidates
    assert "completions" in candidates
    assert "hooks" in candidates
    assert "tools" in candidates

    tool_candidates = _run_typed_completion(["dev", "install", "tools", "--tool", ""], 4, capsys)

    assert "gitleaks" in tool_candidates
    assert "ktfmt" in tool_candidates
    assert "ruff" in tool_candidates
    assert "clang-format" in tool_candidates
    assert "purs-tidy" in tool_candidates
    assert "csharpier" in tool_candidates


def test_completion_lists_commit_subcommands(capsys) -> None:
    candidates = _run_typed_completion(["dev", "commit", ""], 2, capsys)

    assert "verify" in candidates


def test_completion_lists_verify_security_tools(capsys) -> None:
    tool_candidates = _run_typed_completion(["dev", "verify", "security", "--tool", ""], 4, capsys)

    assert "gitleaks" in tool_candidates
    assert "trufflehog" in tool_candidates
    assert "gradle-dependency-check" in tool_candidates


def test_completion_suggests_project_and_repo_targets(monkeypatch, capsys) -> None:
    import dev.typed_cli as typed_cli

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", SimpleNamespace())]),
        defined_repos=OrderedDict([("jeeves", SimpleNamespace())]),
    )

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: config)

    candidates = _run_typed_completion(["dev", "build", ""], 2, capsys)

    assert "app-wabbit-dev" in candidates
    assert "jeeves" in candidates


def test_completion_suggests_check_targets_and_colon_forms(monkeypatch, capsys) -> None:
    import dev.typed_cli as typed_cli

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", SimpleNamespace())]),
        defined_repos=OrderedDict([("jeeves", SimpleNamespace())]),
    )

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: config)

    candidates = _run_typed_completion(["dev", "check", ""], 2, capsys)

    assert "list" in candidates
    assert "show" in candidates
    assert "config" in candidates
    assert ":root" in candidates
    assert "app-wabbit-dev" in candidates
    assert "jeeves" in candidates
    assert ":app-wabbit-dev" in candidates
    assert ":jeeves" in candidates


def test_completion_suggests_check_names_after_target(monkeypatch, capsys) -> None:
    import dev.tasks.check as check_task
    import dev.typed_cli as typed_cli

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: None)
    monkeypatch.setattr(check_task, "list_check_selectors", lambda config=None: ["spdx-header", "text-quality"])

    candidates = _run_typed_completion(["dev", "check", "app-wabbit-dev", ""], 3, capsys)

    assert candidates == ("spdx-header", "text-quality")


def test_completion_suggests_check_names_for_show(monkeypatch, capsys) -> None:
    import dev.tasks.check as check_task
    import dev.typed_cli as typed_cli

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: None)
    monkeypatch.setattr(check_task, "list_check_selectors", lambda config=None: ["spdx-header"])

    candidates = _run_typed_completion(["dev", "check", "show", ""], 3, capsys)

    assert candidates == ("spdx-header",)


def test_completion_suggests_check_bundles(monkeypatch, capsys) -> None:
    import dev.tasks.check as check_task
    import dev.typed_cli as typed_cli

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: None)
    monkeypatch.setattr(check_task, "list_check_bundle_names", lambda: ["docs", "security"])

    candidates = _run_typed_completion(["dev", "check", "--bundle", ""], 3, capsys)

    assert candidates == ("docs", "security")


def test_completion_suggests_push_targets_and_dot(monkeypatch, capsys) -> None:
    import dev.typed_cli as typed_cli

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", SimpleNamespace())]),
        defined_repos=OrderedDict([("jeeves", SimpleNamespace())]),
    )

    monkeypatch.setattr(typed_cli, "_load_workspace_config", lambda: config)

    candidates = _run_typed_completion(["dev", "push", ""], 2, capsys)

    assert "." in candidates
    assert "app-wabbit-dev" in candidates
    assert "jeeves" in candidates


def test_completion_suggests_doctor_only_values(monkeypatch, capsys) -> None:
    import dev.tasks.doctor as doctor_task

    monkeypatch.setattr(doctor_task, "doctor_only_choices", lambda: ("build", "gradle", "publish"))

    candidates = _run_typed_completion(["dev", "doctor", "--only", ""], 3, capsys)

    assert candidates == ("build", "gradle", "publish")


def test_completion_query_compatibility_command_uses_typed_grammar(capsys) -> None:
    output = _run_typed_command(["completion", "query", "bash", "1", "dev", "do"], capsys)

    candidates = tuple(line.split("\t", 1)[0] for line in output.splitlines() if line)
    assert "doctor" in candidates
    assert "docs" not in candidates
