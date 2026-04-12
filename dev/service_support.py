from __future__ import annotations

import json
import os
import signal
import sys
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
    branch_name: str | None = None
    upstream_name: str | None = None
    ahead_count: int | None = None
    behind_count: int | None = None
    tracking_refreshed_at: datetime | None = None

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
            "branchName": self.branch_name,
            "upstreamName": self.upstream_name,
            "aheadCount": self.ahead_count,
            "behindCount": self.behind_count,
            "trackingRefreshedAt": (
                self.tracking_refreshed_at.isoformat() if self.tracking_refreshed_at is not None else None
            ),
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
    dashboard_state_file: Path
    stdout_log: Path
    stderr_log: Path
    dashboard_pid_file: Path
    dashboard_stdout_log: Path
    dashboard_stderr_log: Path


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


@dataclass(frozen=True)
class DashboardPid:
    pid: int
    workspace_root: Path
    started_at: datetime
    interval_seconds: int
    port: int

    def to_json(self) -> JSONObject:
        return {
            "pid": self.pid,
            "workspaceRoot": str(self.workspace_root),
            "startedAt": self.started_at.isoformat(),
            "intervalSeconds": self.interval_seconds,
            "port": self.port,
        }


@dataclass(frozen=True)
class DashboardSnapshotSummary:
    workspace_root: Path
    workspace_name: str
    updated_at: datetime
    dirty_repo_count: int
    publishable_repo_count: int
    repo_count: int


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _workspace_service_root(workspace_root: Path) -> Path:
    digest = sha1(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:12]
    workspace_name = workspace_root.resolve().name or "workspace"
    return _service_storage_root() / f"{workspace_name}-{digest}"


def _service_storage_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dev" / "service"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "dev" / "service"
        return Path.home() / "AppData" / "Roaming" / "dev" / "service"

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "dev" / "service"
    return Path.home() / ".local" / "state" / "dev" / "service"


def service_paths_for_workspace(workspace_root: Path) -> ServicePaths:
    root = _workspace_service_root(workspace_root)
    return ServicePaths(
        root=root,
        pid_file=root / "monitor.pid.json",
        state_file=root / "monitor.state.json",
        dashboard_state_file=root / "dashboard.state.json",
        stdout_log=root / "monitor.stdout.log",
        stderr_log=root / "monitor.stderr.log",
        dashboard_pid_file=root / "dashboard.pid.json",
        dashboard_stdout_log=root / "dashboard.stdout.log",
        dashboard_stderr_log=root / "dashboard.stderr.log",
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


def write_dashboard_pid(paths: ServicePaths, pid_info: DashboardPid) -> None:
    ensure_service_dir(paths)
    paths.dashboard_pid_file.write_text(json.dumps(pid_info.to_json(), indent=2) + "\n", encoding="utf-8")


def load_dashboard_pid(paths: ServicePaths) -> DashboardPid | None:
    if not paths.dashboard_pid_file.is_file():
        return None
    raw = json.loads(paths.dashboard_pid_file.read_text(encoding="utf-8"))
    match raw:
        case {
            "pid": int(pid),
            "workspaceRoot": str(workspace_root),
            "startedAt": str(started_at),
            "intervalSeconds": int(interval_seconds),
            "port": int(port),
        }:
            return DashboardPid(
                pid=pid,
                workspace_root=Path(workspace_root),
                started_at=datetime.fromisoformat(started_at),
                interval_seconds=interval_seconds,
                port=port,
            )
        case _:
            return None


def remove_dashboard_pid(paths: ServicePaths) -> None:
    if paths.dashboard_pid_file.exists():
        paths.dashboard_pid_file.unlink()


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


def cleanup_stale_dashboard_pid(paths: ServicePaths) -> None:
    pid_info = load_dashboard_pid(paths)
    if pid_info is None:
        return
    if not process_is_alive(pid_info.pid):
        remove_dashboard_pid(paths)


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
                    } as repo_payload:
                        branch_name_raw = repo_payload.get("branchName")
                        upstream_name_raw = repo_payload.get("upstreamName")
                        ahead_count_raw = repo_payload.get("aheadCount")
                        behind_count_raw = repo_payload.get("behindCount")
                        tracking_refreshed_at_raw = repo_payload.get("trackingRefreshedAt")
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

                        branch_name: str | None
                        match branch_name_raw:
                            case None:
                                branch_name = None
                            case str(branch_name_value):
                                branch_name = branch_name_value
                            case _:
                                branch_name = None

                        upstream_name: str | None
                        match upstream_name_raw:
                            case None:
                                upstream_name = None
                            case str(upstream_name_value):
                                upstream_name = upstream_name_value
                            case _:
                                upstream_name = None

                        ahead_count: int | None
                        match ahead_count_raw:
                            case None:
                                ahead_count = None
                            case int(ahead_count_value):
                                ahead_count = ahead_count_value
                            case _:
                                ahead_count = None

                        behind_count: int | None
                        match behind_count_raw:
                            case None:
                                behind_count = None
                            case int(behind_count_value):
                                behind_count = behind_count_value
                            case _:
                                behind_count = None

                        tracking_refreshed_at: datetime | None
                        match tracking_refreshed_at_raw:
                            case None:
                                tracking_refreshed_at = None
                            case str(tracking_refreshed_at_text):
                                tracking_refreshed_at = datetime.fromisoformat(tracking_refreshed_at_text)
                            case _:
                                tracking_refreshed_at = None

                        repos.append(
                            MonitorRepoState(
                                name=name,
                                path=Path(path),
                                staged_count=staged_count,
                                unstaged_count=unstaged_count,
                                untracked_count=untracked_count,
                                error=error_text,
                                dirty_since=dirty_since,
                                branch_name=branch_name,
                                upstream_name=upstream_name,
                                ahead_count=ahead_count,
                                behind_count=behind_count,
                                tracking_refreshed_at=tracking_refreshed_at,
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


def load_dashboard_snapshot_summary(paths: ServicePaths) -> DashboardSnapshotSummary | None:
    if not paths.dashboard_state_file.is_file():
        return None
    raw = json.loads(paths.dashboard_state_file.read_text(encoding="utf-8"))
    match raw:
        case {
            "workspaceRoot": str(workspace_root),
            "workspaceName": str(workspace_name),
            "updatedAt": str(updated_at),
            "dirtyRepoCount": int(dirty_repo_count),
            "publishableRepoCount": int(publishable_repo_count),
            "repos": list(repos_raw),
        }:
            return DashboardSnapshotSummary(
                workspace_root=Path(workspace_root),
                workspace_name=workspace_name,
                updated_at=datetime.fromisoformat(updated_at),
                dirty_repo_count=dirty_repo_count,
                publishable_repo_count=publishable_repo_count,
                repo_count=len(repos_raw),
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
                branch_name=repo_status.tracking.branch_name if repo_status.tracking is not None else None,
                upstream_name=repo_status.tracking.upstream_name if repo_status.tracking is not None else None,
                ahead_count=repo_status.tracking.ahead_count if repo_status.tracking is not None else None,
                behind_count=repo_status.tracking.behind_count if repo_status.tracking is not None else None,
                tracking_refreshed_at=repo_status.tracking_refreshed_at,
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


def format_tracking_status(repo: MonitorRepoState) -> str:
    branch_name = repo.branch_name or "HEAD"
    if repo.upstream_name is None:
        return f"{branch_name} (no upstream)"

    ahead_count = repo.ahead_count if repo.ahead_count is not None else 0
    behind_count = repo.behind_count if repo.behind_count is not None else 0
    return f"{branch_name} vs {repo.upstream_name}: ahead {ahead_count}, behind {behind_count}"


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
    "DashboardPid",
    "DashboardSnapshotSummary",
    "ServicePaths",
    "ServicePid",
    "build_monitor_snapshot",
    "cleanup_stale_dashboard_pid",
    "cleanup_stale_service_pid",
    "ensure_service_dir",
    "format_dirty_age",
    "format_local_timestamp",
    "format_tracking_status",
    "icon_for_snapshot",
    "load_dashboard_pid",
    "load_dashboard_snapshot_summary",
    "load_monitor_snapshot",
    "load_service_pid",
    "process_is_alive",
    "repo_check_spacing_seconds",
    "remove_dashboard_pid",
    "remove_service_pid",
    "service_paths_for_workspace",
    "terminate_process",
    "write_dashboard_pid",
    "write_monitor_snapshot",
    "write_service_pid",
]
