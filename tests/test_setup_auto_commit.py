from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from dev.generated_files import SETUP_GENERATED_MARKER


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=repo, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _managed_gradle_file_text(body: str) -> str:
    return f"// {SETUP_GENERATED_MARKER}\n//\n{body}"


def _demo_project(repo_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        name="demo",
        project_id="demo",
        path=repo_root,
        repo_root=repo_root,
        quarantine=False,
    )


def test_auto_commit_setup_only_commits_allowed_tracked_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "root.clj").write_text('(workspace "demo")\n', encoding="utf-8")
    (repo_root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "root.clj").write_text('(workspace "demo-updated")\n', encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text('plugins { id("java") }\n'),
        encoding="utf-8",
    )

    commit_calls: list[str] = []

    def fake_commit_repo_changes(
        project: SimpleNamespace,
        repo,
        openai_key: str | None = None,
        interactive: bool = True,
        add_files: bool = True,
    ) -> None:
        del openai_key, interactive, add_files
        commit_calls.append(project.name)
        repo.git.add(all=True)
        repo.index.commit("Refresh setup-managed files\n\nSemver Impact: NONE")

    monkeypatch.setattr(setup_module, "commit_repo_changes", fake_commit_repo_changes)

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        workspace_root=repo_root,
        openai_key="test-openai-key",
    )

    assert commit_calls == ["demo"]
    assert len(results) == 1
    assert results[0].status == "committed"
    assert set(results[0].changed_paths) == {"build.gradle.kts", "root.clj"}
    assert _git(repo_root, "status", "--short").strip() == ""


def test_auto_commit_setup_only_skips_when_untracked_files_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text('plugins { id("java") }\n'),
        encoding="utf-8",
    )
    (repo_root / "notes.txt").write_text("draft\n", encoding="utf-8")

    commit_calls: list[str] = []

    def fake_commit_repo_changes(
        project: SimpleNamespace,
        repo,
        openai_key: str | None = None,
        interactive: bool = True,
        add_files: bool = True,
    ) -> None:
        del project, repo, openai_key, interactive, add_files
        commit_calls.append("called")

    monkeypatch.setattr(setup_module, "commit_repo_changes", fake_commit_repo_changes)

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        workspace_root=repo_root,
        openai_key="test-openai-key",
    )

    assert commit_calls == []
    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has untracked files after setup."


def test_auto_commit_setup_only_skips_nonmanaged_tracked_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dev.tasks.setup as setup_module

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo_root / "build.gradle.kts").write_text(
        _managed_gradle_file_text("plugins {}\n"),
        encoding="utf-8",
    )
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "Initial commit\n\nSemver Impact: NONE")

    (repo_root / "README.md").write_text("# Demo\n\nUpdated.\n", encoding="utf-8")

    commit_calls: list[str] = []

    def fake_commit_repo_changes(
        project: SimpleNamespace,
        repo,
        openai_key: str | None = None,
        interactive: bool = True,
        add_files: bool = True,
    ) -> None:
        del project, repo, openai_key, interactive, add_files
        commit_calls.append("called")

    monkeypatch.setattr(setup_module, "commit_repo_changes", fake_commit_repo_changes)

    candidates = setup_module._collect_setup_auto_commit_candidates(
        [_demo_project(repo_root)],
        workspace_root=repo_root,
        include_workspace_root=False,
    )
    results = setup_module._auto_commit_setup_repos(
        candidates,
        workspace_root=repo_root,
        openai_key="test-openai-key",
    )

    assert commit_calls == []
    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].message == "Repo has changes outside the setup-only auto-commit scope."
    assert results[0].changed_paths == ("README.md",)
