from __future__ import annotations

import os
import shlex
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from git.cmd import Git

from dev.config import Config


def github_ssh_command(github_ssh_key: str | None) -> str | None:
    if github_ssh_key is None:
        return None
    key_text = github_ssh_key.strip()
    if not key_text:
        return None

    key_path = Path(key_text).expanduser()
    return f"ssh -i {shlex.quote(str(key_path))} -o IdentitiesOnly=yes"


def git_subprocess_env(config: Config, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    ssh_command = github_ssh_command(config.github_ssh_key)
    if ssh_command is not None:
        env["GIT_SSH_COMMAND"] = ssh_command
    return env


@contextmanager
def configured_git_ssh(git: Git, config: Config) -> Iterator[None]:
    ssh_command = github_ssh_command(config.github_ssh_key)
    if ssh_command is None:
        yield
        return

    with git.custom_environment(GIT_SSH_COMMAND=ssh_command):
        yield


__all__ = [
    "configured_git_ssh",
    "git_subprocess_env",
    "github_ssh_command",
]
