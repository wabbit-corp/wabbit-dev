from __future__ import annotations

from pathlib import Path

import pytest

from dev.checks.repo_contributors import (
    E_GENERIC_CONTRIBUTOR_IDENTITY,
    E_INVALID_CONTRIBUTOR_EMAIL,
    E_PROHIBITED_CONTRIBUTOR_IDENTITY,
    RepoContributorIdentityCheck,
)
from dev.git_contributors import GitContributor


def test_repo_contributor_identity_check_reports_invalid_email(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".git").mkdir()

    monkeypatch.setattr(
        "dev.checks.repo_contributors.list_git_contributors",
        lambda path: {GitContributor("Alice", "alice-at-example.com"): 3},
    )

    issues = RepoContributorIdentityCheck().check(tmp_path, None)

    assert [issue.issue_type for issue in issues] == [E_INVALID_CONTRIBUTOR_EMAIL]
    assert issues[0].location is not None
    assert issues[0].location.path == tmp_path


def test_repo_contributor_identity_check_reports_generic_and_prohibited_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".git").mkdir()

    monkeypatch.setattr(
        "dev.checks.repo_contributors.list_git_contributors",
        lambda path: {
            GitContributor("Your Name", "you@example.com"): 2,
            GitContributor("root", "root@localhost"): 1,
        },
    )

    issues = RepoContributorIdentityCheck().check(tmp_path, None)

    issue_types = [issue.issue_type for issue in issues]
    assert issue_types.count(E_GENERIC_CONTRIBUTOR_IDENTITY) == 2
    assert issue_types.count(E_PROHIBITED_CONTRIBUTOR_IDENTITY) == 1
    assert issue_types.count(E_INVALID_CONTRIBUTOR_EMAIL) == 1


def test_repo_contributor_identity_check_ignores_non_git_directories(tmp_path: Path) -> None:
    assert RepoContributorIdentityCheck().check(tmp_path, None) == []
