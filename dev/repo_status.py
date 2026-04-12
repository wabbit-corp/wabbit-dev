from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from dev.config import Config
from dev.repo_resolution import ResolvedRepoTarget, configured_repo_targets, resolve_repo_targets


@dataclass(frozen=True)
class RepoStatusRecord:
    name: str
    path: Path
    staged_changes: tuple[str, ...]
    unstaged_changes: tuple[str, ...]
    untracked_files: tuple[str, ...]
    oldest_dirty_timestamp: datetime | None = None
    error: str | None = None

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


def status_lists(repo: Repo) -> tuple[list[str], list[str], list[str]]:
    staged: list[str] = []
    unstaged: list[str] = []
    untracked = sorted(repo.untracked_files)

    porcelain = repo.git.status("--porcelain=1", "--untracked-files=all")
    for raw_line in porcelain.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip()
        if not path_text:
            continue
        if status == "??":
            continue
        if status[0] != " ":
            staged.append(path_text)
        if status[1] != " ":
            unstaged.append(path_text)

    return sorted(dict.fromkeys(staged)), sorted(dict.fromkeys(unstaged)), untracked


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
        is_dirty = repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=False)
        if is_dirty:
            staged_changes, unstaged_changes, untracked_files = status_lists(repo)
            oldest_dirty_timestamp = oldest_dirty_timestamp_for_paths(
                repo_root,
                [*staged_changes, *unstaged_changes, *untracked_files],
            )
        else:
            staged_changes = []
            unstaged_changes = []
            untracked_files = []
            oldest_dirty_timestamp = None
        return RepoStatusRecord(
            name=target.name,
            path=repo_root,
            staged_changes=tuple(staged_changes),
            unstaged_changes=tuple(unstaged_changes),
            untracked_files=tuple(untracked_files),
            oldest_dirty_timestamp=oldest_dirty_timestamp,
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
    "RepoStatusRecord",
    "collect_repo_status_record",
    "collect_repo_status_records",
    "oldest_dirty_timestamp_for_paths",
    "status_lists",
]
