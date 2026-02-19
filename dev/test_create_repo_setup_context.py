from pathlib import Path
from types import SimpleNamespace
import sys

import jinja2


def _load_setup_module():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.tasks.setup as setup_module

    return setup_module


def _patch_template_io(monkeypatch, setup_module) -> None:
    monkeypatch.setattr(setup_module, "get_coc_file", lambda: "CODE_OF_CONDUCT\n")
    monkeypatch.setattr(setup_module.dev.io, "read_text_file", lambda _path: "TEXT\n")
    monkeypatch.setattr(
        setup_module.dev.io, "read_template", lambda _path: jinja2.Template("")
    )


def test_create_repo_setup_context_without_token_is_offline(monkeypatch) -> None:
    setup_module = _load_setup_module()
    _patch_template_io(monkeypatch, setup_module)

    github_calls: list[dict] = []

    class DummyGithub:
        def __init__(self, *args, **kwargs):
            github_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("github.Github", DummyGithub)

    config = SimpleNamespace(github_token=None)
    ctx = setup_module.create_repo_setup_context(
        config, setup_module.RepoSetupMode.LOCAL
    )

    assert ctx.is_github_api_available is False
    assert ctx.known_repo_names == []
    assert ctx.known_github_repos == {}
    assert github_calls == []


def test_create_repo_setup_context_handles_github_api_errors(monkeypatch) -> None:
    setup_module = _load_setup_module()
    _patch_template_io(monkeypatch, setup_module)

    from github.GithubException import GithubException

    class DummyGithub:
        def __init__(self, *args, **kwargs):
            pass

        def get_user(self):
            raise GithubException(status=401, data={"message": "bad token"})

    monkeypatch.setattr("github.Github", DummyGithub)

    config = SimpleNamespace(github_token="bad-token")
    ctx = setup_module.create_repo_setup_context(
        config, setup_module.RepoSetupMode.LOCAL
    )

    assert ctx.is_github_api_available is False
    assert ctx.known_repo_names == []
    assert ctx.known_github_repos == {}
