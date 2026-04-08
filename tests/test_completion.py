from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace


def test_bash_completion_script_registers_query_handler() -> None:
    from dev.tasks.completion import bash_completion_script

    script = bash_completion_script("wabbit-dev")

    assert "complete -o bashdefault -o default -F _wabbit_dev_completion wabbit-dev" in script
    assert 'completion query bash "$COMP_CWORD"' in script


def test_zsh_completion_script_registers_compdef() -> None:
    from dev.tasks.completion import zsh_completion_script

    script = zsh_completion_script("wabbit-dev")

    assert "#compdef wabbit-dev" in script
    assert "compdef _wabbit_dev_completion wabbit-dev" in script
    assert 'completion query zsh $((CURRENT - 1))' in script


def test_completion_reply_lists_top_level_commands() -> None:
    from dev.tasks.completion import get_completion_reply

    reply = get_completion_reply(["wabbit-dev", ""], 1)

    assert "completion" in reply.candidates
    assert "doctor" in reply.candidates
    assert reply.allow_files is False


def test_completion_reply_lists_project_subcommands() -> None:
    from dev.tasks.completion import get_completion_reply

    reply = get_completion_reply(["wabbit-dev", "project", ""], 2)

    assert reply.candidates == ("list", "show", "deps", "repo")
    assert reply.allow_files is False


def test_completion_reply_suggests_project_and_repo_targets(monkeypatch) -> None:
    import dev.tasks.completion as completion_task

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", object())]),
        defined_repos=OrderedDict([("jeeves", object())]),
    )

    monkeypatch.setattr(completion_task, "load_config", lambda: config)

    reply = completion_task.get_completion_reply(["wabbit-dev", "build", ""], 2)

    assert reply.candidates == ("app-wabbit-dev", "jeeves")
    assert reply.allow_files is True


def test_completion_reply_suggests_check_targets_and_colon_forms(monkeypatch) -> None:
    import dev.tasks.completion as completion_task

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", object())]),
        defined_repos=OrderedDict([("jeeves", object())]),
    )

    monkeypatch.setattr(completion_task, "load_config", lambda: config)
    monkeypatch.setattr(completion_task, "list_check_names", lambda config=None: ["SpdxHeaderCheck"])

    reply = completion_task.get_completion_reply(["wabbit-dev", "check", ""], 2)

    assert reply.allow_files is True
    assert reply.candidates == (":root", "app-wabbit-dev", "jeeves", ":app-wabbit-dev", ":jeeves")


def test_completion_reply_suggests_check_names_after_target(monkeypatch) -> None:
    import dev.tasks.completion as completion_task

    monkeypatch.setattr(completion_task, "load_config", lambda: None)
    monkeypatch.setattr(completion_task, "list_check_names", lambda config=None: ["SpdxHeaderCheck", "TextQualityCheck"])

    reply = completion_task.get_completion_reply(["wabbit-dev", "check", "app-wabbit-dev", ""], 3)

    assert reply.allow_files is False
    assert reply.candidates == ("SpdxHeaderCheck", "TextQualityCheck")


def test_completion_reply_suggests_check_names_for_describe(monkeypatch) -> None:
    import dev.tasks.completion as completion_task

    monkeypatch.setattr(completion_task, "load_config", lambda: None)
    monkeypatch.setattr(completion_task, "list_check_names", lambda config=None: ["SpdxHeaderCheck"])

    reply = completion_task.get_completion_reply(["wabbit-dev", "check", "--describe", ""], 3)

    assert reply.allow_files is False
    assert reply.candidates == ("SpdxHeaderCheck",)


def test_completion_reply_suggests_push_targets_and_dot(monkeypatch) -> None:
    import dev.tasks.completion as completion_task

    config = SimpleNamespace(
        defined_projects=OrderedDict([("app-wabbit-dev", object())]),
        defined_repos=OrderedDict([("jeeves", object())]),
    )

    monkeypatch.setattr(completion_task, "load_config", lambda: config)

    reply = completion_task.get_completion_reply(["wabbit-dev", "push", ""], 2)

    assert reply.allow_files is True
    assert reply.candidates == (".", "app-wabbit-dev", "jeeves")
