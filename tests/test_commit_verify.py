from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=repo, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def test_commit_message_requires_semver_impact() -> None:
    from dev.commit_policy import verify_commit_message

    result = verify_commit_message("Update docs", source="test")

    assert not result.passed
    assert [finding.code for finding in result.findings] == ["E_MISSING_SEMVER_IMPACT"]
    assert "Add exactly one final line" in result.findings[0].fix


def test_commit_message_rejects_long_subject_and_trailing_period() -> None:
    from dev.commit_policy import verify_commit_message

    subject = "Update generated repository metadata and install hooks across every configured repository."
    result = verify_commit_message(f"{subject}\n\nSemver Impact: NONE", source="test")

    assert not result.passed
    assert [finding.code for finding in result.findings] == [
        "E_SUBJECT_TOO_LONG",
        "E_SUBJECT_TRAILING_PERIOD",
    ]


def test_commit_verify_staged_requires_changelog_for_version_change(tmp_path: Path) -> None:
    from dev.tasks.commit_verify import commit_verify

    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    _git(repo, "tag", "1.0.0")

    (repo / "pyproject.toml").write_text('[project]\nversion = "1.1.0"\n', encoding="utf-8")
    _git(repo, "add", "pyproject.toml")

    exit_code = commit_verify(
        target=str(repo),
        message="Bump version\n\nSemver Impact: MINOR",
        staged=True,
        quiet=True,
    )

    assert exit_code == 1


def test_commit_verify_range_checks_each_commit(tmp_path: Path) -> None:
    from dev.tasks.commit_verify import commit_verify

    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")
    (repo / "README.md").write_text("# Demo\n\nUpdated.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Update README.")

    exit_code = commit_verify(target=str(repo), revision_range="HEAD~1..HEAD", quiet=True)

    assert exit_code == 1
