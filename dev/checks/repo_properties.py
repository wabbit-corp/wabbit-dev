"""
Checks for repository-root metadata hygiene such as `.editorconfig`, GitHub
community files, and workflow presence.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from dev.check_fixers import rerun_setup_for_repo_root
from dev.checks.base import Issue, IssueType, RepoCheck, Severity
from dev.config import Project, find_workspace_root, load_config
from dev.repo_metadata import build_repo_metadata_plan

_CODEOWNER_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

E_MISSING_EDITORCONFIG = IssueType("E_MISSING_EDITORCONFIG", "Missing repository .editorconfig file.")
E_REPO_CODEOWNERS_UNCONFIGURED = IssueType(
    "E_REPO_CODEOWNERS_UNCONFIGURED",
    "No default code owners are configured in root.clj, so .github/CODEOWNERS cannot be generated.",
    severity=Severity.WARNING,
)
E_MISSING_CODEOWNERS = IssueType("E_MISSING_CODEOWNERS", "Missing .github/CODEOWNERS file.")
E_CODEOWNERS_INVALID_ENTRY = IssueType(
    "E_CODEOWNERS_INVALID_ENTRY",
    ".github/CODEOWNERS contains an invalid ownership rule: {entry}.",
)
E_CODEOWNERS_MISSING_DEFAULT_RULE = IssueType(
    "E_CODEOWNERS_MISSING_DEFAULT_RULE",
    ".github/CODEOWNERS does not define a default '*' ownership rule.",
)
E_MISSING_SECURITY_POLICY = IssueType("E_MISSING_SECURITY_POLICY", "Missing .github/SECURITY.md file.")
E_MISSING_PULL_REQUEST_TEMPLATE = IssueType(
    "E_MISSING_PULL_REQUEST_TEMPLATE",
    "Missing .github/pull_request_template.md file.",
)
E_MISSING_ISSUE_TEMPLATE = IssueType(
    "E_MISSING_ISSUE_TEMPLATE",
    "Missing {path} issue template file.",
)
E_MISSING_REPO_WORKFLOW = IssueType(
    "E_MISSING_REPO_WORKFLOW",
    "Repository should expose at least one CI workflow under .github/workflows/.",
    severity=Severity.WARNING,
)


def _is_valid_codeowner_owner(token: str) -> bool:
    if token.startswith("@"):
        return len(token) > 1
    return _CODEOWNER_EMAIL_RE.fullmatch(token) is not None


def _validate_codeowners_file(path: Path, *, fix: Callable[[], None] | None = None) -> list[Issue]:
    if not path.is_file():
        issue = E_MISSING_CODEOWNERS.at(path)
        if fix is not None:
            issue = issue.fixable(fix)
        return [issue]

    issues: list[Issue] = []
    has_default_rule = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.split()
        if len(parts) < 2:
            issue = E_CODEOWNERS_INVALID_ENTRY.make(entry=stripped).at(path)
            if fix is not None:
                issue = issue.fixable(fix)
            issues.append(issue)
            continue

        pattern, owners = parts[0], parts[1:]
        if pattern == "*":
            has_default_rule = True
        if not all(_is_valid_codeowner_owner(owner) for owner in owners):
            issue = E_CODEOWNERS_INVALID_ENTRY.make(entry=stripped).at(path)
            if fix is not None:
                issue = issue.fixable(fix)
            issues.append(issue)

    if not has_default_rule:
        issue = E_CODEOWNERS_MISSING_DEFAULT_RULE.at(path)
        if fix is not None:
            issue = issue.fixable(fix)
        issues.append(issue)
    return issues


class RepoMetadataHygieneCheck(RepoCheck):
    """
    Ensure Wabbit-managed repositories carry the generated repo metadata bundle:
    `.editorconfig`, GitHub community files, and at least one workflow when the
    repo is meant to publish artifacts or docs.
    """

    order = 80

    def check(self, path: Path, project: Project | None) -> list[Issue]:
        del project
        if not path.is_dir():
            return []
        if find_workspace_root(path) is None:
            return []

        config = load_config(path)
        plan = build_repo_metadata_plan(config, path)
        if plan is None:
            return []

        issues: list[Issue] = []
        repo_root = plan.repo_root

        def fix_repo_metadata() -> None:
            rerun_setup_for_repo_root(repo_root)

        if plan.requires_editorconfig and not (repo_root / ".editorconfig").is_file():
            issues.append(E_MISSING_EDITORCONFIG.at(repo_root).fixable(fix_repo_metadata))

        if not plan.requires_github_metadata:
            return issues

        github_root = repo_root / ".github"
        if plan.code_owners:
            issues.extend(_validate_codeowners_file(github_root / "CODEOWNERS", fix=fix_repo_metadata))
        else:
            issues.append(E_REPO_CODEOWNERS_UNCONFIGURED.at(repo_root))

        if not (github_root / "SECURITY.md").is_file():
            issues.append(E_MISSING_SECURITY_POLICY.at(github_root / "SECURITY.md").fixable(fix_repo_metadata))
        if not (github_root / "pull_request_template.md").is_file():
            issues.append(
                E_MISSING_PULL_REQUEST_TEMPLATE.at(github_root / "pull_request_template.md").fixable(fix_repo_metadata)
            )

        issue_template_root = github_root / "ISSUE_TEMPLATE"
        for expected_name in ("bug_report.yml", "feature_request.yml"):
            expected_path = issue_template_root / expected_name
            if not expected_path.is_file():
                issues.append(
                    E_MISSING_ISSUE_TEMPLATE.make(path=str(expected_path.relative_to(repo_root)))
                    .at(expected_path)
                    .fixable(fix_repo_metadata)
                )

        if plan.requires_ci_workflows:
            workflows_dir = github_root / "workflows"
            workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
            if not workflow_files:
                issues.append(E_MISSING_REPO_WORKFLOW.at(workflows_dir).fixable(fix_repo_metadata))

        return issues


__all__ = [
    "E_CODEOWNERS_INVALID_ENTRY",
    "E_CODEOWNERS_MISSING_DEFAULT_RULE",
    "E_MISSING_CODEOWNERS",
    "E_MISSING_EDITORCONFIG",
    "E_MISSING_ISSUE_TEMPLATE",
    "E_MISSING_PULL_REQUEST_TEMPLATE",
    "E_MISSING_REPO_WORKFLOW",
    "E_MISSING_SECURITY_POLICY",
    "E_REPO_CODEOWNERS_UNCONFIGURED",
    "RepoMetadataHygieneCheck",
]
