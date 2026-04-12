from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2
import pytest

import dev.tasks.setup as setup_task_module
from dev.config import DataProject, load_config
from dev.template_assets import repo_template_path

if TYPE_CHECKING:
    from dev.config import Config


def _patch_template_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_read_text_file(_path: str) -> str:
        return "TEXT\n"

    def fake_read_template(_path: str, *, strict: bool = False) -> jinja2.Template:
        del strict
        return jinja2.Template("")

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


def test_create_repo_setup_context_loads_legal_templates_strictly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_read_text_file(_path: str) -> str:
        return "TEXT\n"

    def fake_read_template(path: Path, *, strict: bool = False) -> jinja2.Template:
        calls.append((path, strict))
        return jinja2.Template("")

    monkeypatch.setattr("dev.io.read_text_file", fake_read_text_file)
    monkeypatch.setattr("dev.io.read_template", fake_read_template)

    github_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class DummyGithub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            github_calls.append((args, kwargs))

    monkeypatch.setattr("github.Github", DummyGithub)

    config = _load_repo_config()
    config.github_token = None
    setup_task_module.create_repo_setup_context(config, setup_task_module.RepoSetupMode.LOCAL)

    assert github_calls == []
    strict_paths = {path.as_posix() for path, strict in calls if strict}
    assert strict_paths == {
        repo_template_path("legal", "cla", "v1.0.0", "CLA.md").as_posix(),
        repo_template_path("legal", "cla", "v1.0.0", "CLA_EXPLANATIONS.md").as_posix(),
        repo_template_path("legal", "code-of-conduct", "v1.0.0", "CODE_OF_CONDUCT.md").as_posix(),
        repo_template_path("legal", "contributor-privacy", "v1.0.0", "CONTRIBUTOR_PRIVACY.md").as_posix(),
    }


def test_create_repo_setup_context_skips_github_inventory_in_local_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_template_io(monkeypatch)

    github_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class DummyGithub:
        def __init__(self, *args: object, **kwargs: object) -> None:
            github_calls.append((args, kwargs))

    monkeypatch.setattr("github.Github", DummyGithub)

    config = _load_repo_config()
    config.github_token = "present-token"
    setup_task_module.create_repo_setup_context(
        config,
        setup_task_module.RepoSetupMode.LOCAL,
        require_github_api=True,
    )

    assert github_calls == []


def test_create_repo_setup_context_skips_unused_legal_templates_for_plain_data_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_read_text_file(_path: str) -> str:
        return "TEXT\n"

    def fake_read_template(path: Path, *, strict: bool = False) -> jinja2.Template:
        calls.append((path, strict))
        return jinja2.Template("")

    monkeypatch.setattr("dev.io.read_text_file", fake_read_text_file)
    monkeypatch.setattr("dev.io.read_template", fake_read_template)

    config = _load_repo_config()
    data_project = next(
        project
        for project in config.defined_projects.values()
        if isinstance(project, DataProject) and not project.preserve_legal_files
    )

    setup_task_module.create_repo_setup_context(
        config,
        setup_task_module.RepoSetupMode.LOCAL,
        selected_projects=[data_project],
    )

    strict_paths = {path.as_posix() for path, strict in calls if strict}
    assert strict_paths == set()
