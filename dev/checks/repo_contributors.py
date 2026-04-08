"""
Checks git contributor history for invalid or placeholder contributor identities.
"""

from __future__ import annotations

import re
from pathlib import Path

from dev.checks.base import Issue, IssueType, RepoCheck
from dev.config import Project
from dev.git_contributors import GitContributor, list_git_contributors

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_GENERIC_CONTRIBUTOR_NAMES = frozenset(
    {
        "admin",
        "root",
        "test",
        "unknown",
        "your name",
        "yourname",
    }
)
DEFAULT_GENERIC_CONTRIBUTOR_EMAILS = frozenset(
    {
        "admin@example.com",
        "name@example.com",
        "root@localhost",
        "test@example.com",
        "user@example.com",
        "you@example.com",
        "your@email.com",
    }
)
DEFAULT_PROHIBITED_CONTRIBUTOR_NAMES = frozenset(
    {
        "administrator",
        "root",
    }
)
DEFAULT_PROHIBITED_CONTRIBUTOR_EMAILS = frozenset(
    {
        "root@localhost",
    }
)
DEFAULT_PROHIBITED_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "invalid",
        "localhost",
        "localdomain",
    }
)

E_INVALID_CONTRIBUTOR_EMAIL = IssueType(
    "E_INVALID_CONTRIBUTOR_EMAIL",
    "Git contributor '{contributor}' has an invalid email address '{email}'.",
)
E_GENERIC_CONTRIBUTOR_IDENTITY = IssueType(
    "E_GENERIC_CONTRIBUTOR_IDENTITY",
    "Git contributor '{contributor}' uses placeholder or generic identity information.",
)
E_PROHIBITED_CONTRIBUTOR_IDENTITY = IssueType(
    "E_PROHIBITED_CONTRIBUTOR_IDENTITY",
    "Git contributor '{contributor}' uses a prohibited identity.",
)


def _email_domain(email: str) -> str | None:
    if "@" not in email:
        return None
    return email.rsplit("@", 1)[1].lower()


def _is_valid_email(email: str) -> bool:
    return EMAIL_RE.fullmatch(email) is not None


def _is_generic_contributor(
    contributor: GitContributor,
    generic_names: frozenset[str],
    generic_emails: frozenset[str],
    prohibited_domains: frozenset[str],
) -> bool:
    normalized_name = contributor.name.strip().lower()
    normalized_email = contributor.email.strip().lower()
    if normalized_name in generic_names or normalized_email in generic_emails:
        return True

    email_domain = _email_domain(normalized_email)
    return email_domain in prohibited_domains


def _is_prohibited_contributor(
    contributor: GitContributor,
    prohibited_names: frozenset[str],
    prohibited_emails: frozenset[str],
) -> bool:
    normalized_name = contributor.name.strip().lower()
    normalized_email = contributor.email.strip().lower()
    return normalized_name in prohibited_names or normalized_email in prohibited_emails


class RepoContributorIdentityCheck(RepoCheck):
    order = 85

    def __init__(
        self,
        generic_names: frozenset[str] = DEFAULT_GENERIC_CONTRIBUTOR_NAMES,
        generic_emails: frozenset[str] = DEFAULT_GENERIC_CONTRIBUTOR_EMAILS,
        prohibited_names: frozenset[str] = DEFAULT_PROHIBITED_CONTRIBUTOR_NAMES,
        prohibited_emails: frozenset[str] = DEFAULT_PROHIBITED_CONTRIBUTOR_EMAILS,
        prohibited_email_domains: frozenset[str] = DEFAULT_PROHIBITED_EMAIL_DOMAINS,
    ):
        self.generic_names = frozenset(name.lower() for name in generic_names)
        self.generic_emails = frozenset(email.lower() for email in generic_emails)
        self.prohibited_names = frozenset(name.lower() for name in prohibited_names)
        self.prohibited_emails = frozenset(email.lower() for email in prohibited_emails)
        self.prohibited_email_domains = frozenset(domain.lower() for domain in prohibited_email_domains)

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del project
        if not path.is_dir() or not (path / ".git").exists():
            return []

        try:
            contributors = list_git_contributors(path)
        except ValueError:
            return []

        issues: list[Issue] = []
        for contributor, commit_count in sorted(contributors.items(), key=lambda item: (-item[1], item[0])):
            if not _is_valid_email(contributor.email):
                issues.append(
                    E_INVALID_CONTRIBUTOR_EMAIL.make(
                        contributor=str(contributor),
                        name=contributor.name,
                        email=contributor.email,
                        commit_count=commit_count,
                    ).at(path)
                )

            if _is_generic_contributor(
                contributor,
                generic_names=self.generic_names,
                generic_emails=self.generic_emails,
                prohibited_domains=self.prohibited_email_domains,
            ):
                issues.append(
                    E_GENERIC_CONTRIBUTOR_IDENTITY.make(
                        contributor=str(contributor),
                        name=contributor.name,
                        email=contributor.email,
                        commit_count=commit_count,
                    ).at(path)
                )

            if _is_prohibited_contributor(
                contributor,
                prohibited_names=self.prohibited_names,
                prohibited_emails=self.prohibited_emails,
            ):
                issues.append(
                    E_PROHIBITED_CONTRIBUTOR_IDENTITY.make(
                        contributor=str(contributor),
                        name=contributor.name,
                        email=contributor.email,
                        commit_count=commit_count,
                    ).at(path)
                )

        return issues


__all__ = [
    "DEFAULT_GENERIC_CONTRIBUTOR_EMAILS",
    "DEFAULT_GENERIC_CONTRIBUTOR_NAMES",
    "DEFAULT_PROHIBITED_CONTRIBUTOR_EMAILS",
    "DEFAULT_PROHIBITED_CONTRIBUTOR_NAMES",
    "DEFAULT_PROHIBITED_EMAIL_DOMAINS",
    "E_GENERIC_CONTRIBUTOR_IDENTITY",
    "E_INVALID_CONTRIBUTOR_EMAIL",
    "E_PROHIBITED_CONTRIBUTOR_IDENTITY",
    "RepoContributorIdentityCheck",
]
