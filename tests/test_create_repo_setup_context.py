from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import pytest

import dev.tasks.setup as setup_task_module
from dev.config import load_config

if TYPE_CHECKING:
    from dev.config import Config


def _patch_template_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_coc_file() -> str:
        return "CODE_OF_CONDUCT\n"

    def fake_read_text_file(_path: str) -> str:
        return "TEXT\n"

    def fake_read_template(_path: str) -> jinja2.Template:
        return jinja2.Template("")

    monkeypatch.setattr(setup_task_module, "get_coc_file", fake_get_coc_file)
    monkeypatch.setattr("dev.io.read_text_file", fake_read_text_file)
    monkeypatch.setattr("dev.io.read_template", fake_read_template)


def _load_repo_config() -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    candidate_roots = [repo_root, repo_root / "test"]

    for candidate in candidate_roots:
        if (candidate / "root.clj").is_file() and (candidate / "root.private.clj").is_file():
            cwd = os.getcwd()
            os.chdir(candidate)
            try:
                return load_config()
            finally:
                os.chdir(cwd)

    pytest.skip("No root.clj/root.private.clj fixture available for config-loading tests")


def test_create_repo_setup_context_without_token_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_template_io(monkeypatch)

    github_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class DummyGithub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            github_calls.append((args, kwargs))

    monkeypatch.setattr("github.Github", DummyGithub)

    config = _load_repo_config()
    config.github_token = None
    ctx = setup_task_module.create_repo_setup_context(config, setup_task_module.RepoSetupMode.LOCAL)

    assert ctx.is_github_api_available is False
    assert ctx.known_repo_names == []
    assert ctx.known_github_repos == {}
    assert github_calls == []


def test_create_repo_setup_context_handles_github_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_template_io(monkeypatch)

    from github.GithubException import GithubException

    class DummyGithub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def get_user(self) -> object:
            raise GithubException(status=401, data={"message": "bad token"})

    monkeypatch.setattr("github.Github", DummyGithub)

    config = _load_repo_config()
    config.github_token = "bad-token"
    ctx = setup_task_module.create_repo_setup_context(config, setup_task_module.RepoSetupMode.LOCAL)

    assert ctx.is_github_api_available is False
    assert ctx.known_repo_names == []
    assert ctx.known_github_repos == {}
