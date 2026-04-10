from __future__ import annotations

from mu.parser import parse


def test_github_ssh_command_expands_configured_key() -> None:
    from dev.git_env import github_ssh_command

    command = github_ssh_command("~/.ssh/id_example")

    assert command is not None
    assert command.startswith("ssh -i ")
    assert "/.ssh/id_example" in command
    assert "-o IdentitiesOnly=yes" in command


def test_git_subprocess_env_sets_git_ssh_command() -> None:
    from dev.config import Config
    from dev.git_env import git_subprocess_env

    config = Config(raw=parse("()"))
    config.github_ssh_key = "/tmp/id_example"

    env = git_subprocess_env(config, {"PATH": "/bin"})

    assert env["PATH"] == "/bin"
    assert env["GIT_SSH_COMMAND"] == "ssh -i /tmp/id_example -o IdentitiesOnly=yes"


def test_git_subprocess_env_leaves_existing_env_without_configured_key() -> None:
    from dev.config import Config
    from dev.git_env import git_subprocess_env

    config = Config(raw=parse("()"))

    env = git_subprocess_env(config, {"PATH": "/bin"})

    assert env == {"PATH": "/bin"}
