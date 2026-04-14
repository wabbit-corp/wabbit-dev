from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import subprocess

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from dev.config import Config
from dev.git_env import git_subprocess_env
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets, resolve_repo_targets


@dataclass(frozen=True)
class RepoTrackingState:
    branch_name: str | None = None
    upstream_name: str | None = None
    ahead_count: int | None = None
    behind_count: int | None = None


@dataclass(frozen=True)
class RepoStatusRecord:
    name: str
    path: Path
    staged_changes: tuple[str, ...]
    unstaged_changes: tuple[str, ...]
    untracked_files: tuple[str, ...]
    repo_started_at: datetime | None = None
    oldest_dirty_timestamp: datetime | None = None
    error: str | None = None
    tracking: RepoTrackingState | None = None
    tracking_refreshed_at: datetime | None = None

    @property
    def is_clean(self) -> bool:
        return not self.is_dirty

    @property
    def is_dirty(self) -> bool:
        return self.error is not None or bool(self.staged_changes or self.unstaged_changes or self.untracked_files)

    @property
    def staged_count(self) -> int:
        return len(self.staged_changes)

    @property
    def unstaged_count(self) -> int:
        return len(self.unstaged_changes)

    @property
    def untracked_count(self) -> int:
        return len(self.untracked_files)


@dataclass(frozen=True)
class _StatusSummary:
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    tracking: RepoTrackingState


def _parse_tracking_header(header: str) -> RepoTrackingState:
    metadata = header.removeprefix("## ").strip()
    if not metadata:
        return RepoTrackingState()

    branch_segment, separator, status_segment = metadata.partition(" [")
    branch_name: str | None = None
    upstream_name: str | None = None

    if branch_segment != "HEAD (no branch)":
        branch_text, upstream_separator, upstream_text = branch_segment.partition("...")
        branch_name = branch_text or None
        if upstream_separator:
            upstream_name = upstream_text or None

    ahead_count: int | None = None
    behind_count: int | None = None

    if separator and status_segment.endswith("]"):
        for status_part in status_segment[:-1].split(", "):
            direction, _, count_text = status_part.partition(" ")
            match direction:
                case "ahead":
                    try:
                        ahead_count = int(count_text)
                    except ValueError:
                        ahead_count = None
                case "behind":
                    try:
                        behind_count = int(count_text)
                    except ValueError:
                        behind_count = None
                case _:
                    continue

    return RepoTrackingState(
        branch_name=branch_name,
        upstream_name=upstream_name,
        ahead_count=ahead_count,
        behind_count=behind_count,
    )


def _parse_status_summary(porcelain: str) -> _StatusSummary:
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    tracking = RepoTrackingState()

    for raw_line in porcelain.splitlines():
        if not raw_line:
            continue
        if raw_line.startswith("## "):
            tracking = _parse_tracking_header(raw_line)
            continue
        status = raw_line[:2]
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip()
        if not path_text:
            continue
        if status == "??":
            untracked.append(path_text)
            continue
        if status[0] != " ":
            staged.append(path_text)
        if status[1] != " ":
            unstaged.append(path_text)

    return _StatusSummary(
        staged=tuple(sorted(dict.fromkeys(staged))),
        unstaged=tuple(sorted(dict.fromkeys(unstaged))),
        untracked=tuple(sorted(dict.fromkeys(untracked))),
        tracking=tracking,
    )


def status_lists(repo: Repo) -> tuple[list[str], list[str], list[str]]:
    summary = _parse_status_summary(repo.git.status("--branch", "--porcelain=1", "--untracked-files=all"))
    return list(summary.staged), list(summary.unstaged), list(summary.untracked)


def local_tracking_state(repo: Repo) -> RepoTrackingState:
    try:
        summary = _parse_status_summary(repo.git.status("--branch", "--porcelain=1", "--untracked-files=no"))
        return summary.tracking
    except GitCommandError:
        return RepoTrackingState()


def refresh_remote_tracking(
    target: ResolvedRepoTarget,
    *,
    config: Config,
    timeout_seconds: int = 20,
) -> bool:
    try:
        repo = Repo(target.path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return False

    try:
        remote_names = [remote.name for remote in repo.remotes]
    finally:
        repo.close()

    remote_name = "origin" if "origin" in remote_names else (remote_names[0] if remote_names else None)
    if remote_name is None:
        return False

    try:
        result = subprocess.run(
            ["git", "fetch", "--prune", "--quiet", remote_name],
            cwd=target.path,
            env=git_subprocess_env(config),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def oldest_dirty_timestamp_for_paths(repo_root: Path, relative_paths: Sequence[str]) -> datetime | None:
    oldest_mtime: float | None = None
    repo_root_resolved = repo_root.resolve()

    for relative_path in relative_paths:
        candidate = (repo_root_resolved / relative_path).resolve()
        try:
            candidate.relative_to(repo_root_resolved)
        except ValueError:
            continue
        try:
            stat_result = candidate.stat()
        except OSError:
            continue
        if oldest_mtime is None or stat_result.st_mtime < oldest_mtime:
            oldest_mtime = stat_result.st_mtime

    if oldest_mtime is None:
        return None
    return datetime.fromtimestamp(oldest_mtime, tz=UTC)


def collect_repo_status_record(target: ResolvedRepoTarget) -> RepoStatusRecord:
    path = target.path
    if not path.exists():
        return RepoStatusRecord(
            name=target.name,
            path=path.resolve(),
            staged_changes=(),
            unstaged_changes=(),
            untracked_files=(),
            error="Path does not exist.",
        )

    try:
        repo = Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return RepoStatusRecord(
            name=target.name,
            path=path.resolve(),
            staged_changes=(),
            unstaged_changes=(),
            untracked_files=(),
            error="Path is not a git repository.",
        )

    try:
        working_tree_dir = repo.working_tree_dir
        if working_tree_dir is None:
            return RepoStatusRecord(
                name=target.name,
                path=path.resolve(),
                staged_changes=(),
                unstaged_changes=(),
                untracked_files=(),
                error="Repository has no working tree.",
            )

        repo_root = Path(working_tree_dir).resolve()
        summary = _parse_status_summary(repo.git.status("--branch", "--porcelain=1", "--untracked-files=all"))
        staged_changes = list(summary.staged)
        unstaged_changes = list(summary.unstaged)
        untracked_files = list(summary.untracked)
        repo_started_at: datetime | None = None
        try:
            root_commit = next(repo.iter_commits(rev="HEAD", max_parents=0))
            repo_started_at = datetime.fromtimestamp(root_commit.committed_date, tz=UTC)
        except (StopIteration, GitCommandError, ValueError):
            try:
                repo_started_at = datetime.fromtimestamp(repo_root.stat().st_mtime, tz=UTC)
            except OSError:
                repo_started_at = None
        if staged_changes or unstaged_changes or untracked_files:
            oldest_dirty_timestamp = oldest_dirty_timestamp_for_paths(
                repo_root,
                [*staged_changes, *unstaged_changes, *untracked_files],
            )
        else:
            oldest_dirty_timestamp = None
        return RepoStatusRecord(
            name=target.name,
            path=repo_root,
            staged_changes=tuple(staged_changes),
            unstaged_changes=tuple(unstaged_changes),
            untracked_files=tuple(untracked_files),
            repo_started_at=repo_started_at,
            oldest_dirty_timestamp=oldest_dirty_timestamp,
            tracking=summary.tracking,
        )
    finally:
        repo.close()


def collect_repo_status_records(
    config: Config,
    *,
    targets: Sequence[str] | None = None,
) -> list[RepoStatusRecord]:
    resolved_targets = configured_repo_targets(config) if not targets else resolve_repo_targets(targets, config=config)
    return [collect_repo_status_record(target) for target in resolved_targets]


__all__ = [
    "RepoTrackingState",
    "RepoStatusRecord",
    "collect_repo_status_record",
    "collect_repo_status_records",
    "local_tracking_state",
    "oldest_dirty_timestamp_for_paths",
    "refresh_remote_tracking",
    "status_lists",
]
