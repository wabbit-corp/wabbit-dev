from __future__ import annotations

import json
import os
import signal
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from hashlib import sha1
from pathlib import Path
from typing import Literal

from dev.json_types import JSONObject
from dev.repo_status import RepoStatusRecord

type MonitorColor = Literal["green", "yellow", "red"]

STALE_DIRTY_AFTER = timedelta(hours=8)
MIN_REPO_CHECK_SPACING_SECONDS = 0.1


@dataclass(frozen=True)
class MonitorRepoState:
    name: str
    path: Path
    staged_count: int
    unstaged_count: int
    untracked_count: int
    error: str | None = None
    dirty_since: datetime | None = None

    @property
    def is_dirty(self) -> bool:
        return self.error is not None or (self.staged_count + self.unstaged_count + self.untracked_count) > 0

    def to_json(self) -> JSONObject:
        return {
            "name": self.name,
            "path": str(self.path),
            "stagedCount": self.staged_count,
            "unstagedCount": self.unstaged_count,
            "untrackedCount": self.untracked_count,
            "dirty": self.is_dirty,
            "dirtySince": self.dirty_since.isoformat() if self.dirty_since is not None else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class MonitorSnapshot:
    workspace_root: Path
    workspace_name: str
    checked_at: datetime
    total_repo_count: int
    dirty_repo_count: int
    stale_repo_count: int
    error_repo_count: int
    color: MonitorColor
    repos: tuple[MonitorRepoState, ...]

    def to_json(self) -> JSONObject:
        return {
            "workspaceRoot": str(self.workspace_root),
            "workspaceName": self.workspace_name,
            "checkedAt": self.checked_at.isoformat(),
            "totalRepoCount": self.total_repo_count,
            "dirtyRepoCount": self.dirty_repo_count,
            "staleRepoCount": self.stale_repo_count,
            "errorRepoCount": self.error_repo_count,
            "color": self.color,
            "repos": [repo.to_json() for repo in self.repos],
        }


@dataclass(frozen=True)
class ServicePaths:
    root: Path
    pid_file: Path
    state_file: Path
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class ServicePid:
    pid: int
    workspace_root: Path
    started_at: datetime
    interval_seconds: int

    def to_json(self) -> JSONObject:
        return {
            "pid": self.pid,
            "workspaceRoot": str(self.workspace_root),
            "startedAt": self.started_at.isoformat(),
            "intervalSeconds": self.interval_seconds,
        }


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _workspace_service_root(workspace_root: Path) -> Path:
    digest = sha1(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:12]
    workspace_name = workspace_root.resolve().name or "workspace"
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "dev"
        / "service"
        / f"{workspace_name}-{digest}"
    )


def service_paths_for_workspace(workspace_root: Path) -> ServicePaths:
    root = _workspace_service_root(workspace_root)
    return ServicePaths(
        root=root,
        pid_file=root / "monitor.pid.json",
        state_file=root / "monitor.state.json",
        stdout_log=root / "monitor.stdout.log",
        stderr_log=root / "monitor.stderr.log",
    )


def ensure_service_dir(paths: ServicePaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)


def write_service_pid(paths: ServicePaths, pid_info: ServicePid) -> None:
    ensure_service_dir(paths)
    paths.pid_file.write_text(json.dumps(pid_info.to_json(), indent=2) + "\n", encoding="utf-8")


def load_service_pid(paths: ServicePaths) -> ServicePid | None:
    if not paths.pid_file.is_file():
        return None
    raw = json.loads(paths.pid_file.read_text(encoding="utf-8"))
    match raw:
        case {
            "pid": int(pid),
            "workspaceRoot": str(workspace_root),
            "startedAt": str(started_at),
            "intervalSeconds": int(interval_seconds),
        }:
            return ServicePid(
                pid=pid,
                workspace_root=Path(workspace_root),
                started_at=datetime.fromisoformat(started_at),
                interval_seconds=interval_seconds,
            )
        case _:
            return None


def remove_service_pid(paths: ServicePaths) -> None:
    if paths.pid_file.exists():
        paths.pid_file.unlink()


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cleanup_stale_service_pid(paths: ServicePaths) -> None:
    pid_info = load_service_pid(paths)
    if pid_info is None:
        return
    if not process_is_alive(pid_info.pid):
        remove_service_pid(paths)


def terminate_process(pid: int) -> None:
    os.kill(pid, signal.SIGTERM)


def write_monitor_snapshot(paths: ServicePaths, snapshot: MonitorSnapshot) -> None:
    ensure_service_dir(paths)
    paths.state_file.write_text(json.dumps(snapshot.to_json(), indent=2) + "\n", encoding="utf-8")


def load_monitor_snapshot(paths: ServicePaths) -> MonitorSnapshot | None:
    if not paths.state_file.is_file():
        return None
    raw = json.loads(paths.state_file.read_text(encoding="utf-8"))
    match raw:
        case {
            "workspaceRoot": str(workspace_root),
            "workspaceName": str(workspace_name),
            "checkedAt": str(checked_at),
            "totalRepoCount": int(total_repo_count),
            "dirtyRepoCount": int(dirty_repo_count),
            "staleRepoCount": int(stale_repo_count),
            "errorRepoCount": int(error_repo_count),
            "color": str(color),
            "repos": list(repos_raw),
        }:
            repos: list[MonitorRepoState] = []
            for repo_raw in repos_raw:
                match repo_raw:
                    case {
                        "name": str(name),
                        "path": str(path),
                        "stagedCount": int(staged_count),
                        "unstagedCount": int(unstaged_count),
                        "untrackedCount": int(untracked_count),
                        "dirtySince": dirty_since_raw,
                        "error": error_raw,
                    }:
                        dirty_since: datetime | None
                        match dirty_since_raw:
                            case None:
                                dirty_since = None
                            case str(dirty_since_text):
                                dirty_since = datetime.fromisoformat(dirty_since_text)
                            case _:
                                dirty_since = None

                        error_text: str | None
                        match error_raw:
                            case None:
                                error_text = None
                            case str(error_value):
                                error_text = error_value
                            case _:
                                error_text = None

                        repos.append(
                            MonitorRepoState(
                                name=name,
                                path=Path(path),
                                staged_count=staged_count,
                                unstaged_count=unstaged_count,
                                untracked_count=untracked_count,
                                error=error_text,
                                dirty_since=dirty_since,
                            )
                        )
                    case _:
                        continue

            if color not in {"green", "yellow", "red"}:
                return None

            return MonitorSnapshot(
                workspace_root=Path(workspace_root),
                workspace_name=workspace_name,
                checked_at=datetime.fromisoformat(checked_at),
                total_repo_count=total_repo_count,
                dirty_repo_count=dirty_repo_count,
                stale_repo_count=stale_repo_count,
                error_repo_count=error_repo_count,
                color=color,
                repos=tuple(repos),
            )
        case _:
            return None


def _repo_sort_key(repo: MonitorRepoState) -> tuple[int, float, str]:
    if not repo.is_dirty:
        return (1, float("inf"), repo.name)
    if repo.dirty_since is None:
        return (0, float("inf"), repo.name)
    return (0, repo.dirty_since.timestamp(), repo.name)


def _color_for_counts(dirty_repo_count: int, stale_repo_count: int, error_repo_count: int) -> MonitorColor:
    if error_repo_count > 0 or stale_repo_count > 0:
        return "red"
    if dirty_repo_count == 0:
        return "green"
    if dirty_repo_count <= 3:
        return "yellow"
    return "red"


def build_monitor_snapshot(
    workspace_root: Path,
    repo_statuses: Sequence[RepoStatusRecord],
    *,
    checked_at: datetime | None = None,
) -> MonitorSnapshot:
    effective_checked_at = _now_utc() if checked_at is None else checked_at
    repos: list[MonitorRepoState] = []
    dirty_repo_count = 0
    stale_repo_count = 0
    error_repo_count = 0

    for repo_status in repo_statuses:
        dirty_since = repo_status.oldest_dirty_timestamp
        if repo_status.is_dirty:
            dirty_repo_count += 1
            if dirty_since is not None and (effective_checked_at - dirty_since) >= STALE_DIRTY_AFTER:
                stale_repo_count += 1
        if repo_status.error is not None:
            error_repo_count += 1
        repos.append(
            MonitorRepoState(
                name=repo_status.name,
                path=repo_status.path.resolve(),
                staged_count=repo_status.staged_count,
                unstaged_count=repo_status.unstaged_count,
                untracked_count=repo_status.untracked_count,
                error=repo_status.error,
                dirty_since=dirty_since,
            )
        )

    repos.sort(key=_repo_sort_key)
    color = _color_for_counts(dirty_repo_count, stale_repo_count, error_repo_count)
    return MonitorSnapshot(
        workspace_root=workspace_root.resolve(),
        workspace_name=workspace_root.resolve().name or "workspace",
        checked_at=effective_checked_at,
        total_repo_count=len(repo_statuses),
        dirty_repo_count=dirty_repo_count,
        stale_repo_count=stale_repo_count,
        error_repo_count=error_repo_count,
        color=color,
        repos=tuple(repos),
    )


def format_dirty_age(dirty_since: datetime | None, *, now: datetime | None = None) -> str:
    if dirty_since is None:
        return "-"
    effective_now = _now_utc() if now is None else now
    total_seconds = max(0, int((effective_now - dirty_since).total_seconds()))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_local_timestamp(timestamp: datetime, *, timezone: tzinfo | None = None) -> str:
    effective_timestamp = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    localized = effective_timestamp.astimezone() if timezone is None else effective_timestamp.astimezone(timezone)
    return localized.strftime("%Y-%m-%d %H:%M:%S %Z")


def repo_check_spacing_seconds(interval_seconds: int, repo_count: int) -> float:
    normalized_interval = max(1, interval_seconds)
    normalized_repo_count = max(1, repo_count)
    return max(MIN_REPO_CHECK_SPACING_SECONDS, normalized_interval / normalized_repo_count)


def icon_for_snapshot(snapshot: MonitorSnapshot) -> str:
    if snapshot.color == "green":
        return "🟢"
    if snapshot.color == "yellow":
        return f"🟡 {snapshot.dirty_repo_count}"
    if snapshot.error_repo_count > 0:
        return f"🔴 !{snapshot.error_repo_count}"
    return f"🔴 {snapshot.dirty_repo_count}"


__all__ = [
    "MonitorColor",
    "MonitorRepoState",
    "MonitorSnapshot",
    "STALE_DIRTY_AFTER",
    "ServicePaths",
    "ServicePid",
    "build_monitor_snapshot",
    "cleanup_stale_service_pid",
    "ensure_service_dir",
    "format_dirty_age",
    "format_local_timestamp",
    "icon_for_snapshot",
    "load_monitor_snapshot",
    "load_service_pid",
    "process_is_alive",
    "repo_check_spacing_seconds",
    "remove_service_pid",
    "service_paths_for_workspace",
    "terminate_process",
    "write_monitor_snapshot",
    "write_service_pid",
]
