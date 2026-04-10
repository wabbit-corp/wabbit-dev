from __future__ import annotations

from pathlib import Path

from dev.config import load_config, project_repo_root
from dev.git_contributors import GitContributor, list_git_contributors
from dev.messages import error, success, warning


def audit_contributors() -> int:
    config = load_config()

    if not config.default_git_user_name or not config.default_git_user_email:
        error("The expected default git identity is not configured.")
        error('Set `(git-user "Your Name" "you@example.com")` in root.private.clj or root.clj.')
        return 1

    expected = GitContributor(config.default_git_user_name, config.default_git_user_email)
    seen_repo_paths: set[Path] = set()
    mismatched = False
    scanned = 0

    for project in config.defined_projects.values():
        repo_root = project_repo_root(project)
        resolved_root = repo_root.resolve()
        if resolved_root in seen_repo_paths:
            continue
        seen_repo_paths.add(resolved_root)

        if not repo_root.is_dir():
            warning(f"Skipping {repo_root}: directory does not exist.")
            continue
        if not (repo_root / ".git").exists():
            warning(f"Skipping {repo_root}: not a git repository.")
            continue

        scanned += 1
        contributors = list_git_contributors(repo_root)
        unexpected = {
            contributor: commit_count for contributor, commit_count in contributors.items() if contributor != expected
        }
        if not unexpected:
            continue

        mismatched = True
        error(f"Unexpected contributors found in {repo_root}:")
        for contributor, commit_count in sorted(unexpected.items(), key=lambda item: item[1], reverse=True):
            print(f"  {contributor}: {commit_count} commits")

    if mismatched:
        return 1
    if scanned == 0:
        warning("No git repositories were found to audit.")
        return 0

    success(f"Contributor audit passed for {scanned} repository/repositories.")
    return 0


__all__ = ["audit_contributors"]
