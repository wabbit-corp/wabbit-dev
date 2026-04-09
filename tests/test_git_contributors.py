from __future__ import annotations

import subprocess
from pathlib import Path

from dev.git_contributors import GitContributor, get_git_user_email, get_git_user_name, list_git_contributors


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_git_repo(repo: Path) -> None:
    _run_git(repo, "init")
    _run_git(repo, "config", "user.name", "Alice Example")
    _run_git(repo, "config", "user.email", "alice@example.com")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "Initial commit")


def test_list_git_contributors_does_not_change_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    original_cwd = Path.cwd()

    contributors = list_git_contributors(repo)

    assert Path.cwd() == original_cwd
    assert contributors == {GitContributor("Alice Example", "alice@example.com"): 1}


def test_get_git_user_helpers_do_not_change_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    original_cwd = Path.cwd()

    assert get_git_user_name(repo) == "Alice Example"
    assert get_git_user_email(repo) == "alice@example.com"
    assert Path.cwd() == original_cwd
