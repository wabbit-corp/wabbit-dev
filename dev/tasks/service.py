from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dev.config import find_workspace_root
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, heading, info, muted, success, warning
from dev.service_support import (
    cleanup_stale_service_pid,
    ensure_service_dir,
    format_dirty_age,
    icon_for_snapshot,
    load_monitor_snapshot,
    load_service_pid,
    process_is_alive,
    remove_service_pid,
    service_paths_for_workspace,
    terminate_process,
    write_service_pid,
    ServicePid,
)


def _workspace_root() -> Path | None:
    root = find_workspace_root()
    return root.resolve() if root is not None else None


def _service_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _macos_supported() -> bool:
    return sys.platform == "darwin"


def _service_command(workspace_root: Path, *, interval_seconds: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "dev.menubar_service",
        "--workspace-root",
        str(workspace_root),
        "--interval-seconds",
        str(interval_seconds),
    ]


def service_start(*, interval_seconds: int = 60) -> int:
    workspace_root = _workspace_root()
    if workspace_root is None:
        error(contextualize_failure("Could not find root.clj for service startup.", ["service", "start"]))
        return 1
    if not _macos_supported():
        error("The repo monitor menubar service currently supports macOS only.")
        return 1

    paths = service_paths_for_workspace(workspace_root)
    cleanup_stale_service_pid(paths)
    existing_pid = load_service_pid(paths)
    if existing_pid is not None and process_is_alive(existing_pid.pid):
        snapshot = load_monitor_snapshot(paths)
        if snapshot is None:
            info(f"Service already running for {workspace_root} (pid {existing_pid.pid}).")
        else:
            info(
                f"Service already running for {workspace_root} (pid {existing_pid.pid}) "
                f"{icon_for_snapshot(snapshot)}"
            )
        return 0

    ensure_service_dir(paths)
    with open(paths.stdout_log, "a", encoding="utf-8") as stdout_log:
        with open(paths.stderr_log, "a", encoding="utf-8") as stderr_log:
            process = subprocess.Popen(
                _service_command(workspace_root, interval_seconds=interval_seconds),
                cwd=_service_project_root(),
                stdout=stdout_log,
                stderr=stderr_log,
                start_new_session=True,
            )

    pid_info = ServicePid(
        pid=process.pid,
        workspace_root=workspace_root,
        started_at=datetime.now(UTC),
        interval_seconds=interval_seconds,
    )
    write_service_pid(paths, pid_info)

    time.sleep(0.5)
    if not process_is_alive(process.pid):
        remove_service_pid(paths)
        error(
            "Service process exited immediately. "
            f"See logs at {paths.stdout_log} and {paths.stderr_log}."
        )
        return 1

    success(f"Started repo monitor for {workspace_root} (pid {process.pid}).")
    print(f"  Interval: {interval_seconds}s")
    print(f"  Logs: {muted(paths.stdout_log)} / {muted(paths.stderr_log)}")
    return 0


def service_stop() -> int:
    workspace_root = _workspace_root()
    if workspace_root is None:
        error(contextualize_failure("Could not find root.clj for service shutdown.", ["service", "stop"]))
        return 1

    paths = service_paths_for_workspace(workspace_root)
    cleanup_stale_service_pid(paths)
    pid_info = load_service_pid(paths)
    if pid_info is None:
        warning(f"No running repo monitor found for {workspace_root}.")
        return 1

    try:
        terminate_process(pid_info.pid)
    except OSError as ex:
        remove_service_pid(paths)
        warning(f"Service pid {pid_info.pid} was not running cleanly: {ex}")
        return 1

    remove_service_pid(paths)
    success(f"Stopped repo monitor for {workspace_root} (pid {pid_info.pid}).")
    return 0


def service_status() -> int:
    workspace_root = _workspace_root()
    if workspace_root is None:
        error(contextualize_failure("Could not find root.clj for service status.", ["service", "status"]))
        return 1

    paths = service_paths_for_workspace(workspace_root)
    cleanup_stale_service_pid(paths)
    pid_info = load_service_pid(paths)
    snapshot = load_monitor_snapshot(paths)

    if pid_info is None:
        warning(f"Repo monitor is not running for {workspace_root}.")
        if snapshot is not None:
            print(f"  Last snapshot: {snapshot.checked_at.isoformat()}")
            print(f"  Last state: {icon_for_snapshot(snapshot)}")
        return 1

    print(f"{heading('Service')}: {accent('running', 'green')} (pid {pid_info.pid})")
    print(f"{heading('Workspace')}: {muted(workspace_root)}")
    print(f"{heading('Interval')}: {pid_info.interval_seconds}s")
    print(f"{heading('Logs')}: {muted(paths.stdout_log)} / {muted(paths.stderr_log)}")

    if snapshot is None:
        print(f"{heading('State')}: {muted('Waiting for first snapshot.')}")
        return 0

    print(
        f"{heading('Snapshot')}: {snapshot.checked_at.isoformat()} {icon_for_snapshot(snapshot)} "
        f"({snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, {snapshot.stale_repo_count} stale)"
    )
    dirty_repos = [repo for repo in snapshot.repos if repo.is_dirty]
    if not dirty_repos:
        print(f"  {muted('All repos clean.')}")
        return 0

    print(f"{heading('Dirty Repos')}:")
    for repo in dirty_repos[:12]:
        age_text = format_dirty_age(repo.dirty_since)
        counts = f"{repo.staged_count}/{repo.unstaged_count}/{repo.untracked_count}"
        suffix = f" error={repo.error}" if repo.error is not None else ""
        print(f"  {accent(repo.name, 'yellow')} age={age_text} counts={counts}{suffix}")
    if len(dirty_repos) > 12:
        print(f"  {muted(f'... and {len(dirty_repos) - 12} more')}")
    return 0


__all__ = [
    "service_start",
    "service_status",
    "service_stop",
]
