from __future__ import annotations

import json
from pathlib import Path

from dev.commit_policy import (
    CommitPolicyReport,
    commit_diff_context,
    commit_message,
    commit_parent_count,
    commit_tags,
    commits_in_range,
    git_root,
    staged_diff_context,
    verify_commit_message,
)
from dev.config import find_workspace_root, load_config
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, success
from dev.repo_resolution import resolve_repo_target


def commit_verify(
    *,
    target: str | None = None,
    message_file: str | None = None,
    message: str | None = None,
    revision_range: str | None = None,
    staged: bool = False,
    json_output: bool = False,
    quiet: bool = False,
) -> int:
    try:
        repo_root = _resolve_repo_root(target)
        report = _verify(
            repo_root=repo_root,
            message_file=message_file,
            message=message,
            revision_range=revision_range,
            staged=staged,
        )
    except ValueError as ex:
        if json_output:
            print(json.dumps({"passed": False, "error": str(ex)}, indent=2))
        else:
            error(contextualize_failure(str(ex), ["commit", "verify"]))
        return 2

    if json_output:
        print(json.dumps(report.to_payload(), indent=2))
    elif not report.passed:
        _print_failure_report(report)
    elif not quiet:
        success(f"Commit policy passed for {len(report.results)} message(s).")

    return 0 if report.passed else 1


def _verify(
    *,
    repo_root: Path,
    message_file: str | None,
    message: str | None,
    revision_range: str | None,
    staged: bool,
) -> CommitPolicyReport:
    selected_modes = sum(1 for item in (message_file, message, revision_range) if item is not None)
    if selected_modes != 1:
        raise ValueError("Use exactly one of --message-file, --message, or --range.")

    if message_file is not None:
        path = Path(message_file).expanduser()
        if not path.is_file():
            raise ValueError(f"Commit message file does not exist: {path}")
        diff_context = staged_diff_context(repo_root) if staged else None
        return CommitPolicyReport(
            results=(
                verify_commit_message(
                    path.read_text(encoding="utf-8"),
                    source=str(path),
                    diff_context=diff_context,
                ),
            )
        )

    if message is not None:
        diff_context = staged_diff_context(repo_root) if staged else None
        return CommitPolicyReport(
            results=(
                verify_commit_message(
                    message,
                    source="--message",
                    diff_context=diff_context,
                ),
            )
        )

    assert revision_range is not None
    commits = commits_in_range(repo_root, revision_range)
    results = []
    for commit in commits:
        results.append(
            verify_commit_message(
                commit_message(repo_root, commit),
                source=revision_range,
                commit=commit,
                parent_count=commit_parent_count(repo_root, commit),
                tags=commit_tags(repo_root, commit),
                diff_context=commit_diff_context(repo_root, commit),
            )
        )
    return CommitPolicyReport(results=tuple(results))


def _resolve_repo_root(target: str | None) -> Path:
    if target is None:
        return git_root(Path.cwd())

    path = Path(target).expanduser()
    if path.exists():
        return git_root(path)

    if find_workspace_root() is None:
        raise ValueError(f"Repository target does not exist: {target}")

    config = load_config()
    resolved_target = resolve_repo_target(target, config=config)
    return git_root(resolved_target.path)


def _print_failure_report(report: CommitPolicyReport) -> None:
    error("Commit message policy failed.")
    for result in report.results:
        if result.passed:
            continue
        subject = result.subject or "<empty>"
        prefix = f"{result.commit[:12]} " if result.commit is not None else ""
        print(f"  {accent(prefix + subject, 'yellow')}")
        for finding in result.findings:
            print(f"    [{finding.code}] {finding.message}")
            print(f"    Fix: {finding.fix}")


__all__ = ["commit_verify"]
