from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def test_commit_runs_prod_setup_and_commits_once_per_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.commit as commit_module
    from dev.tasks.setup import RepoSetupMode

    alpha_path = tmp_path / "alpha"
    beta_path = tmp_path / "beta"
    alpha_path.mkdir(parents=True, exist_ok=True)
    beta_path.mkdir(parents=True, exist_ok=True)

    alpha_project = SimpleNamespace(name="alpha", path=alpha_path, quarantine=False)
    beta_project = SimpleNamespace(name="beta", path=beta_path, quarantine=False)
    config = SimpleNamespace(
        defined_projects={"alpha": alpha_project, "beta": beta_project},
        openai_key="test-openai-key",
    )

    setup_calls: list[tuple[str, bool, bool, bool]] = []
    commit_calls: list[tuple[str, bool, bool, str | None, str]] = []
    captured_modes: list[RepoSetupMode] = []

    class FakeRepo:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.working_tree_dir = str(tmp_path / "shared-repo")

        def close(self) -> None:
            return None

    def fake_load_config() -> object:
        return config

    def fake_toposort_projects(_projects: object, target_project: str | None = None) -> list[str]:
        assert target_project == "alpha"
        return ["alpha", "beta"]

    def fake_create_repo_setup_context(_config: object, mode: RepoSetupMode) -> object:
        captured_modes.append(mode)
        return object()

    def fake_setup_project(
        _ctx: object, project: object, interactive: bool, commit_changes: bool, allow_push: bool
    ) -> None:
        assert isinstance(project, SimpleNamespace)
        setup_calls.append((project.name, interactive, commit_changes, allow_push))

    def fake_commit_repo_changes(
        project: object,
        repo: object,
        openai_key: str | None,
        interactive: bool,
        add_files: bool,
    ) -> None:
        assert isinstance(project, SimpleNamespace)
        assert isinstance(repo, FakeRepo)
        commit_calls.append((project.name, interactive, add_files, openai_key, repo.working_tree_dir))

    monkeypatch.setattr(commit_module, "load_config", fake_load_config)
    monkeypatch.setattr(commit_module, "toposort_projects", fake_toposort_projects)
    monkeypatch.setattr(commit_module, "create_repo_setup_context", fake_create_repo_setup_context)
    monkeypatch.setattr(commit_module, "setup_project", fake_setup_project)
    monkeypatch.setattr(commit_module, "commit_repo_changes", fake_commit_repo_changes)
    monkeypatch.setattr(commit_module, "Repo", FakeRepo)

    commit_module.commit("alpha")

    assert captured_modes == [RepoSetupMode.PROD]
    assert setup_calls == [("alpha", False, False, False), ("beta", False, False, False)]
    assert commit_calls == [
        ("alpha", False, True, "test-openai-key", str(tmp_path / "shared-repo")),
    ]


def test_commit_requires_openai_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.commit as commit_module

    alpha_path = tmp_path / "alpha"
    alpha_path.mkdir(parents=True, exist_ok=True)
    alpha_project = SimpleNamespace(name="alpha", path=alpha_path, quarantine=False)
    config = SimpleNamespace(
        defined_projects={"alpha": alpha_project},
        openai_key=None,
    )

    errors: list[str] = []

    def fake_load_config() -> object:
        return config

    def capture_error(message: str) -> None:
        errors.append(message)

    monkeypatch.setattr(commit_module, "load_config", fake_load_config)
    monkeypatch.setattr(commit_module, "error", capture_error)

    commit_module.commit("alpha")

    assert errors == ["OpenAI key is required to generate commit messages."]


def test_commit_without_project_runs_all_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dev.tasks.commit as commit_module
    from dev.tasks.setup import RepoSetupMode

    alpha_path = tmp_path / "alpha"
    beta_path = tmp_path / "beta"
    alpha_path.mkdir(parents=True, exist_ok=True)
    beta_path.mkdir(parents=True, exist_ok=True)

    alpha_project = SimpleNamespace(name="alpha", path=alpha_path, quarantine=False)
    beta_project = SimpleNamespace(name="beta", path=beta_path, quarantine=False)
    config = SimpleNamespace(
        defined_projects={"alpha": alpha_project, "beta": beta_project},
        openai_key="test-openai-key",
    )

    setup_calls: list[tuple[str, bool, bool, bool]] = []
    commit_calls: list[tuple[str, bool, bool, str | None, str]] = []
    captured_targets: list[str | None] = []
    captured_modes: list[RepoSetupMode] = []

    class FakeRepo:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.working_tree_dir = str(path)

        def close(self) -> None:
            return None

    def fake_load_config() -> object:
        return config

    def fake_toposort_projects(_projects: object, target_project: str | None = None) -> list[str]:
        captured_targets.append(target_project)
        return ["alpha", "beta"]

    def fake_create_repo_setup_context(_config: object, mode: RepoSetupMode) -> object:
        captured_modes.append(mode)
        return object()

    def fake_setup_project(
        _ctx: object, project: object, interactive: bool, commit_changes: bool, allow_push: bool
    ) -> None:
        assert isinstance(project, SimpleNamespace)
        setup_calls.append((project.name, interactive, commit_changes, allow_push))

    def fake_commit_repo_changes(
        project: object,
        repo: object,
        openai_key: str | None,
        interactive: bool,
        add_files: bool,
    ) -> None:
        assert isinstance(project, SimpleNamespace)
        assert isinstance(repo, FakeRepo)
        commit_calls.append((project.name, interactive, add_files, openai_key, repo.working_tree_dir))

    monkeypatch.setattr(commit_module, "load_config", fake_load_config)
    monkeypatch.setattr(commit_module, "toposort_projects", fake_toposort_projects)
    monkeypatch.setattr(commit_module, "create_repo_setup_context", fake_create_repo_setup_context)
    monkeypatch.setattr(commit_module, "setup_project", fake_setup_project)
    monkeypatch.setattr(commit_module, "commit_repo_changes", fake_commit_repo_changes)
    monkeypatch.setattr(commit_module, "Repo", FakeRepo)

    commit_module.commit()

    assert captured_targets == [None]
    assert captured_modes == [RepoSetupMode.PROD]
    assert setup_calls == [("alpha", False, False, False), ("beta", False, False, False)]
    assert commit_calls == [
        ("alpha", False, True, "test-openai-key", str(alpha_path)),
        ("beta", False, True, "test-openai-key", str(beta_path)),
    ]
