from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dev.config import find_workspace_root
from dev.dashboard_process import ensure_dashboard_server, stop_dashboard_server
from dev.failure_context import contextualize_failure
from dev.messages import accent, error, heading, info, muted, success, warning
from dev.service_db import load_backup_repo_summaries
from dev.service_support import (
    cleanup_stale_dashboard_pid,
    ServicePid,
    cleanup_stale_service_pid,
    ensure_service_dir,
    format_dirty_age,
    load_dashboard_pid,
    load_dashboard_snapshot_summary,
    format_local_timestamp,
    format_tracking_status,
    icon_for_snapshot,
    load_monitor_snapshot,
    load_service_pid,
    process_is_alive,
    remove_service_pid,
    service_paths_for_workspace,
    terminate_process,
    write_service_pid,
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
    cleanup_stale_dashboard_pid(paths)
    pid_info = load_service_pid(paths)
    stopped_monitor = False
    if pid_info is not None:
        try:
            terminate_process(pid_info.pid)
        except OSError as ex:
            remove_service_pid(paths)
            warning(f"Service pid {pid_info.pid} was not running cleanly: {ex}")
        else:
            remove_service_pid(paths)
            success(f"Stopped repo monitor for {workspace_root} (pid {pid_info.pid}).")
            stopped_monitor = True

    dashboard_result = stop_dashboard_server(workspace_root)
    stopped_dashboard = dashboard_result.ok
    if stopped_dashboard:
        success(dashboard_result.message)

    if not stopped_monitor and not stopped_dashboard:
        warning(f"No running repo monitor or dashboard found for {workspace_root}.")
        return 1
    return 0


def service_status() -> int:
    workspace_root = _workspace_root()
    if workspace_root is None:
        error(contextualize_failure("Could not find root.clj for service status.", ["service", "status"]))
        return 1

    paths = service_paths_for_workspace(workspace_root)
    cleanup_stale_service_pid(paths)
    cleanup_stale_dashboard_pid(paths)
    pid_info = load_service_pid(paths)
    snapshot = load_monitor_snapshot(paths)
    dashboard_pid = load_dashboard_pid(paths)
    dashboard_summary = load_dashboard_snapshot_summary(paths)
    backup_summaries = load_backup_repo_summaries(paths)

    print(f"{heading('Workspace')}: {muted(workspace_root)}")

    monitor_running = pid_info is not None
    if monitor_running and pid_info is not None:
        print(f"{heading('Monitor')}: {accent('running', 'green')} (pid {pid_info.pid})")
        print(f"  Interval: {pid_info.interval_seconds}s")
        print(f"  Logs: {muted(paths.stdout_log)} / {muted(paths.stderr_log)}")
        if snapshot is None:
            print(f"  State: {muted('Waiting for first snapshot.')}")
        else:
            print(
                f"  Snapshot: {format_local_timestamp(snapshot.checked_at)} {icon_for_snapshot(snapshot)} "
                f"({snapshot.dirty_repo_count}/{snapshot.total_repo_count} dirty, {snapshot.stale_repo_count} stale)"
            )
            dirty_repos = [repo for repo in snapshot.repos if repo.is_dirty]
            if not dirty_repos:
                print(f"  {muted('All repos clean.')}")
            else:
                for repo in dirty_repos[:12]:
                    age_text = format_dirty_age(repo.dirty_since)
                    counts = f"{repo.staged_count}/{repo.unstaged_count}/{repo.untracked_count}"
                    suffix = f" error={repo.error}" if repo.error is not None else ""
                    tracking_suffix = ""
                    if repo.error is None:
                        tracking_suffix = f" tracking={format_tracking_status(repo)}"
                    print(f"  {accent(repo.name, 'yellow')} age={age_text} counts={counts}{tracking_suffix}{suffix}")
                if len(dirty_repos) > 12:
                    print(f"  {muted(f'... and {len(dirty_repos) - 12} more')}")
    else:
        print(f"{heading('Monitor')}: {muted('not running')}")
        if snapshot is not None:
            print(f"  Last snapshot: {format_local_timestamp(snapshot.checked_at)} {icon_for_snapshot(snapshot)}")

    dashboard_running = dashboard_pid is not None
    if dashboard_running and dashboard_pid is not None:
        print(f"{heading('Dashboard')}: {accent('running', 'green')} (pid {dashboard_pid.pid})")
        print(f"  URL: {muted(f'http://127.0.0.1:{dashboard_pid.port}/')}")
        print(f"  Logs: {muted(paths.dashboard_stdout_log)} / {muted(paths.dashboard_stderr_log)}")
        if dashboard_summary is not None:
            print(
                "  State: "
                f"{format_local_timestamp(dashboard_summary.updated_at)} "
                f"({dashboard_summary.dirty_repo_count}/{dashboard_summary.repo_count} dirty, "
                f"{dashboard_summary.publishable_repo_count} publishable)"
            )
    else:
        print(f"{heading('Dashboard')}: {muted('not running')}")
        if dashboard_summary is not None:
            print(f"  Last state: {format_local_timestamp(dashboard_summary.updated_at)}")

    if not backup_summaries:
        print(f"{heading('Backups')}: {muted('no recorded backup activity')}")
    else:
        latest_attempts = [summary.last_attempted_at for summary in backup_summaries if summary.last_attempted_at is not None]
        success_count = sum(1 for summary in backup_summaries if summary.last_status == "success")
        error_count = sum(1 for summary in backup_summaries if summary.last_status == "error")
        latest_attempt_text = (
            format_local_timestamp(max(latest_attempts))
            if latest_attempts
            else muted("unknown")
        )
        print(
            f"{heading('Backups')}: "
            f"{success_count} ok, {error_count} error, latest attempt {latest_attempt_text}"
        )
        failing_summaries = [summary for summary in backup_summaries if summary.last_status == "error"]
        for summary in failing_summaries[:8]:
            attempted_text = (
                format_local_timestamp(summary.last_attempted_at)
                if summary.last_attempted_at is not None
                else "unknown"
            )
            detail = summary.last_message or "backup failed"
            print(f"  {accent(summary.repo_name, 'red')} at {attempted_text}: {detail}")
        if len(failing_summaries) > 8:
            print(f"  {muted(f'... and {len(failing_summaries) - 8} more backup failures')}")

    if not monitor_running and not dashboard_running:
        warning(f"No workspace services are running for {workspace_root}.")
        return 1
    return 0


def service_dashboard(*, interval_seconds: int = 60) -> int:
    workspace_root = _workspace_root()
    if workspace_root is None:
        error(contextualize_failure("Could not find root.clj for dashboard startup.", ["service", "dashboard"]))
        return 1

    result = ensure_dashboard_server(workspace_root, interval_seconds=interval_seconds, open_browser=True)
    if not result.ok:
        error(result.message)
        return 1

    success(result.message)
    paths = service_paths_for_workspace(workspace_root)
    print(f"  URL: {muted(result.url or '-')}")
    print(f"  Logs: {muted(paths.dashboard_stdout_log)} / {muted(paths.dashboard_stderr_log)}")
    return 0


__all__ = [
    "service_dashboard",
    "service_start",
    "service_status",
    "service_stop",
]
